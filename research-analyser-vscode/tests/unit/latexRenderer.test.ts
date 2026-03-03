import * as assert from "assert";
import { renderToString, renderInline } from "../../src/util/latexRenderer";

suite("latexRenderer", () => {
  test("renderToString returns HTML string", () => {
    const result = renderToString("\\alpha + \\beta");
    assert.ok(typeof result === "string");
    assert.ok(result.length > 0);
    assert.ok(result.includes("<span") || result.includes("<math") || result.includes("katex"));
  });

  test("renderToString handles invalid latex gracefully", () => {
    const result = renderToString("\\invalidcommandXYZ{{{");
    assert.ok(typeof result === "string");
    assert.ok(result.length > 0);
  });

  test("renderInline returns HTML string", () => {
    const result = renderInline("x^2");
    assert.ok(typeof result === "string");
    assert.ok(result.length > 0);
  });

  test("renderToString with empty string does not throw", () => {
    assert.doesNotThrow(() => renderToString(""));
  });
});
