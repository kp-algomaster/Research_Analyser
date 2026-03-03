import { Equation, EquationIndex, EquationRef } from "../types";

// Greek letter names recognised as symbols
const GREEK = new Set([
  "alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta",
  "iota", "kappa", "lambda", "mu", "nu", "xi", "pi", "rho", "sigma",
  "tau", "upsilon", "phi", "chi", "psi", "omega",
  "Alpha", "Beta", "Gamma", "Delta", "Epsilon", "Zeta", "Eta", "Theta",
  "Iota", "Kappa", "Lambda", "Mu", "Nu", "Xi", "Pi", "Rho", "Sigma",
  "Tau", "Upsilon", "Phi", "Chi", "Psi", "Omega",
]);

// Patterns for symbol extraction
const PATTERNS = [
  /\\([a-zA-Z]+)/g,              // \alpha, \mathcal{L}
  /\b([a-zA-Z][a-zA-Z0-9]*(?:[_^][a-zA-Z0-9{}]+)+)/g, // subscript / superscript: W_q, x_{t}
  /\b([a-zA-Z])\b/g,            // single-char variables
];

function extractSymbols(latex: string): Set<string> {
  const symbols = new Set<string>();
  for (const pattern of PATTERNS) {
    const re = new RegExp(pattern.source, pattern.flags);
    let m: RegExpExecArray | null;
    while ((m = re.exec(latex)) !== null) {
      const sym = m[1];
      if (sym && sym.length > 0 && sym !== "cdot" && sym !== "frac" && sym !== "sum") {
        symbols.add(sym);
        symbols.add(sym.toLowerCase());
        // Also add camelCase splits: W_q → W, q
        if (sym.includes("_")) {
          sym.split("_").filter(Boolean).forEach((p) => symbols.add(p));
        }
        if (sym.includes("^")) {
          sym.split("^").filter(Boolean).forEach((p) => symbols.add(p));
        }
      }
    }
  }
  // Add Greek names directly
  for (const g of GREEK) {
    if (latex.includes(g) || latex.includes("\\" + g)) {
      symbols.add(g);
    }
  }
  return symbols;
}

export function buildSymbolIndex(equations: Equation[], refs: EquationRef[]): EquationIndex {
  const bySymbol = new Map<string, EquationRef[]>();
  const byId = new Map<string, Equation>();

  for (const eq of equations) {
    byId.set(eq.id, eq);
  }

  for (const ref of refs) {
    const eq = byId.get(ref.equationId);
    if (!eq) { continue; }
    const symbols = extractSymbols(eq.latex);
    for (const sym of symbols) {
      if (!bySymbol.has(sym)) {
        bySymbol.set(sym, []);
      }
      bySymbol.get(sym)!.push(ref);
    }
  }

  return { bySymbol, byId };
}
