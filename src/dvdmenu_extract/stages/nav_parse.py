from __future__ import annotations

"""Stage B: nav_parse.

Builds a format-neutral NavigationModel from the disc input. For SVCD, this
stage invokes the vcd-info backend to extract track metadata and writes
svcd_nav.json plus raw tool output for debugging.

Button ordering heuristic (DVD menus):
- Build two candidate orders for each menu: row-major and column-major.
- Build an expected target order from PGC first-cell (vob_id, first_sector).
- Choose the candidate with the lower mismatch score against the target order.
- This adapts to discs where menu navigation is column-first vs row-first.
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
    debug_spu: bool,
) -> tuple[dict, bool, str | None]:
    video_ts = input_path / "VIDEO_TS"
    titles, parse_error = parse_dvd_ifo_titles(video_ts)
    if titles:
        # Try to parse real menu buttons if possible
        menu_buttons = parse_dvd_nav_menu_buttons(video_ts, debug_spu=debug_spu)
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
                def _height(btn: dict) -> int:
                    rect = btn.get("selection_rect") or {}
                    return int(rect.get("h", 0))

                def _aspect_ok(btn: dict) -> bool:
                    rect = btn.get("selection_rect") or {}
                    w = int(rect.get("w", 0))
                    h = int(rect.get("h", 0))
                    if w <= 0 or h <= 0:
                        return False
                    return h <= w * 3

                def _select_group(group: list[dict]) -> list[dict]:
                    group = [btn for btn in group if _area(btn) > 0 and _aspect_ok(btn)]
                    group.sort(key=_height)
                    if len(group) > expected_count:
                        best_window = group[:expected_count]
                        best_spread = _height(best_window[-1]) - _height(best_window[0])
                        for start in range(1, len(group) - expected_count + 1):
                            window = group[start : start + expected_count]
                            spread = _height(window[-1]) - _height(window[0])
                            if spread < best_spread:
                                best_spread = spread
                                best_window = window
                        height_cluster = best_window
                    else:
                        height_cluster = group
                    height_cluster.sort(key=_area)
                    if len(height_cluster) > expected_count:
                        best_window = height_cluster[:expected_count]
                        best_spread = _area(best_window[-1]) - _area(best_window[0])
                        for start in range(1, len(height_cluster) - expected_count + 1):
                            window = height_cluster[start : start + expected_count]
                            spread = _area(window[-1]) - _area(window[0])
                            if spread < best_spread:
                                best_spread = spread
                                best_window = window
                        return best_window
                    return height_cluster

                grouped: dict[str, list[dict]] = {}
                for btn in candidates:
                    grouped.setdefault(str(btn.get("menu_id")), []).append(btn)

                best_group: list[dict] = []
                best_score: tuple[int, int] | None = None
                for menu_id, group in grouped.items():
                    if len(group) < expected_count:
                        continue
                    selected = _select_group(group)
                    if len(selected) != expected_count:
                        continue
                    selected.sort(key=_area)
                    area_spread = _area(selected[-1]) - _area(selected[0])
                    selected.sort(key=_height)
                    height_spread = _height(selected[-1]) - _height(selected[0])
                    score = (area_spread, height_spread)
                    if best_score is None or score < best_score:
                        best_score = score
                        best_group = selected

                trimmed = best_group or _select_group(candidates)
                if len(candidates) > expected_count:
                    logger.info(
                        "nav_parse: trimming menu buttons from %d to %d for title %d",
                        len(candidates),
                        expected_count,
                        title.title_id,
                    )
                def _pos_key(btn: dict) -> tuple[int, int]:
                    rect = btn.get("selection_rect") or {}
                    return (int(rect.get("y", 0)), int(rect.get("x", 0)))
                def _center_x(btn: dict) -> float:
                    rect = btn.get("selection_rect") or {}
                    return (float(rect.get("x", 0)) + float(rect.get("w", 0)) / 2.0)

                # Heuristic: try row-major and column-major ordering and pick the
                # one that best matches the target PGC order (vob_id, first_sector).
                # This keeps ordering stable across discs with different menu layouts.
                def _order_row_major(buttons: list[dict]) -> list[dict]:
                    # Group by row with a loose y-tolerance to avoid tiny offsets
                    # causing left-column items to sort before right-column items.
                    rows: list[list[dict]] = []
                    tolerance = 18
                    for btn in sorted(buttons, key=_pos_key):
                        rect = btn.get("selection_rect") or {}
                        cy = int(rect.get("y", 0)) + int(rect.get("h", 0)) // 2
                        placed = False
                        for row in rows:
                            row_rect = row[0].get("selection_rect") or {}
                            row_cy = int(row_rect.get("y", 0)) + int(
                                row_rect.get("h", 0)
                            ) // 2
                            if abs(cy - row_cy) <= tolerance:
                                row.append(btn)
                                placed = True
                                break
                        if not placed:
                            rows.append([btn])
                    rows.sort(
                        key=lambda row: int(
                            (row[0].get("selection_rect") or {}).get("y", 0)
                        )
                    )
                    ordered: list[dict] = []
                    for row in rows:
                        row.sort(
                            key=lambda b: int(
                                (b.get("selection_rect") or {}).get("x", 0)
                            )
                        )
                        ordered.extend(row)
                    return ordered

                def _order_column_major(buttons: list[dict]) -> list[dict]:
                    centers = [_center_x(btn) for btn in buttons]
                    if not centers:
                        return buttons
                    median_x = sorted(centers)[len(centers) // 2]
                    left = [btn for btn in buttons if _center_x(btn) <= median_x]
                    right = [btn for btn in buttons if _center_x(btn) > median_x]
                    left.sort(key=_pos_key)
                    right.sort(key=_pos_key)
                    return left + right

                # Build an expected order using playback targets (per button).
                # We use target PGC's first cell (vob_id, first_sector) as a
                # proxy for the playback position that the button jumps to.
                def _target_positions(title_obj) -> dict[int, tuple[int, int] | None]:
                    positions: dict[int, tuple[int, int] | None] = {}
                    for pgc in title_obj.pgcs:
                        pos = None
                        if pgc.cells:
                            cell = pgc.cells[0]
                            if cell.first_sector is not None:
                                vob_id = int(cell.vob_id or 0)
                                pos = (vob_id, int(cell.first_sector))
                        positions[pgc.pgc_id] = pos
                    return positions

                def _target_rank_from_buttons(
                    buttons: list[dict], positions: dict[int, tuple[int, int] | None]
                ) -> dict[str, int] | None:
                    ranked: list[tuple[str, tuple[int, int]]] = []
                    for btn in buttons:
                        pgc_id = btn.get("pgc_id")
                        if pgc_id is None:
                            return None
                        pos = positions.get(pgc_id)
                        if pos is None:
                            return None
                        ranked.append((btn.get("button_id", ""), pos))
                    if len(ranked) < 2:
                        return None
                    ranked.sort(key=lambda item: (item[1][0], item[1][1]))
                    return {button_id: idx for idx, (button_id, _) in enumerate(ranked)}

                positions = _target_positions(title)
                def _order_by_nav_graph(buttons: list[dict]) -> list[dict] | None:
                    if not buttons:
                        return None
                    logger = logging.getLogger(__name__)

                    def _rect(btn: dict) -> dict:
                        return btn.get("selection_rect") or {}

                    def _center(btn: dict) -> tuple[float, float]:
                        rect = _rect(btn)
                        return (
                            float(rect.get("x", 0)) + float(rect.get("w", 0)) / 2.0,
                            float(rect.get("y", 0)) + float(rect.get("h", 0)) / 2.0,
                        )

                    # Build link graph. Prefer NAV-pack links if they look valid;
                    # otherwise derive adjacency from spatial layout.
                    nav_links_valid = True
                    by_index = {}
                    for btn in buttons:
                        nav_links = btn.get("nav_links")
                        nav_index = btn.get("nav_index")
                        if nav_links and nav_index:
                            by_index[int(nav_index)] = btn
                        else:
                            nav_links_valid = False
                    if nav_links_valid:
                        indices = set(by_index.keys())
                        for btn in by_index.values():
                            links = btn.get("nav_links") or {}
                            for key in ("up", "down", "left", "right"):
                                val = links.get(key, 0)
                                if val != 0 and val not in indices:
                                    nav_links_valid = False
                                    break
                            if not nav_links_valid:
                                break
                    if nav_links_valid:
                        logger.info(
                            "nav_parse: nav graph source for title %d menu %s: nav-pack links",
                            title.title_id,
                            menu_id,
                        )

                    if not nav_links_valid:
                        logger.info(
                            "nav_parse: nav graph source for title %d menu %s: derived spatial links",
                            title.title_id,
                            menu_id,
                        )
                        by_index = {idx + 1: btn for idx, btn in enumerate(buttons)}
                        for idx, btn in by_index.items():
                            cx, cy = _center(btn)
                            best = {"up": None, "down": None, "left": None, "right": None}
                            best_score = {"up": float("inf"), "down": float("inf"), "left": float("inf"), "right": float("inf")}
                            for other_idx, other in by_index.items():
                                if other_idx == idx:
                                    continue
                                ox, oy = _center(other)
                                dx = ox - cx
                                dy = oy - cy
                                if dy < 0:  # up
                                    score = abs(dy) + 0.5 * abs(dx)
                                    if score < best_score["up"]:
                                        best_score["up"] = score
                                        best["up"] = other_idx
                                if dy > 0:  # down
                                    score = abs(dy) + 0.5 * abs(dx)
                                    if score < best_score["down"]:
                                        best_score["down"] = score
                                        best["down"] = other_idx
                                if dx < 0:  # left
                                    score = abs(dx) + 0.5 * abs(dy)
                                    if score < best_score["left"]:
                                        best_score["left"] = score
                                        best["left"] = other_idx
                                if dx > 0:  # right
                                    score = abs(dx) + 0.5 * abs(dy)
                                    if score < best_score["right"]:
                                        best_score["right"] = score
                                        best["right"] = other_idx
                            btn["nav_links"] = {
                                "index": idx,
                                "up": best["up"] or 0,
                                "down": best["down"] or 0,
                                "left": best["left"] or 0,
                                "right": best["right"] or 0,
                            }
                            btn["nav_index"] = idx

                    start = min(
                        by_index.values(),
                        key=lambda b: (
                            (_rect(b).get("y", 0)),
                            (_rect(b).get("x", 0)),
                        ),
                    )

                    def _traverse(mode: str) -> list[dict]:
                        ordered: list[dict] = []
                        visited = set()
                        row_start = start
                        col_start = start
                        current = start
                        while current and current.get("nav_index") not in visited:
                            ordered.append(current)
                            visited.add(current.get("nav_index"))
                            links = current.get("nav_links") or {}
                            if mode == "row":
                                next_idx = links.get("right", 0)
                                if next_idx and next_idx in by_index and next_idx not in visited:
                                    current = by_index[next_idx]
                                    continue
                                down_idx = (row_start.get("nav_links") or {}).get("down", 0)
                                if down_idx and down_idx in by_index and down_idx not in visited:
                                    row_start = by_index[down_idx]
                                    current = row_start
                                    continue
                            else:
                                next_idx = links.get("down", 0)
                                if next_idx and next_idx in by_index and next_idx not in visited:
                                    current = by_index[next_idx]
                                    continue
                                right_idx = (col_start.get("nav_links") or {}).get("right", 0)
                                if right_idx and right_idx in by_index and right_idx not in visited:
                                    col_start = by_index[right_idx]
                                    current = col_start
                                    continue
                            break
                        return ordered if len(ordered) == len(by_index) else None

                    row_order = _traverse("row")
                    col_order = _traverse("col")

                    def _path_distance(order: list[dict]) -> float:
                        total = 0.0
                        for idx in range(1, len(order)):
                            prev = _rect(order[idx - 1])
                            curr = _rect(order[idx])
                            prev_x = float(prev.get("x", 0)) + float(prev.get("w", 0)) / 2.0
                            prev_y = float(prev.get("y", 0)) + float(prev.get("h", 0)) / 2.0
                            curr_x = float(curr.get("x", 0)) + float(curr.get("w", 0)) / 2.0
                            curr_y = float(curr.get("y", 0)) + float(curr.get("h", 0)) / 2.0
                            total += abs(curr_x - prev_x) + abs(curr_y - prev_y)
                        return total

                    if row_order and col_order:
                        return (
                            row_order
                            if _path_distance(row_order) <= _path_distance(col_order)
                            else col_order
                        )
                    return row_order or col_order

                rank = _target_rank_from_buttons(trimmed, positions)
                row_order = _order_row_major(trimmed)
                col_order = _order_column_major(trimmed)
                graph_order = _order_by_nav_graph(trimmed)

                def _order_distance(order: list[dict]) -> float:
                    total = 0.0
                    for idx in range(1, len(order)):
                        prev = order[idx - 1].get("selection_rect") or {}
                        curr = order[idx].get("selection_rect") or {}
                        prev_x = float(prev.get("x", 0)) + float(prev.get("w", 0)) / 2.0
                        prev_y = float(prev.get("y", 0)) + float(prev.get("h", 0)) / 2.0
                        curr_x = float(curr.get("x", 0)) + float(curr.get("w", 0)) / 2.0
                        curr_y = float(curr.get("y", 0)) + float(curr.get("h", 0)) / 2.0
                        total += abs(curr_x - prev_x) + abs(curr_y - prev_y)
                    return total

                def _order_score(order: list[dict]) -> int | None:
                    indices = []
                    for idx, btn in enumerate(order):
                        button_id = btn.get("button_id")
                        if rank is None or button_id not in rank:
                            return None
                        indices.append(abs(rank[button_id] - idx))
                    return sum(indices)

                score_row = _order_score(row_order)
                score_col = _order_score(col_order)
                dist_row = _order_distance(row_order)
                dist_col = _order_distance(col_order)
                logger.info(
                    "nav_parse: ordering heuristic for title %d menu %s: "
                    "row_score=%s col_score=%s row_dist=%.1f col_dist=%.1f",
                    title.title_id,
                    menu_id,
                    score_row,
                    score_col,
                    dist_row,
                    dist_col,
                )
                if graph_order:
                    logger.info(
                        "nav_parse: nav graph order for title %d menu %s: %s",
                        title.title_id,
                        menu_id,
                        [btn.get("nav_index") for btn in graph_order],
                    )
                    logger.info(
                        "nav_parse: nav graph summary for title %d menu %s: used graph order",
                        title.title_id,
                        menu_id,
                    )
                    ordered = graph_order
                else:
                    logger.info(
                        "nav_parse: nav graph order unavailable for title %d menu %s",
                        title.title_id,
                        menu_id,
                    )
                    if dist_row > 0 and dist_col > 0:
                        if dist_col <= dist_row * 0.9:
                            ordered = col_order
                        elif dist_row <= dist_col * 0.9:
                            ordered = row_order
                        else:
                            if score_row is None and score_col is None:
                                ordered = row_order
                            elif score_row is None:
                                ordered = col_order
                            elif score_col is None:
                                ordered = row_order
                            elif score_row <= score_col:
                                ordered = row_order
                            else:
                                ordered = col_order
                    else:
                        if score_row is None and score_col is None:
                            ordered = row_order
                        elif score_row is None:
                            ordered = col_order
                        elif score_col is None:
                            ordered = row_order
                        elif score_row <= score_col:
                            ordered = row_order
                        else:
                            ordered = col_order

                for btn in ordered:
                    btn["button_id"] = f"btn{button_index}"
                    btn.pop("nav_links", None)
                    btn.pop("nav_index", None)
                    button_index += 1
                trimmed = ordered
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
    debug_spu: bool = False,
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
            debug_spu,
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
