from __future__ import annotations

"""Stage C2: menu_validation.

Validates alignment between navigation-derived menu buttons and menu_map
entries, producing a diagnostic JSON artifact and failing fast on mismatch.
"""

from pathlib import Path

from dvdmenu_extract.models.enums import DiscFormat
from dvdmenu_extract.models.menu import MenuMapModel
from dvdmenu_extract.models.menu_validation import (
    MenuValidationIssue,
    MenuValidationMenuCount,
    MenuValidationModel,
    MenuValidationTargetKindCount,
)
from dvdmenu_extract.models.nav import NavigationModel
from dvdmenu_extract.util.assertx import ValidationError
from dvdmenu_extract.util.io import read_json, write_json


def run(nav_path: Path, menu_map_path: Path, out_dir: Path) -> MenuValidationModel:
    nav = read_json(nav_path, NavigationModel)
    menu_map = read_json(menu_map_path, MenuMapModel)

    issues: list[MenuValidationIssue] = []
    menu_entry_ids = {entry.entry_id for entry in menu_map.entries}
    nav_button_ids: set[str] = set()
    menu_id_counts: dict[str, int] = {}
    nav_menu_id_counts: dict[str, int] = {}
    target_kind_counts: dict[str, int] = {}

    for entry in menu_map.entries:
        menu_id = entry.menu_id or "unknown"
        menu_id_counts[menu_id] = menu_id_counts.get(menu_id, 0) + 1
        target_kind_counts[entry.target.kind] = (
            target_kind_counts.get(entry.target.kind, 0) + 1
        )

    if nav.disc_format == DiscFormat.DVD and nav.dvd is not None:
        nav_button_ids = {button.button_id for button in nav.dvd.menu_buttons}
        for button in nav.dvd.menu_buttons:
            nav_menu_id_counts[button.menu_id] = (
                nav_menu_id_counts.get(button.menu_id, 0) + 1
            )

        missing_in_menu_map = sorted(nav_button_ids - menu_entry_ids)
        missing_in_nav = sorted(menu_entry_ids - nav_button_ids)
        if missing_in_menu_map:
            issues.append(
                MenuValidationIssue(
                    code="buttons_missing_in_menu_map",
                    message=f"Buttons missing in menu_map: {missing_in_menu_map}",
                )
            )
        if missing_in_nav:
            issues.append(
                MenuValidationIssue(
                    code="menu_map_missing_in_buttons",
                    message=f"menu_map entries missing in nav buttons: {missing_in_nav}",
                )
            )
        allowed_kinds = {"dvd_pgc", "dvd_cell"}
        unexpected = sorted(set(target_kind_counts) - allowed_kinds)
        if unexpected:
            issues.append(
                MenuValidationIssue(
                    code="unexpected_target_kind",
                    message=f"Unexpected target kinds for DVD: {unexpected}",
                )
            )
    else:
        missing_in_menu_map = []
        missing_in_nav = []
        if nav.disc_format in {DiscFormat.SVCD, DiscFormat.VCD}:
            allowed_kinds = {"track", "segment_item", "time_range"}
            unexpected = sorted(set(target_kind_counts) - allowed_kinds)
            if unexpected:
                issues.append(
                    MenuValidationIssue(
                        code="unexpected_target_kind",
                        message=(
                            f"Unexpected target kinds for {nav.disc_format}: {unexpected}"
                        ),
                    )
                )

    menu_ids = sorted(set(menu_id_counts) | set(nav_menu_id_counts))
    menu_counts = [
        MenuValidationMenuCount(
            menu_id=menu_id,
            menu_entry_count=menu_id_counts.get(menu_id, 0),
            nav_button_count=nav_menu_id_counts.get(menu_id, 0),
        )
        for menu_id in menu_ids
    ]
    if nav.disc_format == DiscFormat.DVD:
        for menu in menu_counts:
            if menu.menu_entry_count != menu.nav_button_count:
                issues.append(
                    MenuValidationIssue(
                        code="menu_count_mismatch",
                        message=(
                            f"Menu {menu.menu_id} entry/button mismatch: "
                            f"{menu.menu_entry_count} vs {menu.nav_button_count}"
                        ),
                    )
                )

    target_kinds = [
        MenuValidationTargetKindCount(kind=kind, count=count)
        for kind, count in sorted(target_kind_counts.items())
    ]
    ok = len(issues) == 0
    model = MenuValidationModel(
        ok=ok,
        disc_format=nav.disc_format,
        menu_entry_count=len(menu_entry_ids),
        nav_button_count=len(nav_button_ids),
        menu_counts=menu_counts,
        target_kind_counts=target_kinds,
        missing_in_menu_map=missing_in_menu_map,
        missing_in_nav_buttons=missing_in_nav,
        issues=issues,
    )
    write_json(out_dir / "menu_validation.json", model)

    if not ok:
        raise ValidationError("Menu validation failed; see menu_validation.json")
    return model
