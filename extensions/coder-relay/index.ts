import { execFileSync } from "node:child_process";
import { appendFileSync, existsSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { basename, dirname, join } from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

/**
 * Coder relay - seamless orchestrator takeover for the coder skill.
 *
 * The coder skill's relay procedure writes pipeline state to
 * `<git-common-dir>/coder-handoffs/<session-id>/00-progress.json`. When the
 * orchestrator wants a takeover it sets the discrete `relay_ready: true` flag
 * in that file and ends its turn. On `agent_end` this extension checks for the
 * flag (no baselines, no increment inference), dispatches the `/coder-relay`
 * command, and the command clears the flag before replacing the session in
 * place with a fresh one that continues the pipeline: same TUI window, token
 * count resets, no orphan process.
 *
 * Every agent_end scan appends one decision line to
 * `<handoff-root>/.relay-log.jsonl` so silent no-ops stay diagnosable.
 *
 * At `session_start`, a pending flag from an interrupted pipeline is surfaced
 * to the user (with the exact resume command) instead of being silently
 * swallowed.
 */

interface Progress {
	session_id?: string;
	next_step?: string;
	relay_count?: number;
	relay_ready?: boolean;
}

const BOOTSTRAP_TEMPLATE =
	"You are the coder orchestrator for session $SESSION_ID. " +
	"Handoff dir: $HANDOFF. Read 00-progress.json and continue at next_step.";

export default function coderRelay(pi: ExtensionAPI): void {
	function handoffRoot(cwd: string): string | null {
		try {
			const commonDir = execFileSync("git", ["rev-parse", "--path-format=absolute", "--git-common-dir"], {
				cwd,
				encoding: "utf8",
				stdio: ["ignore", "pipe", "ignore"],
			}).trim();
			return commonDir ? join(commonDir, "coder-handoffs") : null;
		} catch {
			return null;
		}
	}

	function readProgress(file: string): Progress | null {
		try {
			const parsed = JSON.parse(readFileSync(file, "utf8")) as Progress;
			return typeof parsed === "object" && parsed !== null ? parsed : null;
		} catch {
			return null;
		}
	}

	/** Discrete takeover signal: the flag, and only the flag. */
	function isPending(progress: Progress): boolean {
		return progress.relay_ready === true && progress.next_step !== "COMPLETE";
	}

	function scan(cwd: string): Array<{ dir: string; file: string; progress: Progress }> {
		const found: Array<{ dir: string; file: string; progress: Progress }> = [];
		const root = handoffRoot(cwd);
		if (!root || !existsSync(root)) return found;
		for (const entry of readdirSync(root).sort()) {
			const file = join(root, entry, "00-progress.json");
			if (!existsSync(file)) continue;
			const progress = readProgress(file);
			if (!progress || !isPending(progress)) continue;
			found.push({ dir: join(root, entry), file, progress });
		}
		return found;
	}

	function logDecision(root: string, decision: Record<string, unknown>): void {
		try {
			const line = JSON.stringify({ ts: new Date().toISOString(), ...decision }) + "\n";
			appendFileSync(join(root, ".relay-log.jsonl"), line);
		} catch {
			// Best-effort diagnosability; never block the pipeline on logging.
		}
	}

	pi.on("session_start", async (_event, ctx) => {
		if (ctx.mode !== "tui") return;
		const pending = scan(ctx.cwd);
		for (const { dir, progress } of pending) {
			ctx.ui.notify(
				`coder-relay: interrupted pipeline found (session ${progress.session_id}, relay ${progress.relay_count ?? 0}). ` +
					`Resume with: /coder-relay ${dir}`,
				"info",
			);
		}
	});

	pi.on("agent_end", async (_event, ctx) => {
		// Interactive takeover only; headless modes keep the detached fallback.
		if (ctx.mode !== "tui") return;
		const root = handoffRoot(ctx.cwd);
		const pending = scan(ctx.cwd);
		if (root) logDecision(root, { event: "agent_end", cwd: ctx.cwd, pending: pending.length });
		if (pending.length === 0) return;
		const { dir } = pending[0];
		// expandPromptTemplates dispatches the extension command below, giving
		// the replacement a proper command context.
		pi.sendUserMessage(`/coder-relay ${dir}`, { expandPromptTemplates: true });
	});

	pi.registerCommand("coder-relay", {
		description: "Replace the current session in place with the coder successor (args: handoff dir)",
		handler: async (args, ctx) => {
			if (ctx.mode !== "tui") {
				ctx.ui.notify("coder-relay requires interactive mode", "error");
				return;
			}
			const dir = args.trim();
			const file = dir ? join(dir, "00-progress.json") : "";
			const progress = file ? readProgress(file) : null;
			if (!dir || !progress?.session_id || typeof progress.relay_count !== "number") {
				ctx.ui.notify("Usage: /coder-relay <handoff-dir with 00-progress.json>", "error");
				return;
			}
			if (progress.next_step === "COMPLETE") {
				ctx.ui.notify(`Session ${progress.session_id} is COMPLETE; nothing to relay`, "info");
				return;
			}

			// Consume the flag before takeover so a failed or cancelled
			// replacement never re-triggers on the next agent_end. Boot sanity
			// and the relay_count circuit breaker stay in the skill.
			try {
				const updated = { ...progress, relay_ready: false };
				writeFileSync(file, JSON.stringify(updated));
			} catch (err) {
				ctx.ui.notify(`coder-relay: could not clear relay_ready: ${err}`, "error");
				return;
			}

			const parentSession = ctx.sessionManager.getSessionFile();
			const bootstrap = BOOTSTRAP_TEMPLATE.replace("$SESSION_ID", progress.session_id).replace("$HANDOFF", dir);
			ctx.ui.notify(`Relay: handing off to generation ${progress.relay_count} (${basename(dir)})`, "info");
			const result = await ctx.newSession({
				parentSession: parentSession ?? undefined,
				withSession: async (replacement) => {
					await replacement.sendUserMessage(bootstrap);
				},
			});
			if (result.cancelled) {
				ctx.ui.notify(`Relay cancelled; current session continues. Retry with: /coder-relay ${dir}`, "info");
			}
		},
	});
}
