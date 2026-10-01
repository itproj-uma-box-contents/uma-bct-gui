from __future__ import annotations

import csv
from pathlib import Path

import flet as ft

# This column is used to locate the crop image on disk; it isn't shown as a form field.
IMAGE_LINK_FIELD = "Cropped Box Image Link"
# Flags get their own add/remove-a-row UI instead of a generic TextField.
FLAGS_FIELD = "Review Flags"
# Columns handled by dedicated UI rather than the generic text-field loop.
CUSTOM_FIELDS = {IMAGE_LINK_FIELD, FLAGS_FIELD}
# These fields tend to hold longer free text, so give them more room to wrap.
MULTILINE_FIELDS = {"Description"}
# VLM-computed metadata shown for context, not meant to be hand-edited.
READ_ONLY_FIELDS = {"Transcription Confidence (%)"}
# Separator used to pack the flags list into the CSV's single text column.
FLAGS_SEPARATOR = "; "

NOTHING_TO_REVIEW = "Nothing to review..."
# Fixed width of the left-hand form column; the image takes whatever's left.
FORM_WIDTH = 380


def load_rows(csv_path: Path) -> tuple[list[str], list[dict[str, str]]]:
    """Read catalogue.csv into (header order, row dicts)."""
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = [dict(row) for row in reader]
    return fieldnames, rows


def save_rows(csv_path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    """Rewrite catalogue.csv in full, preserving the original column order."""
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def page_main(page: ft.Page) -> None:
    page.title = "UMA BCT Review"
    page.window.width = 1200
    page.window.height = 800
    page.padding = 20

    # Review state. Nothing is loaded until the user picks a folder, so all of
    # this starts empty and is (re)populated by load_folder().
    outputs_dir: Path | None = None
    csv_path: Path | None = None
    fieldnames: list[str] = []
    rows: list[dict[str, str]] = []
    form_fields: list[str] = []
    current_index = 0
    text_fields: dict[str, ft.TextField] = {}

    file_picker = ft.FilePicker()

    empty_message = ft.Text(NOTHING_TO_REVIEW, size=18, weight=ft.FontWeight.BOLD)
    empty_state = ft.Column(
        controls=[empty_message],
        alignment=ft.MainAxisAlignment.CENTER,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        expand=True,
    )

    # Populated by load_folder() with one TextField per catalogue column. Fixed
    # width rather than expand=1, so it sizes to its fields and leaves the rest
    # of the row to the image.
    form_column = ft.Column(
        width=FORM_WIDTH,
        spacing=12,
        scroll=ft.ScrollMode.AUTO,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
    )

    # One row per flag: a TextField plus a remove button. Rebuilt on every
    # refresh() from the current row's semicolon-separated flags text.
    flags_column = ft.Column(spacing=6)

    def make_flag_row(value: str = "") -> ft.Row:
        field = ft.TextField(value=value, dense=True, expand=True)
        remove_btn = ft.IconButton(icon=ft.Icons.CLOSE, icon_size=18, tooltip="Remove flag")
        row = ft.Row(controls=[field, remove_btn], spacing=4)
        row.data = field  # lets callers read this row's text back out later

        def on_remove(e: ft.Event) -> None:
            flags_column.controls.remove(row)
            page.update()

        remove_btn.on_click = on_remove
        return row

    def on_add_flag(e: ft.Event) -> None:
        flags_column.controls.append(make_flag_row())
        page.update()

    add_flag_btn = ft.TextButton(content="+ Add flag", on_click=on_add_flag)

    def set_flags(value: str) -> None:
        parts = [p.strip() for p in value.split(";")] if value else []
        flags_column.controls = [make_flag_row(p) for p in parts if p]

    def get_flags_text() -> str:
        values = [row.data.value.strip() for row in flags_column.controls]
        return FLAGS_SEPARATOR.join(v for v in values if v)

    flags_block = ft.Column(
        controls=[
            ft.Text("Review Flags", size=12, color=ft.Colors.ON_SURFACE_VARIANT),
            flags_column,
            add_flag_btn,
        ],
        spacing=6,
    )

    no_image_placeholder = ft.Text("No image", color=ft.Colors.ON_SURFACE_VARIANT)
    image_area = ft.Container(content=no_image_placeholder, expand=1)

    status_text = ft.Text(size=16, weight=ft.FontWeight.BOLD)

    open_folder_btn = ft.Button(content="Open outputs folder")

    discard_box_btn = ft.Button(
        content="Discard box",
        bgcolor=ft.Colors.RED,
        color=ft.Colors.WHITE,
    )
    discard_changes_btn = ft.Button(
        content="Discard changes",
        bgcolor=ft.Colors.YELLOW,
        color=ft.Colors.BLACK,
    )
    back_btn = ft.Button(
        content="Back",
        bgcolor=ft.Colors.GREY,
        color=ft.Colors.BLACK,
    )
    save_next_btn = ft.Button(
        content="Save & Next",
        bgcolor=ft.Colors.BLUE,
        color=ft.Colors.WHITE,
    )

    def set_controls_enabled(enabled: bool) -> None:
        for tf in text_fields.values():
            tf.disabled = not enabled
        add_flag_btn.disabled = not enabled
        discard_box_btn.disabled = not enabled
        discard_changes_btn.disabled = not enabled
        save_next_btn.disabled = not enabled

    def refresh(update: bool = True) -> None:
        """Repaint the form/image/status for current_index, or report that
        there's nothing left to review once every row has been handled."""
        if current_index >= len(rows):
            status_text.value = "No records left to review."
            for tf in text_fields.values():
                tf.value = ""
            flags_column.controls = []
            image_area.content = no_image_placeholder
            set_controls_enabled(False)
            # Still let the user step back to revisit an already-reviewed record.
            back_btn.disabled = current_index <= 0
            if update:
                page.update()
            return

        row = rows[current_index]
        for name in form_fields:
            text_fields[name].value = row.get(name, "")
        set_flags(row.get(FLAGS_FIELD, ""))

        # Image paths in the CSV are relative to the outputs directory.
        image_rel = row.get(IMAGE_LINK_FIELD, "")
        image_path = outputs_dir / image_rel if outputs_dir and image_rel else None
        if image_path and image_path.is_file():
            # Read bytes directly rather than pointing Image at the path: the
            # outputs dir is arbitrary and outside Flet's assets_dir.
            image_area.content = ft.InteractiveViewer(
                content=ft.Image(
                    src=image_path.read_bytes(),
                    fit=ft.BoxFit.CONTAIN,
                    expand=True,
                    error_content=no_image_placeholder,
                ),
                min_scale=1,
                max_scale=8,
                # Lets trackpad scrolling zoom, not just pan, matching mouse-wheel zoom.
                trackpad_scroll_causes_scale=True,
            )
        else:
            image_area.content = no_image_placeholder

        status_text.value = f"Record {current_index + 1} of {len(rows)}"
        set_controls_enabled(True)
        back_btn.disabled = current_index <= 0
        if update:
            page.update()

    def show_empty_state(message: str) -> None:
        nonlocal outputs_dir, csv_path
        outputs_dir = None
        csv_path = None
        page.title = "UMA BCT Review"
        empty_message.value = message
        content_area.content = empty_state
        buttons_row.visible = False
        page.update()

    def load_folder(dir_path: Path) -> None:
        nonlocal outputs_dir, csv_path, fieldnames, rows, form_fields, current_index

        candidate_csv = dir_path / "catalogue.csv"
        if not candidate_csv.is_file():
            show_empty_state(f"No catalogue.csv found in {dir_path}")
            return

        outputs_dir = dir_path
        csv_path = candidate_csv
        fieldnames, rows = load_rows(csv_path)
        form_fields = [name for name in fieldnames if name not in CUSTOM_FIELDS]
        current_index = 0

        # Rebuild the field inputs from scratch: a different folder's catalogue
        # could have different columns.
        text_fields.clear()
        for name in form_fields:
            text_fields[name] = ft.TextField(
                label=name,
                multiline=name in MULTILINE_FIELDS,
                min_lines=3 if name in MULTILINE_FIELDS else 1,
                max_lines=6 if name in MULTILINE_FIELDS else 1,
                read_only=name in READ_ONLY_FIELDS,
            )
        form_column.controls = [*text_fields.values(), flags_block]

        page.title = f"UMA BCT Review — {outputs_dir.name}"
        content_area.content = body
        buttons_row.visible = True
        refresh()

    async def on_open_folder(e: ft.Event) -> None:
        try:
            selected = await file_picker.get_directory_path(
                dialog_title="Select outputs folder"
            )
        except Exception as ex:
            show_empty_state(f"Couldn't open the folder picker: {ex}")
            return
        if selected:
            load_folder(Path(selected))

    def on_discard_box(e: ft.Event) -> None:
        # This crop wasn't a real record: drop the row entirely and move on.
        nonlocal current_index
        del rows[current_index]
        save_rows(csv_path, fieldnames, rows)
        refresh()

    def on_discard_changes(e: ft.Event) -> None:
        # Reload the row's saved values, discarding any unsaved edits.
        refresh()

    def on_back(e: ft.Event) -> None:
        # Revisit the previous record; unsaved edits on the current one are dropped.
        nonlocal current_index
        if current_index > 0:
            current_index -= 1
            refresh()

    def on_save_next(e: ft.Event) -> None:
        nonlocal current_index
        row = rows[current_index]
        for name in form_fields:
            row[name] = text_fields[name].value or ""
        row[FLAGS_FIELD] = get_flags_text()
        save_rows(csv_path, fieldnames, rows)
        current_index += 1
        refresh()

    open_folder_btn.on_click = on_open_folder
    discard_box_btn.on_click = on_discard_box
    discard_changes_btn.on_click = on_discard_changes
    back_btn.on_click = on_back
    save_next_btn.on_click = on_save_next

    # Left: editable fields. Right: the crop image.
    body = ft.Row(
        controls=[form_column, image_area],
        expand=True,
        spacing=24,
    )

    top_bar = ft.Row(
        controls=[open_folder_btn, status_text],
        spacing=16,
    )

    buttons_row = ft.Row(
        controls=[discard_box_btn, discard_changes_btn, back_btn, save_next_btn],
        alignment=ft.MainAxisAlignment.START,
        spacing=12,
        visible=False,
    )

    # Swapped between empty_state and body as folders are opened.
    content_area = ft.Container(content=empty_state, expand=True)

    page.add(
        ft.Column(
            controls=[top_bar, content_area, buttons_row],
            expand=True,
            spacing=16,
            # Without this, children only take their natural width and the
            # centered empty-state message ends up hugging the left edge.
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        )
    )


def main() -> None:
    ft.run(page_main)


if __name__ == "__main__":
    main()
