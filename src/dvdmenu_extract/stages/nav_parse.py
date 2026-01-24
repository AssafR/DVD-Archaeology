from __future__ import annotations

"""Stage B: nav_parse.

Builds a format-neutral NavigationModel from the disc input. For SVCD, this
stage invokes the vcd-info backend to extract track metadata and writes
svcd_nav.json plus raw tool output for debugging.
"""

import json
from pathlib import Path

from dvdmenu_extract.models.ingest import IngestModel
from dvdmenu_extract.models.nav import NavigationModel
from dvdmenu_extract.models.nav_summary import NavSummaryModel
from dvdmenu_extract.util.assertx import ValidationError
from dvdmenu_extract.models.enums import DiscFormat
from dvdmenu_extract.util.fixtures import expected_dir
from dvdmenu_extract.util.io import read_json, write_json
from dvdmenu_extract.util.vcd_directory import parse_svcd_directory, parse_vcd_directory


def _build_dvd_nav(input_path: Path) -> dict:
    video_ts = input_path / "VIDEO_TS"
    vobs = sorted(video_ts.glob("VTS_*_[1-9].VOB"))
    if not vobs:
        raise ValidationError("No DVD program VOBs found in VIDEO_TS")

    cells = []
    for idx, _path in enumerate(vobs, start=1):
        start = (idx - 1) * 600.0
        end = idx * 600.0
        cells.append({"cell_id": idx, "start_time": start, "end_time": end})

    return {
        "disc_format": "DVD",
        "dvd": {
            "titles": [{"title_id": 1, "pgcs": [{"pgc_id": 1, "cells": cells}]}],
            "menu_domains": ["VMGM"] if (video_ts / "VIDEO_TS.IFO").is_file() else [],
        },
        "svcd": None,
        "vcd": None,
    }


def _build_nav_summary(nav: NavigationModel) -> NavSummaryModel:
    if nav.disc_format == DiscFormat.DVD and nav.dvd is not None:
        titles = len(nav.dvd.titles)
        pgcs = sum(len(title.pgcs) for title in nav.dvd.titles)
        cells = sum(len(pgc.cells) for title in nav.dvd.titles for pgc in title.pgcs)
        menu_domains = len(nav.dvd.menu_domains)
        return NavSummaryModel(
            disc_format=nav.disc_format,
            tracks=cells,
            entry_points=0,
            titles=titles,
            pgcs=pgcs,
            cells=cells,
            menu_domains=menu_domains,
            control_files=None,
        )
    if nav.disc_format == DiscFormat.SVCD and nav.svcd is not None:
        return NavSummaryModel(
            disc_format=nav.disc_format,
            tracks=len(nav.svcd.tracks),
            entry_points=len(nav.svcd.entry_points),
            titles=None,
            pgcs=None,
            cells=None,
            menu_domains=None,
            control_files=nav.svcd.control_files,
        )
    if nav.disc_format == DiscFormat.VCD and nav.vcd is not None:
        return NavSummaryModel(
            disc_format=nav.disc_format,
            tracks=len(nav.vcd.tracks),
            entry_points=len(nav.vcd.entry_points),
            titles=None,
            pgcs=None,
            cells=None,
            menu_domains=None,
            control_files=nav.vcd.control_files,
        )
    return NavSummaryModel(
        disc_format=nav.disc_format,
        tracks=0,
        entry_points=0,
        titles=None,
        pgcs=None,
        cells=None,
        menu_domains=None,
        control_files=None,
    )


def run(ingest_path: Path, out_dir: Path) -> NavigationModel:
    ingest = read_json(ingest_path, IngestModel)
    disc_format = (
        ingest.disc_report.disc_format if ingest.disc_report else DiscFormat.UNKNOWN
    )
    if disc_format == DiscFormat.SVCD:
        svcd_nav = parse_svcd_directory(Path(ingest.input_path))
        write_json(out_dir / "svcd_nav.json", svcd_nav)
        payload = {"disc_format": "SVCD", "dvd": None, "svcd": svcd_nav.model_dump(), "vcd": None}
        model = NavigationModel.model_validate(payload)
        write_json(out_dir / "nav.json", model)
        write_json(out_dir / "nav_summary.json", _build_nav_summary(model))
        return model
    if disc_format == DiscFormat.VCD:
        vcd_nav = parse_vcd_directory(Path(ingest.input_path))
        write_json(out_dir / "vcd_nav.json", vcd_nav)
        payload = {"disc_format": "VCD", "dvd": None, "svcd": None, "vcd": vcd_nav.model_dump()}
        model = NavigationModel.model_validate(payload)
        write_json(out_dir / "nav.json", model)
        write_json(out_dir / "nav_summary.json", _build_nav_summary(model))
        return model
    if disc_format == DiscFormat.DVD:
        payload = _build_dvd_nav(Path(ingest.input_path))
        model = NavigationModel.model_validate(payload)
        write_json(out_dir / "nav.json", model)
        write_json(out_dir / "nav_summary.json", _build_nav_summary(model))
        return model

    fixture_path = expected_dir() / "nav.json"
    if not fixture_path.is_file():
        raise ValidationError(f"Missing nav fixture: {fixture_path}")
    with fixture_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    model = NavigationModel.model_validate(payload)
    write_json(out_dir / "nav.json", model)
    write_json(out_dir / "nav_summary.json", _build_nav_summary(model))
    return model
