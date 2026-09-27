// mmd2excalidraw.test.mjs — tests for the Mermaid → Excalidraw converter.
// Run: node --test scripts/figures/
import test from "node:test";
import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const script = path.join(path.dirname(fileURLToPath(import.meta.url)), "mmd2excalidraw.mjs");

function run(mmd, out) {
  return new Promise((resolve) => {
    execFile("node", [script, mmd, out], (err, stdout, stderr) => {
      resolve({ code: err?.code ?? 0, stdout, stderr });
    });
  });
}

test("flowchart converts to typed elements with no image fallback", async () => {
  // Arrange
  const dir = await mkdtemp(path.join(tmpdir(), "mmd2x-"));
  const src = path.join(dir, "in.mmd");
  const out = path.join(dir, "out.excalidraw");
  await writeFile(src, [
    "flowchart TD",
    "  A[Entry] --> B[Work]",
    "  classDef core fill:#ffec99",
    "  class A core",
  ].join("\n"));

  // Act
  const { code } = await run(src, out);
  const scene = JSON.parse(await readFile(out, "utf8"));

  // Assert
  assert.equal(code, 0);
  assert.equal(scene.type, "excalidraw");
  const types = new Set(scene.elements.map((e) => e.type));
  assert.ok(types.has("rectangle"), "nodes are rectangles");
  assert.ok(types.has("arrow"), "edges are arrows");
  assert.ok(!types.has("image"), "no embedded-image fallback");
  const styled = scene.elements.find((e) => e.type === "rectangle");
  assert.equal(styled.fontFamily, 5, "Excalifont applied");
  assert.equal(styled.backgroundColor, "#ffec99", "classDef fill mapped");
  await rm(dir, { recursive: true, force: true });
});

test("unsupported mermaid type exits non-zero with image-fallback error", async () => {
  // Arrange
  const dir = await mkdtemp(path.join(tmpdir(), "mmd2x-"));
  const src = path.join(dir, "in.mmd");
  const out = path.join(dir, "out.excalidraw");
  await writeFile(src, ["pie title Demo", '  "a": 42'].join("\n"));

  // Act
  const { code, stderr } = await run(src, out);

  // Assert
  assert.equal(code, 1);
  assert.match(stderr, /not supported/);
  await assert.rejects(() => readFile(out, "utf8"), "no output written on fallback");
  await rm(dir, { recursive: true, force: true });
});
