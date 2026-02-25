/**
 * CLI wrapper for beautiful-mermaid.
 *
 * Usage:
 *   echo "<mermaid code>" | node render.mjs [theme]
 *
 * Args:
 *   theme  — one of the 15 built-in theme names, or omitted for "github-dark"
 *
 * Writes SVG string to stdout.
 * Exits 1 on error, with error message on stderr.
 */

import { renderMermaidSVG, THEMES } from "beautiful-mermaid";

const theme = process.argv[2] || "github-dark";

// Read mermaid code from stdin
const chunks = [];
for await (const chunk of process.stdin) {
  chunks.push(chunk);
}
const code = Buffer.concat(chunks).toString("utf8").trim();

if (!code) {
  process.stderr.write("Error: empty input\n");
  process.exit(1);
}

const themeOpts = THEMES[theme] ?? THEMES["github-dark"];

try {
  const svg = renderMermaidSVG(code, themeOpts);
  process.stdout.write(svg);
} catch (err) {
  process.stderr.write(`Error: ${err.message}\n`);
  process.exit(1);
}
