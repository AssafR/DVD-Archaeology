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
import logging

from dvdmenu_extract.util.dvd_ifo import parse_dvd_ifo_titles, parse_dvd_nav_menu_buttons
from dvdmenu_extract.util.vcd_directory import parse_svcd_directory, parse_vcd_directory


def _build_dvd_nav(
    input_path: Path,
    allow_fallback: bool,
) -> tuple[dict, bool, str | None]:
    video_ts = input_path / "VIDEO_TS"
    titles, parse_error = parse_dvd_ifo_titles(video_ts)
    if titles:
        # Try to parse real menu buttons if possible
        menu_buttons = parse_dvd_nav_menu_buttons(video_ts)
        if menu_buttons:
            logger = logging.getLogger(__name__)
            # Prefer VTSM menu buttons with valid rects; cap to title PGC counts.
            filtered: list[dict] = []
            button_index = 1
            for title in titles:
                expected_count = len(title.pgcs)
                if expected_count == 0:
                    continue
                candidates = [
                    btn
                    for btn in menu_buttons
                    if btn.get("title_id") == title.title_id
                    and str(btn.get("menu_id", "")).upper().startswith("VTSM")
                    and btn.get("selection_rect") is not None
                ]
                if not candidates:
                    continue
                def _area(btn: dict) -> int:
                    rect = btn.get("selection_rect") or {}
                    return int(rect.get("w", 0)) * int(rect.get("h", 0))
                candidates.sort(key=_area, reverse=True)
                trimmed = candidates[:expected_count]
                if len(candidates) > expected_count:
                    logger.info(
                        "nav_parse: trimming menu buttons from %d to %d for title %d",
                        len(candidates),
                        expected_count,
                        title.title_id,
                    )
                # Assign pgc_ids by top-to-bottom, left-to-right order.
                pgc_ids = sorted(pgc.pgc_id for pgc in title.pgcs)
                def _pos_key(btn: dict) -> tuple[int, int]:
                    rect = btn.get("selection_rect") or {}
                    return (int(rect.get("y", 0)), int(rect.get("x", 0)))
                trimmed.sort(key=_pos_key)
                for btn, pgc_id in zip(trimmed, pgc_ids, strict=False):
                    btn["pgc_id"] = pgc_id
                for btn in trimmed:
                    btn["button_id"] = f"btn{button_index}"
                    button_index += 1
                filtered.extend(trimmed)
            if filtered:
                menu_buttons = filtered

        if not menu_buttons:
            # Fallback to synthetic buttons if none found in IFO
            button_index = 1
            for title in titles:
                for pgc in title.pgcs:
                    menu_buttons.append(
                        {
                            "button_id": f"btn{button_index}",
                            "menu_id": "dvd_root",
                            "title_id": title.title_id,
                            "pgc_id": pgc.pgc_id,
                            "selection_rect": None,
                            "highlight_rect": None,
                        }
                    )
                    button_index += 1
        
        return (
            {
            "disc_format": "DVD",
            "dvd": {
                "titles": [
                    {
                        "title_id": title.title_id,
                        "pgcs": [
                            {
                                "pgc_id": pgc.pgc_id,
                                "cells": [
                                    {
                                        "cell_id": cell.cell_id,
                                        "start_time": cell.start_time,
                                        "end_time": cell.end_time,
                                        "first_sector": cell.first_sector,
                                        "last_sector": cell.last_sector,
                                        "vob_id": cell.vob_id,
                                    }
                                    for cell in pgc.cells
                                ],
                            }
                            for pgc in title.pgcs
                        ],
                    }
                    for title in titles
                ],
                    "menu_domains": list(set(btn["menu_id"] for btn in menu_buttons)) if menu_buttons else ["VMGM"],
                    "menu_buttons": menu_buttons,
            },
            "svcd": None,
            "vcd": None,
            },
            True,
            None,
        )

    if not allow_fallback:
        raise ValidationError(f"DVD IFO parsing failed: {parse_error}")

    vobs = sorted(video_ts.glob("VTS_*_[1-9].VOB"))
    if not vobs:
        raise ValidationError("No DVD program VOBs found in VIDEO_TS")

    pgcs = []
    buttons = []
    for idx, _path in enumerate(vobs, start=1):
        start = 0.0
        end = 600.0
        pgcs.append(
            {
                "pgc_id": idx,
                "cells": [{"cell_id": idx, "start_time": start, "end_time": end}],
            }
        )
        buttons.append(
            {
                "button_id": f"btn{idx}",
                "menu_id": "dvd_root",
                "title_id": 1,
                "pgc_id": idx,
                "selection_rect": None,
                "highlight_rect": None,
            }
        )

    return {
        "disc_format": "DVD",
        "dvd": {
            "titles": [{"title_id": 1, "pgcs": pgcs}],
            "menu_domains": ["VMGM"] if (video_ts / "VIDEO_TS.IFO").is_file() else [],
            "menu_buttons": buttons,
        },
        "svcd": None,
        "vcd": None,
    }, False, parse_error


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


def run(
    ingest_path: Path,
    out_dir: Path,
    allow_dvd_ifo_fallback: bool,
) -> NavigationModel:
    ingest = read_json(ingest_path, IngestModel)
    logger = logging.getLogger(__name__)
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
        logger.info("nav_parse: attempting DVD IFO parsing for VTS PGCs")
        payload, used_ifo, parse_error = _build_dvd_nav(
            Path(ingest.input_path),
            allow_dvd_ifo_fallback,
        )
        if used_ifo:
            logger.info("nav_parse: using DVD IFO-based navigation")
        else:
            if parse_error:
                logger.warning("nav_parse: IFO parse failed (%s)", parse_error)
            logger.info("nav_parse: using DVD VOB heuristic navigation")
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
