import * as assert from "assert";
import { buildSymbolIndex } from "../../src/util/symbolIndex";
import { Equation, EquationRef } from "../../src/types";

suite("symbolIndex", () => {
  const equations: Equation[] = [
    {
      id: "eq-1",
      label: "Loss",
      latex: "\\mathcal{L} = \\lambda_1 \\mathcal{L}_{photo} + \\lambda_2 \\mathcal{L}_{smooth}",
      section: "3",
      is_inline: false,
      description: null,
    },
    {
      id: "eq-2",
      label: "Attention",
      latex: "\\text{Attention}(Q, K, V) = \\text{softmax}\\left(\\frac{QK^T}{\\sqrt{d_k}}\\right) V",
      section: "4",
      is_inline: false,
      description: null,
    },
    {
      id: "eq-3",
      label: null,
      latex: "\\alpha = 0.001",
      section: "5",
      is_inline: true,
      description: "learning rate",
    },
  ];

  const refs: EquationRef[] = equations.map((eq) => ({
    equationId: eq.id,
    latex: eq.latex,
    label: eq.label,
    section: eq.section,
    renderedHtml: `<span>${eq.latex}</span>`,
  }));

  test("builds index with byId map", () => {
    const idx = buildSymbolIndex(equations, refs);
    assert.ok(idx.byId.has("eq-1"));
    assert.ok(idx.byId.has("eq-2"));
    assert.ok(idx.byId.has("eq-3"));
    assert.strictEqual(idx.byId.size, 3);
  });

  test("greek letter alpha is indexed", () => {
    const idx = buildSymbolIndex(equations, refs);
    assert.ok(idx.bySymbol.has("alpha"), "should index \\alpha as 'alpha'");
  });

  test("returns undefined for unknown symbol", () => {
    const idx = buildSymbolIndex(equations, refs);
    assert.strictEqual(idx.bySymbol.get("unknownXYZ"), undefined);
  });

  test("equation lookup by id is correct", () => {
    const idx = buildSymbolIndex(equations, refs);
    const eq = idx.byId.get("eq-3");
    assert.strictEqual(eq?.label, null);
    assert.strictEqual(eq?.description, "learning rate");
  });
});
