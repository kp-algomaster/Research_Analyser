import asyncio
import os
from pathlib import Path

from research_analyser.diagram_generator import DiagramGenerator
from research_analyser.models import ExtractedContent, Section


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


async def main() -> None:
    load_env_file(Path(".env"))
    os.environ["SKIP_SSL_VERIFICATION"] = "true"
    os.environ["PYTHONHTTPSVERIFY"] = "0"

    content = ExtractedContent(
        full_text=(
            "We propose a transformer-based method with three stages: data preprocessing, "
            "multi-head attention encoding, and task-specific decoding. "
            "Experiments on benchmark datasets show improved F1 and accuracy."
        ),
        title="Local PaperBanana Smoke Test",
        authors=["Research Analyser"],
        abstract="A small synthetic abstract for local PaperBanana test.",
        sections=[
            Section(
                title="Method",
                content="Stage1 preprocess; Stage2 encode; Stage3 decode",
                level=1,
            )
        ],
        equations=[],
        tables=[],
        figures=[],
        references=[],
    )

    out_dir = Path("output") / "paperbanana_smoke"
    generator = DiagramGenerator(
        provider="gemini",
        vlm_model="gemini-2.0-flash",
        image_model="gemini-3-pro-image-preview",
        output_dir=str(out_dir),
        skip_ssl_verification=True,
    )

    diagrams = await generator.generate(content, ["methodology"])
    if not diagrams:
        print("SMOKE_RESULT=FAIL")
        print("REASON=No diagram returned")
        return

    diagram = diagrams[0]
    image_exists = Path(diagram.image_path).exists()
    status = "PASS" if (image_exists and not diagram.is_fallback) else "WARN"

    print(f"SMOKE_RESULT={status}")
    print(f"IS_FALLBACK={diagram.is_fallback}")
    print(f"IMAGE_EXISTS={image_exists}")
    print(f"IMAGE_PATH={diagram.image_path}")
    if diagram.error:
        print(f"ERROR={diagram.error}")


if __name__ == "__main__":
    asyncio.run(main())
