from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import typer

from dvdmenu_extract.pipeline import PipelineOptions, STAGES, run_pipeline
from dvdmenu_extract.util.assertx import ValidationError
from dvdmenu_extract.util.logging import IndentFilter

app = typer.Typer(add_completion=False)


@app.command()
def main(
    input_path: Optional[Path] = typer.Argument(
        None, exists=True, file_okay=False, dir_okay=True
    ),
    out: Optional[Path] = typer.Option(None, "--out", dir_okay=True, file_okay=False),
    ocr_lang: str = typer.Option("eng+heb", "--ocr-lang"),
    use_stub_ocr: bool = typer.Option(False, "--use-stub-ocr"),
    use_real_ffmpeg: bool = typer.Option(False, "--use-real-ffmpeg"),
    repair: str = typer.Option(
        "off",
        "--repair",
        help="Error resilience mode: off (no repair), safe (moderate error handling), aggressive (maximum resilience, may be slow)",
    ),
    stage: Optional[str] = typer.Option(None, "--stage"),
    until: Optional[str] = typer.Option(None, "--until"),
    from_stage: Optional[str] = typer.Option(None, "--from"),
    force: bool = typer.Option(False, "--force"),
    overwrite_outputs: bool = typer.Option(False, "--overwrite-outputs"),
    use_reference_images: bool = typer.Option(False, "--use-reference-images"),
    use_reference_guidance: bool = typer.Option(False, "--use-reference-guide"),
    list_stages: bool = typer.Option(False, "--list-stages"),
    json_out_root: bool = typer.Option(False, "--json-out-root"),
    json_root_dir: bool = typer.Option(False, "--json-root-dir"),
    use_real_timing: bool = typer.Option(False, "--use-real-timing"),
    allow_dvd_ifo_fallback: bool = typer.Option(False, "--allow-dvd-ifo-fallback"),
    debug_spu: bool = typer.Option(False, "--debug-spu"),
    ocr_reference_path: Optional[Path] = typer.Option(
        None, "--ocr-reference", dir_okay=False
    ),
) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        handler.addFilter(IndentFilter())
        handler.setFormatter(
            logging.Formatter("%(levelname)s %(indent)s%(message)s")
        )
    if list_stages:
        typer.echo("\n".join(STAGES))
        raise typer.Exit(code=0)

    if input_path is None or out is None:
        typer.echo("Error: input_path and --out are required unless --list-stages")
        raise typer.Exit(code=2)
    if stage and until:
        typer.echo("Error: use --stage or --until, not both")
        raise typer.Exit(code=2)
    if stage and from_stage:
        typer.echo("Error: use --stage or --from, not both")
        raise typer.Exit(code=2)
    if until and from_stage:
        typer.echo("Error: use --until or --from, not both")
        raise typer.Exit(code=2)

    options = PipelineOptions(
        ocr_lang=ocr_lang,
        use_real_ocr=not use_stub_ocr,
        use_real_ffmpeg=use_real_ffmpeg,
        repair=repair,
        force=force,
        json_out_root=json_out_root,
        json_root_dir=json_root_dir,
        use_real_timing=use_real_timing,
        allow_dvd_ifo_fallback=allow_dvd_ifo_fallback,
        debug_spu=debug_spu,
        use_reference_images=use_reference_images,
        use_reference_guidance=use_reference_guidance,
        overwrite_outputs=overwrite_outputs,
        ocr_reference_path=str(ocr_reference_path)
        if ocr_reference_path is not None
        else None,
    )
    try:
        run_pipeline(
            input_path=input_path,
            out_dir=out,
            options=options,
            stage=stage,
            until=until,
            from_stage=from_stage,
        )
    except ValidationError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc


if __name__ == "__main__":
    app()
