"""Generate a PaperBanana diagram from a plain text file."""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

from research_analyser.diagram_generator import DiagramGenerator
from research_analyser.models import ExtractedContent


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate one diagram from a text file using PaperBanana.",
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Path to a UTF-8 .txt file.",
    )
    parser.add_argument(
        "--diagram-type",
        default="methodology",
        choices=["methodology", "architecture", "results"],
        help="Diagram type to generate (default: methodology).",
    )
    parser.add_argument(
        "--title",
        default="PaperBanana Text Input",
        help="Title used for diagram context.",
    )
    parser.add_argument(
        "--output-dir",
        default="output/paperbanana_text",
        help="Output directory for generated files.",
    )
    parser.add_argument(
        "--skip-ssl",
        action="store_true",
        help="Set SKIP_SSL_VERIFICATION=true and PYTHONHTTPSVERIFY=0.",
    )
    parser.add_argument(
        "--vlm-model",
        default="gemini-2.0-flash",
        help="VLM model name.",
    )
    parser.add_argument(
        "--image-model",
        default="gemini-3-pro-image-preview",
        help="Image model name.",
    )
    parser.add_argument(
        "--iterations",
        "--iteration",
        type=int,
        default=3,
        help="Max PaperBanana refinement iterations (default: 3).",
    )
    parser.add_argument(
        "--google-api-key",
        default="",
        help="Google API key for PaperBanana/Gemini (sets GOOGLE_API_KEY).",
    )
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    if not input_path.exists() or not input_path.is_file():
        print(f"ERROR: Input file not found: {input_path}")
        return 1

    text = input_path.read_text(encoding="utf-8").strip()
    if not text:
        print("ERROR: Input text file is empty.")
        return 1

    if args.skip_ssl:
        os.environ["SKIP_SSL_VERIFICATION"] = "true"
        os.environ["PYTHONHTTPSVERIFY"] = "0"

    if args.google_api_key:
        os.environ["GOOGLE_API_KEY"] = args.google_api_key

    content = ExtractedContent(
        full_text=text,
        title=args.title,
        authors=["User Input"],
        abstract=text[:1000],
        sections=[],
        equations=[],
        tables=[],
        figures=[],
        references=[],
    )

    generator = DiagramGenerator(
        provider="gemini",
        vlm_model=args.vlm_model,
        image_model=args.image_model,
        output_dir=args.output_dir,
        skip_ssl_verification=args.skip_ssl,
        max_iterations=args.iterations,
    )

    diagrams = await generator.generate(content, [args.diagram_type])
    if not diagrams:
        print("ERROR: No diagram generated.")
        return 1

    d = diagrams[0]
    print(f"DIAGRAM_PATH={d.image_path}")
    print(f"IS_FALLBACK={d.is_fallback}")
    if d.error:
        print(f"ERROR_DETAIL={d.error}")
    return 0


def main() -> None:
    args = _parse_args()
    code = asyncio.run(_run(args))
    raise SystemExit(code)


if __name__ == "__main__":
    main()
