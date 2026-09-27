#!/usr/bin/env node
// mmd2excalidraw.mjs — Mermaid .mmd → styled .excalidraw (figure pipeline).
//
// Pipeline: @excalidraw/mermaid-to-excalidraw (parse + layout) →
// convertToExcalidrawElements (flatten labels) → style pass (Excalifont,
// sketchy strokes, palette fills per docs/diagrams conventions in
// clouatre-labs/decisions-judge-mcp) → determinism pass (stable ids/seeds so
// the committed artifact is byte-stable for the CI drift check).
//
// Exits non-zero when mermaid silently falls back to an embedded SVG image
// (unsupported diagram type): the result would not be editable, which defeats
// the purpose of the pipeline.
//
// Usage: node mmd2excalidraw.mjs input.mmd [output.excalidraw]
import { registerHooks, register } from "node:module";
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { JSDOM } from "jsdom";

// Loader hooks must be installed before the bundler-built Excalidraw packages
// are imported (see mmd-loader.mjs for what each hook shims).
import * as hooks from "./mmd-loader.mjs";
if (typeof registerHooks === "function") {
  registerHooks({ resolve: hooks.resolve, load: hooks.load });
} else {
  register(new URL("./mmd-loader.mjs", import.meta.url));
}

const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>", {
  pretendToBeVisual: true,
  url: "https://localhost/",
});
for (const k of ["window", "document", "navigator", "localStorage", "CustomEvent", "getComputedStyle", "CSSStyleSheet", "SVGElement", "HTMLElement", "Element", "Node"]) {
  globalThis[k] ??= dom.window[k];
}
globalThis.navigator ??= dom.window.navigator;
globalThis.devicePixelRatio ??= 1;
// FontFace API stub: fonts are never loaded, only measured via canvas.
globalThis.FontFace ??= class FontFace {
  constructor(family, source) { this.family = family; this.source = source; this.status = "loaded"; }
  load() { return Promise.resolve(this); }
};
globalThis.document.fonts ??= { add() {}, delete() {}, ready: Promise.resolve(), addEventListener() {} };
globalThis.requestAnimationFrame ??= dom.window.requestAnimationFrame?.bind(dom.window) ?? ((cb) => setTimeout(cb, 16));
globalThis.matchMedia ??= dom.window.matchMedia?.bind(dom.window) ?? (() => ({ matches: false, addEventListener() {}, removeEventListener() {} }));

// Deterministic Math.random (seeded LCG): rough.js path jitter and library
// internals feed edge-label positions, which must be byte-stable across runs
// for the CI drift check.
let rngState = 0x2f6e2b1;
Math.random = () => {
  rngState = (Math.imul(rngState, 1664525) + 1013904223) >>> 0;
  return rngState / 4294967296;
};
// nanoid & friends draw from crypto, not Math.random — same determinism need.
try {
  globalThis.crypto = {
    ...(globalThis.crypto ?? {}),
    getRandomValues: (arr) => {
      for (let i = 0; i < arr.length; i++) {
        rngState = (Math.imul(rngState, 1664525) + 1013904223) >>> 0;
        arr[i] = rngState;
      }
      return arr;
    },
  };
} catch {
  // webcrypto global is non-writable on some runtimes; leave as-is.
}

// jsdom has no text layout: stub getBBox with a character-based estimate so
// mermaid's dagre layout can measure labels. Runs before mermaid is imported.
// Excalifont is ~5% wider than Helvetica: char factor 0.68 + padding 26 keeps
// frames from clipping (single global constant, not per-diagram tweaks).
function attrNum(el, name, dflt = 0) {
  const v = el.getAttribute?.(name);
  return v == null ? dflt : parseFloat(v);
}
function bboxOf(el) {
  const tag = (el.tagName || "").toLowerCase();
  if (tag === "rect") {
    return { x: attrNum(el, "x"), y: attrNum(el, "y"), width: attrNum(el, "width", 10), height: attrNum(el, "height", 10) };
  }
  if (tag === "circle") {
    const r = attrNum(el, "r", 5);
    return { x: attrNum(el, "cx") - r, y: attrNum(el, "cy") - r, width: 2 * r, height: 2 * r };
  }
  if (tag === "ellipse") {
    const rx = attrNum(el, "rx", 5), ry = attrNum(el, "ry", 5);
    return { x: attrNum(el, "cx") - rx, y: attrNum(el, "cy") - ry, width: 2 * rx, height: 2 * ry };
  }
  if (tag === "polygon" || tag === "polyline") {
    const pts = (el.getAttribute("points") || "").trim().split(/[\s,]+/).map(Number).filter((n) => !isNaN(n));
    if (pts.length >= 4) {
      const xs = pts.filter((_, i) => i % 2 === 0), ys = pts.filter((_, i) => i % 2 === 1);
      return { x: Math.min(...xs), y: Math.min(...ys), width: Math.max(...xs) - Math.min(...xs), height: Math.max(...ys) - Math.min(...ys) };
    }
  }
  const children = [...(el.children || [])];
  if (children.length > 0 && (tag === "g" || children.some((c) => (c.tagName || "").toLowerCase() === "g"))) {
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const child of children) {
      if (!child.getBBox) continue;
      const b = child.getBBox();
      if (!b || !isFinite(b.x)) continue;
      let tx = 0, ty = 0;
      const t = /translate\(\s*([\d.eE+-]+)[\s,]*([\d.eE+-]*)/.exec(child.getAttribute?.("transform") || "");
      if (t) { tx = parseFloat(t[1]); ty = t[2] ? parseFloat(t[2]) : 0; }
      minX = Math.min(minX, b.x + tx); minY = Math.min(minY, b.y + ty);
      maxX = Math.max(maxX, b.x + b.width + tx); maxY = Math.max(maxY, b.y + b.height + ty);
    }
    if (isFinite(minX)) return { x: minX, y: minY, width: maxX - minX, height: maxY - minY };
  }
  // text/label elements: character-based estimate
  const text = (el.textContent || "").trim();
  const lines = text.split("\n");
  const fs = 20;
  const w = Math.max(10, ...lines.map((l) => l.length * fs * 0.68)) + 26;
  const h = Math.max(fs * 1.4, lines.length * fs * 1.45) + 12;
  return { x: -w / 2, y: -h / 2, width: w, height: h };
}
dom.window.SVGElement.prototype.getBBox = function () { return bboxOf(this); };

// ---- .mmd source parsing: node fills (single source of truth is the .mmd) ----

const PALETTE = ["#a5d8ff", "#b2f2bb", "#ffec99", "#ffc9c9"];

function decodeEntities(s) {
  return s
    .replaceAll("&lt;", "<")
    .replaceAll("&gt;", ">")
    .replaceAll("&amp;", "&")
    .replaceAll("&quot;", '"')
    .replaceAll("#quot;", '"');
}

function normalizeLabel(s) {
  return decodeEntities(s).replaceAll("\\n", "\n").trim();
}

// Extract fill assignments from the .mmd source:
//   classDef step fill:#a5d8ff   +   class A,B step   (or inline A[label]:::step)
// Returns { label -> fill } keyed by normalized node label.
function parseFills(source) {
  const classDefs = {};
  for (const m of source.matchAll(/^\s*classDef\s+(\w+)\s+(.+)$/gm)) {
    const fill = /fill:\s*(#[0-9a-fA-F]{3,8}|\w+)/.exec(m[2]);
    if (fill) classDefs[m[1]] = fill[1];
  }
  const members = {}; // className -> [nodeId]
  for (const m of source.matchAll(/^\s*class\s+([\w,\s]+?)\s+(\w+)\s*$/gm)) {
    (classDefs[m[2]] !== undefined ? (members[m[2]] ??= []) : null)?.push(...m[1].split(",").map((s) => s.trim()));
  }
  for (const m of source.matchAll(/(\w+)\[[^\]]*\]:::(\w+)/g)) {
    (members[m[2]] ??= []).push(m[1]);
  }
  // nodeId -> label, from A[label] / A["label"] / A(label) / A{"label"}.
  // Lines starting with `subgraph` define group titles, not nodes.
  const nodeLabel = {};
  for (const line of source.split("\n")) {
    if (/^\s*subgraph\b/.test(line)) continue;
    for (const m of line.matchAll(/(\w+)(?:\["([^"]*)"\]|\[([^\]]*)\]|\("([^"]*)"\)|\{"([^"]*)"\})/g)) {
      const label = m[2] ?? m[3] ?? m[4] ?? m[5];
      if (label != null && label !== "") nodeLabel[m[1]] = label;
    }
  }
  const labelFill = {};
  for (const [className, ids] of Object.entries(members)) {
    const fill = classDefs[className];
    if (!fill) continue;
    for (const id of ids) {
      if (nodeLabel[id] != null) labelFill[normalizeLabel(nodeLabel[id])] = fill;
    }
  }
  // Palette cycle for nodes without a classDef, in edge-declaration order.
  let next = 0;
  for (const line of source.split("\n")) {
    if (/^\s*(classDef|class)\b/.test(line) || /^\s*subgraph\b/.test(line)) continue;
    for (const m of line.matchAll(/(?:^|\s|;)(\w+)(?=\s*(?:\[|\(|\{|\-\->|\-\-\-|\.|\+|$))/g)) {
      const id = m[1];
      if (!(id in nodeLabel)) continue;
      const key = normalizeLabel(nodeLabel[id]);
      if (key in labelFill) continue;
      labelFill[key] = PALETTE[next++ % PALETTE.length];
    }
  }
  return labelFill;
}

// ---- style pass: mirror decisions-judge-mcp diagram conventions ----

const INK = "#1e1e1e";
const EDGE_LABEL_INK = "#6b6b6b";

function applyStyle(elements, labelFill) {
  let paletteIdx = 0;
  for (const el of elements) {
    el.fontFamily = 5;
    el.strokeWidth = 2;
    el.roughness = 1;
    el.opacity = 100;
    if (el.type === "arrow" || el.type === "line") {
      el.strokeColor = INK;
      el.backgroundColor = "transparent";
      el.roundness = { type: 2 };
      continue;
    }
    if (el.type === "text") {
      if (el.containerId) {
        el.fontSize = 18; // text inside boxes
        el.strokeColor = INK;
      } else {
        el.fontSize = 16; // standalone / edge-label text
        el.strokeColor = EDGE_LABEL_INK;
      }
      el.backgroundColor = "transparent";
      continue;
    }
    // shapes
    el.strokeColor = INK;
    el.fillStyle = "solid";
    el.roundness = { type: 3 };
    if (el.type === "rectangle" && el.width > 200 && el.boundElements?.some((b) => b.type === "text")) {
      // Heuristic for subgraph group frames; their titles are long and the
      // frame spans several nodes. They stay unfilled so node colors read
      // through. (Group frames are always wider than any single node here.)
    }
    if (el.containerId === null && el.boundElements?.some((b) => b.type === "text")) {
      const textEl = elements.find((t) => t.containerId === el.id);
      const label = textEl ? normalizeLabel(textEl.text) : null;
      if (label != null && label in labelFill) {
        el.backgroundColor = labelFill[label];
        continue;
      }
      // No explicit fill: fall back to the palette cycle for leaf shapes,
      // leaving subgraph frames transparent (they group other nodes).
      const isGroup = elements.some(
        (t) => t.containerId === el.id && labelFill[normalizeLabel(t.text ?? "")] === undefined && elements.some((n) => n.containerId === t.id),
      );
      if (!isGroup) el.backgroundColor = PALETTE[paletteIdx++ % PALETTE.length];
    }
  }
}

// ---- determinism pass: stable ids, seeds, timestamps for the drift check ----

// Edge-label text positions computed by convertToExcalidrawElements wobble
// sub-pixel to ~1px between runs; recompute them deterministically from the
// binding arrow's endpoint midpoint instead.
function pinEdgeLabels(elements) {
  const byId = new Map(elements.map((el) => [el.id, el]));
  for (const el of elements) {
    if (el.type !== "text" || !el.containerId) continue;
    const c = byId.get(el.containerId);
    if (!c || (c.type !== "arrow" && c.type !== "line")) continue;
    const pts = c.points ?? [];
    if (pts.length < 2) continue;
    const mx = c.x + (pts[0][0] + pts[pts.length - 1][0]) / 2;
    const my = c.y + (pts[0][1] + pts[pts.length - 1][1]) / 2;
    el.x = mx - el.width / 2;
    el.y = my - el.height / 2;
  }
}

function stabilize(elements) {
  const idMap = new Map(elements.map((el, i) => [el.id, `el${i}`]));
  return elements.map((el, i) => ({
    ...el,
    id: idMap.get(el.id),
    containerId: el.containerId ? idMap.get(el.containerId) : el.containerId,
    boundElements: el.boundElements?.map((b) => ({ ...b, id: idMap.get(b.id) })) ?? null,
    startBinding: el.startBinding ? { ...el.startBinding, elementId: idMap.get(el.startBinding.elementId) } : null,
    endBinding: el.endBinding ? { ...el.endBinding, elementId: idMap.get(el.endBinding.elementId) } : null,
    seed: 1000 + i,
    version: 1,
    versionNonce: 2000 + i,
    updated: 1,
  }));
}

// ---- main ----

const inPath = process.argv[2];
const outPath = process.argv[3] ?? inPath.replace(/\.mmd$/, ".excalidraw");
if (!inPath) {
  console.error("usage: node mmd2excalidraw.mjs input.mmd [output.excalidraw]");
  process.exit(2);
}
const source = readFileSync(inPath, "utf8");

const { parseMermaidToExcalidraw } = await import("@excalidraw/mermaid-to-excalidraw");
const { elements, files } = await parseMermaidToExcalidraw(source, {
  startOnLoad: false,
  flowchart: { curve: "linear" },
});
const { convertToExcalidrawElements } = await import("@excalidraw/excalidraw");
let full = convertToExcalidrawElements(elements).map((e) =>
  e.type === "text" && typeof e.text === "string" ? { ...e, text: e.text.replaceAll("\\n", "\n") } : e,
);

// Unsupported diagram types silently degrade to a single embedded SVG image:
// not editable, so reject rather than commit a black-box figure.
if (full.length === 1 && full[0].type === "image") {
  console.error(`error: ${inPath}: mermaid type not supported by @excalidraw/mermaid-to-excalidraw — output fell back to a non-editable embedded image`);
  process.exit(1);
}

applyStyle(full, parseFills(source));
pinEdgeLabels(full);
full = stabilize(full);

const scene = { type: "excalidraw", version: 2, source: "mmd2excalidraw.mjs", elements: full, files: files ?? {} };
writeFileSync(outPath, JSON.stringify(scene, null, 2) + "\n");
const counts = full.reduce((m, e) => ((m[e.type] = (m[e.type] ?? 0) + 1), m), {});
console.log(`${path.relative(process.cwd(), outPath)}: ${full.length} elements — ${JSON.stringify(counts)}`);
