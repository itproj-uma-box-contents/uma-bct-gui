import asyncio
import csv
import inspect
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import flet as ft

import main


class TestPage:
    """Keep real Flet controls, without launching a desktop window."""

    def __init__(self):
        self.controls = []
        self.dialogs = []
        self.window = SimpleNamespace(destroy=AsyncMock(), prevent_close=False)

    def add(self, control):
        self.controls.append(control)

    def update(self):
        pass

    def show_dialog(self, dialog):
        self.dialogs.append(dialog)

    def pop_dialog(self):
        self.dialogs.pop()

    def run_task(self, callback):
        asyncio.run(callback())


def walk_controls(control):
    yield control
    for child in getattr(control, "controls", []):
        yield from walk_controls(child)
    content = getattr(control, "content", None)
    if content is not None and not isinstance(content, str):
        yield from walk_controls(content)


class GuiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.path = self.folder / "catalogue.csv"
        self.write_catalogue()
        self.page = TestPage()
        main.page_main(self.page)

    def write_catalogue(self, reviewed=False, include_flags=True):
        fields = ["Description", main.IMAGE_LINK_FIELD, main.REVIEWED_FIELD]
        if include_flags:
            fields.append(main.FLAGS_FIELD)
        with self.path.open("w", newline="", encoding="utf-8") as output:
            writer = csv.DictWriter(output, fieldnames=fields)
            writer.writeheader()
            for description in ("First box", "Second box"):
                writer.writerow({"Description": description, main.REVIEWED_FIELD: str(reviewed)})

    def controls(self):
        for control in self.page.controls:
            yield from walk_controls(control)

    def button(self, label):
        return next(c for c in self.controls() if getattr(c, "content", None) == label)

    def description(self):
        return next(c for c in self.controls() if isinstance(c, ft.TextField) and c.label == "Description")

    def click(self, control):
        handler = control.on_click
        if inspect.iscoroutinefunction(handler):
            asyncio.run(handler(None))
        else:
            handler(None)

    def choose(self, label):
        dialog = self.page.dialogs[-1]
        self.click(next(button for button in dialog.actions if button.content == label))

    def open_folder(self, folder=None):
        with patch.object(ft.FilePicker, "get_directory_path", new=AsyncMock(return_value=str(folder or self.folder))):
            self.click(self.button("Open outputs folder"))

    def test_navigation_still_prompts_and_saves(self):
        self.open_folder()
        self.description().value = "Corrected first box"
        self.click(self.button("Next"))
        self.choose("Save")
        self.assertEqual(self.description().value, "Second box")
        self.assertEqual(main.load_rows(self.path)[1][0]["Description"], "Corrected first box")

    def test_reopening_dirty_folder_can_be_cancelled(self):
        self.open_folder()
        self.description().value = "Unsaved correction"
        self.open_folder()
        self.assertEqual(self.page.dialogs[-1].title.value, "Unsaved changes")
        self.choose("Cancel")
        self.assertEqual(self.description().value, "Unsaved correction")

    def test_folder_switch_save_failure_keeps_current_edits(self):
        self.open_folder()
        self.description().value = "Unsaved correction"
        self.open_folder()
        with patch.object(main, "save_rows", side_effect=main.CatalogueError("Disk full")):
            self.choose("Save")
        self.assertEqual(self.description().value, "Unsaved correction")
        self.assertIn("Disk full", self.page.dialogs[-1].content.value)

    def test_failed_save_stays_dirty_and_discard_restores_original(self):
        self.open_folder()
        self.description().value = "Unsaved correction"
        with patch.object(main, "save_rows", side_effect=main.CatalogueError("Disk full")):
            self.click(self.button("Save"))
        self.choose("OK")
        self.click(self.button("Next"))
        self.assertEqual(self.page.dialogs[-1].title.value, "Unsaved changes")
        self.choose("Cancel")
        self.click(self.button("Discard changes"))
        self.choose("Discard changes")
        self.assertEqual(self.description().value, "First box")

    def test_failed_discard_keeps_both_records(self):
        self.open_folder()
        self.click(self.button("Discard box"))
        with patch.object(main, "save_rows", side_effect=main.CatalogueError("Permission denied")):
            self.choose("Discard box")
        self.choose("OK")
        self.assertEqual(self.description().value, "First box")
        self.click(self.button("Next"))
        self.assertEqual(self.description().value, "Second box")
        self.assertEqual(len(main.load_rows(self.path)[1]), 2)

    def test_external_edit_blocks_save(self):
        self.open_folder()
        self.description().value = "GUI correction"
        self.path.write_text(self.path.read_text().replace("Second box", "External correction"))
        self.click(self.button("Save"))
        self.assertIsInstance(self.page.dialogs[-1], ft.AlertDialog)
        self.assertEqual(self.description().value, "GUI correction")
        self.assertEqual(main.load_rows(self.path)[1][1]["Description"], "External correction")

    def test_bad_folder_preserves_existing_form(self):
        self.open_folder()
        other = self.folder / "other"
        other.mkdir()
        (other / "catalogue.xlsx").write_text("Not a workbook")
        self.open_folder(other)
        self.assertEqual(self.description().value, "First box")
        self.assertIsInstance(self.page.dialogs[-1], ft.AlertDialog)

    def test_added_flags_get_saved_when_header_was_missing(self):
        self.write_catalogue(include_flags=False)
        self.open_folder()
        menu = self.button("+ Add flag")
        self.click(menu.items[0])
        self.click(self.button("Save"))
        fields, rows = main.load_rows(self.path)
        self.assertIn(main.FLAGS_FIELD, fields)
        self.assertEqual(rows[0][main.FLAGS_FIELD], main.DUPLICATE_FLAG)

    def test_closing_dirty_window_can_be_cancelled(self):
        self.open_folder()
        self.description().value = "Unsaved correction"
        self.page.window.on_event(SimpleNamespace(type=ft.WindowEventType.CLOSE))
        self.choose("Cancel")
        self.page.window.destroy.assert_not_awaited()
        self.assertEqual(self.description().value, "Unsaved correction")

    def test_clean_window_closes(self):
        self.page.window.on_event(SimpleNamespace(type=ft.WindowEventType.CLOSE))
        self.page.window.destroy.assert_awaited_once()

    def test_reviewed_catalogue_has_clear_completion_and_revisit_action(self):
        self.write_catalogue(reviewed=True)
        self.open_folder()
        messages = [c.value for c in self.controls() if isinstance(c, ft.Text)]
        self.assertTrue(any("All 2 records reviewed" in (message or "") for message in messages))
        self.click(self.button("View records"))
        self.assertEqual(self.description().value, "First box")

    def test_unreadable_crop_does_not_stop_review(self):
        self.path.write_text(self.path.read_text().replace("First box,,", "First box,crop.png,"))
        (self.folder / "crop.png").write_bytes(b"image")
        with patch.object(Path, "read_bytes", side_effect=PermissionError("Unreadable image")):
            self.open_folder()
        self.assertEqual(self.description().value, "First box")
        messages = [c.value for c in self.controls() if isinstance(c, ft.Text)]
        self.assertTrue(any("image" in (message or "").lower() for message in messages))

    def test_invalid_crop_path_does_not_stop_review(self):
        self.path.write_text(self.path.read_text().replace("First box,,", "First box,invalid\x00path,"))
        self.open_folder()
        self.assertEqual(self.description().value, "First box")
        messages = [c.value for c in self.controls() if isinstance(c, ft.Text)]
        self.assertIn("Couldn't read this image", messages)


if __name__ == "__main__":
    unittest.main()
