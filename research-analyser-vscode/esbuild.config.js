// @ts-check
const esbuild = require("esbuild");
const path = require("path");

const watch = process.argv.includes("--watch");

const baseConfig = {
  bundle: true,
  minify: false,
  sourcemap: true,
  external: ["vscode"],
};

/** @type {esbuild.BuildOptions} */
const extensionConfig = {
  ...baseConfig,
  entryPoints: ["src/extension.ts"],
  outfile: "out/extension.js",
  platform: "node",
  target: "node20",
  format: "cjs",
};

/** @type {esbuild.BuildOptions} */
const webviewConfig = {
  ...baseConfig,
  entryPoints: ["src/webview/panel.ts"],
  outfile: "out/webview/panel.js",
  platform: "browser",
  target: "es2020",
  format: "iife",
  external: [],
};

async function main() {
  if (watch) {
    const [extCtx, webCtx] = await Promise.all([
      esbuild.context(extensionConfig),
      esbuild.context(webviewConfig),
    ]);
    await Promise.all([extCtx.watch(), webCtx.watch()]);
    console.log("Watching for changes…");
  } else {
    await Promise.all([
      esbuild.build(extensionConfig),
      esbuild.build(webviewConfig),
    ]);
    console.log("Build complete.");
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
