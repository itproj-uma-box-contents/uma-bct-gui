"""Run explicitly on a desktop: uv run python tests/desktop_smoke.py.

Uses the real Flutter renderer to catch layout and control-method failures that
the unit-test page cannot detect. All catalogue writes go to temporary folders.
"""

import asyncio
import base64
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import flet as ft
import openpyxl

import main


def walk(control):
    yield control
    for child in getattr(control, "controls", []):
        yield from walk(child)
    child = getattr(control, "content", None)
    if child is not None and not isinstance(child, str):
        yield from walk(child)


def create_batches(root):
    image = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )
    fields = ["Description", "Unit Number", main.IMAGE_LINK_FIELD, main.REVIEWED_FIELD]
    link = '=HYPERLINK("Box Images/box.png","Box")'
    rows = [
        dict(zip(fields, ["Café, archive\nSecond line", "0007", link, "False"])),
        dict(zip(fields, ["Missing box", "0008", "", "False"])),
        dict(zip(fields, ["Another box", "0009", link, "False"])),
    ]
    for suffix in ("csv", "xlsx"):
        folder = root / suffix
        (folder / "Box Images").mkdir(parents=True)
        (folder / "Box Images" / "box.png").write_bytes(image)
        path = folder / f"Catalogue.{suffix}"
        if suffix == "csv":
            main.save_rows(path, fields, rows)
        else:
            workbook = openpyxl.Workbook()
            workbook.active.title = "Catalogue"
            workbook.active.append(fields)
            for row in rows:
                workbook.active.append([row[name] for name in fields])
            workbook.create_sheet("Notes")["A1"] = "Keep this note"
            workbook.active = 1
            workbook.save(path)
            workbook.close()


async def resize_window(page, width, height):
    resized = asyncio.Event()
    original_handler = page.on_resize

    def on_resize(event):
        original_handler(event)
        if (event.width < main.COMPACT_WIDTH) == (width < main.COMPACT_WIDTH):
            resized.set()

    page.on_resize = on_resize
    try:
        page.window.width, page.window.height = width, height
        page.update()
        await asyncio.wait_for(resized.wait(), timeout=10)
    finally:
        page.on_resize = original_handler
    # Wait for Flutter to paint the new layout before invoking its controls.
    await page.take_screenshot()


def run():
    completed = []
    with tempfile.TemporaryDirectory(prefix="uma-bct-desktop-") as temporary:
        root = Path(temporary)
        create_batches(root)

        async def check_window(page):
            preferences = ft.SharedPreferences()
            previous_theme = None
            preference_loaded = False
            try:
                previous_theme = await asyncio.wait_for(preferences.get(main.THEME_PREFERENCE), timeout=3)
                preference_loaded = True
                page.enable_screenshots = True
                await main.page_main(page)

                def controls():
                    return [child for control in page.controls for child in walk(control)]

                def button(label):
                    return next(c for c in controls() if getattr(c, "content", None) == label)

                def arrow(key):
                    page.on_keyboard_event(SimpleNamespace(key=key, shift=False, ctrl=False, alt=False, meta=False))

                for suffix, size in (("csv", (640, 480)), ("xlsx", (1000, 650))):
                    picker = AsyncMock(return_value=str(root / suffix))
                    with patch.object(ft.FilePicker, "get_directory_path", picker):
                        await button("Open outputs folder").on_click(None)
                    await page.take_screenshot()
                    if page.width < main.COMPACT_WIDTH:
                        # The previous record may have left the compact view at
                        # the image. Bring the field into view before focusing it.
                        await page.controls[0].controls[1].scroll_to(offset=0)
                        await page.take_screenshot()
                    description = next(c for c in controls() if isinstance(c, ft.TextField) and c.label == "Description")
                    original_description = description.value
                    arrow("Arrow Right")
                    assert description.value == "Missing box"
                    await page.take_screenshot()
                    arrow("Arrow Left")
                    assert description.value == original_description
                    await page.take_screenshot()
                    await description.focus()
                    await page.take_screenshot()
                    arrow("Arrow Right")
                    assert description.value == original_description
                    description.value = "Saved correction — café"
                    await resize_window(page, *size)
                    assert description.value == "Saved correction — café"
                    if suffix == "csv":
                        toggle = next(c for c in controls() if isinstance(c, ft.IconButton))
                        await toggle.on_click(None)
                        assert await preferences.get(main.THEME_PREFERENCE) == page.theme_mode.value
                        await page.take_screenshot()
                        await page.controls[0].controls[1].scroll_to(offset=-1)
                        await page.take_screenshot()
                    for label in ("Zoom in", "Zoom out", "Reset / Fit"):
                        await button(label).on_click(None)
                    with patch.object(page, "show_dialog", wraps=page.show_dialog) as show_dialog:
                        button("Next").on_click(None)
                        dialog = show_dialog.call_args.args[0]
                        assert dialog.title.value == "Unsaved changes"
                        arrow("Arrow Right")
                        assert description.value == "Saved correction — café"
                        assert show_dialog.call_count == 1
                        next(c for c in dialog.actions if c.content == "Cancel").on_click(None)
                    button("Save").on_click(None)
                    path = main.find_catalogue(root / suffix)
                    assert main.load_rows(path)[1][0]["Description"] == description.value
                    opened = asyncio.Event()

                    async def record_open(selected):
                        assert selected == path
                        opened.set()

                    # Verify the real GUI task path without opening an external
                    # application or leaving a test workbook locked on Windows.
                    with patch.object(main, "open_in_default_app", new=AsyncMock(side_effect=record_open)) as opener:
                        button("Open catalogue").on_click(None)
                        await asyncio.wait_for(opened.wait(), timeout=5)
                        opener.assert_awaited_once_with(path)
                    images = 0
                    for index in range(3):
                        images += any(isinstance(c, ft.Image) for c in controls())
                        if index < 2:
                            button("Next").on_click(None)
                    assert images == 2
                    print(f"PASS: native {suffix.upper()} save, preview, resize, zoom, arrows/focus, and catalogue-open checks", flush=True)
            finally:
                try:
                    if preference_loaded:
                        if previous_theme is None:
                            await asyncio.wait_for(preferences.remove(main.THEME_PREFERENCE), timeout=3)
                            restored = await asyncio.wait_for(preferences.get(main.THEME_PREFERENCE), timeout=3) is None
                        else:
                            restored = await asyncio.wait_for(
                                preferences.set(main.THEME_PREFERENCE, previous_theme), timeout=3
                            )
                        if not restored:
                            raise RuntimeError("Could not restore the original theme preference")
                finally:
                    await asyncio.wait_for(page.window.destroy(), timeout=3)
            completed.append(True)

        async def check(page):
            async with asyncio.timeout(60):
                await check_window(page)

        ft.run(check, view=ft.AppView.FLET_APP_HIDDEN)
    # Flet reports callback exceptions itself, so make failure visible to a shell.
    if not completed:
        raise SystemExit(1)


if __name__ == "__main__":
    run()
