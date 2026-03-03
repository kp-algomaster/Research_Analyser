import katex from "katex";

export function renderToString(latex: string): string {
  try {
    return katex.renderToString(latex.trim(), {
      output: "html",
      throwOnError: false,
      displayMode: true,
    });
  } catch {
    return `<code>${latex}</code>`;
  }
}

export function renderInline(latex: string): string {
  try {
    return katex.renderToString(latex.trim(), {
      output: "html",
      throwOnError: false,
      displayMode: false,
    });
  } catch {
    return `<code>${latex}</code>`;
  }
}
