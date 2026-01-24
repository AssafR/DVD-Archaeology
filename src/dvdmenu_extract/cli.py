from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import typer

from dvdmenu_extract.pipeline import PipelineOptions, STAGES, run_pipeline
from dvdmenu_extract.util.assertx import ValidationError

app = typer.Typer(add_completion=False)


@app.command()
def main(
    input_path: Optional[Path] = typer.Argument(
        None, exists=True, file_okay=False, dir_okay=True
    ),
    out: Optional[Path] = typer.Option(None, "--out", dir_okay=True, file_okay=False),
    ocr_lang: str = typer.Option("eng+heb", "--ocr-lang"),
    use_real_ocr: bool = typer.Option(False, "--use-real-ocr"),
    use_real_ffmpeg: bool = typer.Option(False, "--use-real-ffmpeg"),
    repair: str = typer.Option("off", "--repair"),
    stage: Optional[str] = typer.Option(None, "--stage"),
    until: Optional[str] = typer.Option(None, "--until"),
    force: bool = typer.Option(False, "--force"),
    list_stages: bool = typer.Option(False, "--list-stages"),
    json_out_root: bool = typer.Option(False, "--json-out-root"),
    json_root_dir: bool = typer.Option(False, "--json-root-dir"),
) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if list_stages:
        typer.echo("\n".join(STAGES))
        raise typer.Exit(code=0)

    if input_path is None or out is None:
        typer.echo("Error: input_path and --out are required unless --list-stages")
        raise typer.Exit(code=2)
    if stage and until:
        typer.echo("Error: use --stage or --until, not both")
        raise typer.Exit(code=2)

    options = PipelineOptions(
        ocr_lang=ocr_lang,
        use_real_ocr=use_real_ocr,
        use_real_ffmpeg=use_real_ffmpeg,
        repair=repair,
        force=force,
        json_out_root=json_out_root,
        json_root_dir=json_root_dir,
    )
    try:
        run_pipeline(
            input_path=input_path,
            out_dir=out,
            options=options,
            stage=stage,
            until=until,
        )
    except ValidationError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc


if __name__ == "__main__":
    app()
