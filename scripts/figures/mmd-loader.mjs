// mmd-loader.mjs — shims so @excalidraw/excalidraw (bundler-built) runs in Node:
// 1. .json imports get `type: "json"` attributes (open-color)
// 2. extensionless subpath imports resolve with .js (roughjs)
// 3. CJS @excalidraw/laser-pointer gets a named-export wrapper
// 4. patches mermaid-to-excalidraw subgraph lookup for mermaid v11.12 render-id
//    prefixed SVG ids (upstream bug: queries bare id, SVG has prefixed id)
import path from "node:path";
import { fileURLToPath } from "node:url";

const laserWrapper = `
import lp from "laser-pointer-cjs";
export const LaserPointer = lp.LaserPointer;
export default lp;
`;

export function resolve(specifier, context, next) {
  if (specifier === "@excalidraw/laser-pointer") {
    return { url: "laser-pointer-wrapper:", format: "module", shortCircuit: true };
  }
  if (specifier === "laser-pointer-cjs") {
    const p = path.join(path.dirname(fileURLToPath(import.meta.url)), "../../node_modules/@excalidraw/laser-pointer/dist/cjs.js");
    return { url: `file://${p}`, format: "commonjs", shortCircuit: true };
  }
  try {
    const r = next(specifier, context);
    if (r.url.endsWith(".json")) return { ...r, importAttributes: { type: "json" } };
    return r;
  } catch (err) {
    if (err?.code === "ERR_MODULE_NOT_FOUND" && !specifier.endsWith(".js") && !specifier.endsWith(".json")) {
      return next(specifier + ".js", context);
    }
    throw err;
  }
}

const SUBGRAPH_OLD = "querySelector(`[id='${data.id}']`)";
const SUBGRAPH_NEW = "querySelector(`[id$='-${data.id}']`)";

export function load(url, context, next) {
  if (url === "laser-pointer-wrapper:") {
    return { format: "module", source: laserWrapper, shortCircuit: true };
  }
  if (url.includes("mermaid-to-excalidraw/dist/parser/flowchart.js")) {
    const r = next(url, context);
    const src = r.source.toString();
    if (!src.includes(SUBGRAPH_OLD)) {
      throw new Error(`mmd-loader: subgraph patch target not found in ${url}`);
    }
    return { ...r, source: src.split(SUBGRAPH_OLD).join(SUBGRAPH_NEW), shortCircuit: true };
  }
  return next(url, context);
}
