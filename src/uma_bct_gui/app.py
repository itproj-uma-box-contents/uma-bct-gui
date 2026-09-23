from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import flet as ft

IMAGE_LINK_FIELD = "Cropped Box Image Link"
MULTILINE_FIELDS = {"Description", "Review Flags"}
READ_ONLY_FIELDS = {"Transcription Confidence (%)", "Review Flags"}


def load_rows(csv_path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = [dict(row) for row in reader]
    return fieldnames, rows


def save_rows(csv_path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_page_main(outputs_dir: Path, csv_path: Path):
    fieldnames, rows = load_rows(csv_path)
    form_fields = [name for name in fieldnames if name != IMAGE_LINK_FIELD]

    def page_main(page: ft.Page) -> None:
        page.title = f"UMA BCT Review — {outputs_dir.name}"
        page.window.width = 1200
        page.window.height = 800
        page.padding = 20

        current_index = 0

        text_fields = {
            name: ft.TextField(
                label=name,
                multiline=name in MULTILINE_FIELDS,
                min_lines=3 if name in MULTILINE_FIELDS else 1,
                max_lines=6 if name in MULTILINE_FIELDS else 1,
                read_only=name in READ_ONLY_FIELDS,
            )
            for name in form_fields
        }

        no_image_placeholder = ft.Text("No image", color=ft.Colors.ON_SURFACE_VARIANT)
        image_area = ft.Container(content=no_image_placeholder, expand=1)

        status_text = ft.Text(size=16, weight=ft.FontWeight.BOLD)

        discard_box_btn = ft.Button(
            content="Discard box",
            bgcolor=ft.Colors.RED_400,
            color=ft.Colors.WHITE,
        )
        discard_changes_btn = ft.Button(
            content="Discard changes",
            bgcolor=ft.Colors.YELLOW_700,
            color=ft.Colors.BLACK,
        )
        save_next_btn = ft.Button(
            content="Save & Next",
            bgcolor=ft.Colors.BLUE_400,
            color=ft.Colors.WHITE,
        )

        def set_controls_enabled(enabled: bool) -> None:
            for tf in text_fields.values():
                tf.disabled = not enabled
            discard_box_btn.disabled = not enabled
            discard_changes_btn.disabled = not enabled
            save_next_btn.disabled = not enabled

        def refresh(update: bool = True) -> None:
            if current_index >= len(rows):
                status_text.value = "All records reviewed — nothing left to check."
                for tf in text_fields.values():
                    tf.value = ""
                image_area.content = no_image_placeholder
                set_controls_enabled(False)
                if update:
                    page.update()
                return

            row = rows[current_index]
            for name in form_fields:
                text_fields[name].value = row.get(name, "")

            image_rel = row.get(IMAGE_LINK_FIELD, "")
            image_path = outputs_dir / image_rel if image_rel else None
            if image_path and image_path.is_file():
                image_area.content = ft.InteractiveViewer(
                    content=ft.Image(
                        src=image_path.read_bytes(),
                        fit=ft.BoxFit.CONTAIN,
                        expand=True,
                        error_content=no_image_placeholder,
                    ),
                    min_scale=1,
                    max_scale=8,
                    trackpad_scroll_causes_scale=True,
                )
            else:
                image_area.content = no_image_placeholder

            status_text.value = f"Record {current_index + 1} of {len(rows)}"
            set_controls_enabled(True)
            if update:
                page.update()

        def on_discard_box(e: ft.Event) -> None:
            nonlocal current_index
            del rows[current_index]
            save_rows(csv_path, fieldnames, rows)
            refresh()

        def on_discard_changes(e: ft.Event) -> None:
            refresh()

        def on_save_next(e: ft.Event) -> None:
            nonlocal current_index
            row = rows[current_index]
            for name in form_fields:
                row[name] = text_fields[name].value or ""
            save_rows(csv_path, fieldnames, rows)
            current_index += 1
            refresh()

        discard_box_btn.on_click = on_discard_box
        discard_changes_btn.on_click = on_discard_changes
        save_next_btn.on_click = on_save_next

        body = ft.Row(
            controls=[
                ft.Column(
                    controls=list(text_fields.values()),
                    spacing=12,
                    scroll=ft.ScrollMode.AUTO,
                    expand=1,
                ),
                image_area,
            ],
            expand=True,
            spacing=24,
        )

        buttons_row = ft.Row(
            controls=[discard_box_btn, discard_changes_btn, save_next_btn],
            alignment=ft.MainAxisAlignment.START,
            spacing=12,
        )

        page.add(
            ft.Column(
                controls=[status_text, body, buttons_row],
                expand=True,
                spacing=16,
            )
        )

        refresh()

    return page_main


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="uma-bct-gui",
        description=(
            "Manually verify VLM-transcribed UMA box catalogue records "
            "against their cropped box images."
        ),
    )
    parser.add_argument(
        "outputs_dir",
        type=Path,
        help="Path to an outputs directory containing catalogue.csv",
    )
    args = parser.parse_args(argv)

    outputs_dir: Path = args.outputs_dir.expanduser().resolve()
    csv_path = outputs_dir / "catalogue.csv"
    if not csv_path.is_file():
        print(f"error: no catalogue.csv found in {outputs_dir}", file=sys.stderr)
        sys.exit(1)

    ft.run(build_page_main(outputs_dir, csv_path))


if __name__ == "__main__":
    main()
