"""CLI entry point for Research Analyser."""

import asyncio
import logging
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table as RichTable

from research_analyser.analyser import ResearchAnalyser
from research_analyser.comparison import (
    build_comparison_markdown,
    parse_external_review,
    parse_local_review,
)
from research_analyser.config import Config
from research_analyser.models import AnalysisOptions
from research_analyser.reviewer import interpret_score

console = Console()


def setup_logging(level: str = "INFO"):
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


@click.group()
@click.option("--config", "-c", default=None, help="Path to config file")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
@click.pass_context
def cli(ctx, config, verbose):
    """Research Analyser - AI-powered research paper analysis."""
    ctx.ensure_object(dict)
    ctx.obj["config"] = Config.load(config)
    setup_logging("DEBUG" if verbose else ctx.obj["config"].app.log_level)


@cli.command()
@click.argument("source")
@click.option("--output", "-o", default=None, help="Output directory")
@click.option("--diagrams/--no-diagrams", default=True, help="Generate diagrams")
@click.option("--review/--no-review", default=True, help="Generate review")
@click.option("--venue", default=None, help="Target venue (e.g., 'ICLR 2026')")
@click.option(
    "--diagram-type",
    "-d",
    multiple=True,
    default=["methodology"],
    help="Diagram types to generate",
)
@click.pass_context
def analyse(ctx, source, output, diagrams, review, venue, diagram_type):
    """Analyse a research paper (PDF file, URL, arXiv ID, or DOI)."""
    config = ctx.obj["config"]
    if output:
        config.app.output_dir = output

    options = AnalysisOptions(
        generate_diagrams=diagrams,
        generate_review=review,
        diagram_types=list(diagram_type),
    )

    analyser = ResearchAnalyser(config=config)

    with console.status("[bold green]Analysing paper..."):
        report = asyncio.run(
            analyser.analyse(source, options=options)
        )

    # Display results
    console.print(f"\n[bold green]Analysis Complete![/bold green]")
    console.print(f"Title: [bold]{report.extracted_content.title}[/bold]")
    console.print(f"Authors: {', '.join(report.extracted_content.authors)}")

    # Stats table
    table = RichTable(title="Extraction Summary")
    table.add_column("Metric", style="cyan")
    table.add_column("Count", style="green")
    table.add_row("Sections", str(len(report.extracted_content.sections)))
    table.add_row("Equations", str(len(report.extracted_content.equations)))
    table.add_row("Tables", str(len(report.extracted_content.tables)))
    table.add_row("Figures", str(len(report.extracted_content.figures)))
    table.add_row("References", str(len(report.extracted_content.references)))
    table.add_row("Diagrams Generated", str(len(report.diagrams)))
    console.print(table)

    # Review score
    if report.review:
        score = report.review.overall_score
        decision = interpret_score(score)
        console.print(f"\n[bold]Review Score: {score:.1f}/10 ({decision})[/bold]")

    console.print(f"\nOutput saved to: [blue]{config.app.output_dir}[/blue]")


@cli.command()
@click.argument("source")
@click.option("--output", "-o", default=None, help="Output directory")
@click.option(
    "--type",
    "-t",
    "diagram_types",
    multiple=True,
    default=["methodology"],
    help="Diagram types",
)
@click.pass_context
def diagrams(ctx, source, output, diagram_types):
    """Generate diagrams only from a paper."""
    config = ctx.obj["config"]
    if output:
        config.app.output_dir = output

    options = AnalysisOptions(
        generate_diagrams=True,
        generate_review=False,
        diagram_types=list(diagram_types),
    )

    analyser = ResearchAnalyser(config=config)

    with console.status("[bold green]Generating diagrams..."):
        report = asyncio.run(analyser.analyse(source, options=options))

    console.print(f"[bold green]Generated {len(report.diagrams)} diagram(s)[/bold green]")
    for d in report.diagrams:
        console.print(f"  - {d.diagram_type}: {d.image_path}")


@cli.command()
@click.argument("source")
@click.option("--venue", default=None, help="Target venue")
@click.option("--output", "-o", default=None, help="Output directory")
@click.pass_context
def review(ctx, source, venue, output):
    """Generate peer review only for a paper."""
    config = ctx.obj["config"]
    if output:
        config.app.output_dir = output

    options = AnalysisOptions(
        generate_diagrams=False,
        generate_review=True,
    )

    analyser = ResearchAnalyser(config=config)

    with console.status("[bold green]Generating review..."):
        report = asyncio.run(analyser.analyse(source, options=options))

    if report.review:
        score = report.review.overall_score
        decision = interpret_score(score)
        console.print(f"\n[bold]Review Score: {score:.1f}/10 ({decision})[/bold]")
        console.print(f"\nStrengths:")
        for s in report.review.strengths:
            console.print(f"  + {s}")
        console.print(f"\nWeaknesses:")
        for w in report.review.weaknesses:
            console.print(f"  - {w}")


@cli.command("compare")
@click.argument("external_review_file")
@click.option(
    "--our-output",
    default="./output",
    help="Directory with local outputs (metadata.json/spec_output.md)",
)
@click.option(
    "--save",
    default="./output/review_comparison.md",
    help="Path to save comparison markdown",
)
def compare_reviews(external_review_file, our_output, save):
    """Compare local review results with an external review file."""
    external_path = Path(external_review_file)
    if not external_path.exists():
        console.print(f"[red]External review file not found:[/red] {external_review_file}")
        sys.exit(1)

    local = parse_local_review(Path(our_output))
    external = parse_external_review(external_path)
    markdown = build_comparison_markdown(local, external)

    save_path = Path(save)
    save_path.parent.mkdir(parents=True, exist_ok=True)
    save_path.write_text(markdown, encoding="utf-8")

    console.print("[bold green]Comparison generated[/bold green]")
    console.print(f"Saved to: [blue]{save_path}[/blue]")
    console.print()
    if local.overall_score is not None:
        console.print(f"Local overall: {local.overall_score:.2f} ({interpret_score(local.overall_score)})")
    else:
        console.print("Local overall: n/a")

    if external.overall_score is not None:
        console.print(f"External overall: {external.overall_score:.2f} ({interpret_score(external.overall_score)})")
    else:
        console.print("External overall: n/a")


if __name__ == "__main__":
    cli()
