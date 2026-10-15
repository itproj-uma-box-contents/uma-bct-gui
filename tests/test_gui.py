import asyncio
import base64
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
        self.window = SimpleNamespace(destroy=AsyncMock(), center=AsyncMock(), prevent_close=False)
        self.width = 1000
        self.platform_brightness = ft.Brightness.LIGHT

    def add(self, control):
        self.controls.append(control)

    def update(self, *controls):
        self.dialogs[:] = [dialog for dialog in self.dialogs if dialog.open]

    def show_dialog(self, dialog):
        dialog.open = True
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
        self.preferences = {}
        self.get_preference = AsyncMock(side_effect=lambda key: self.preferences.get(key))
        self.set_preference = AsyncMock(side_effect=self.remember_preference)
        for method, mock in (("get", self.get_preference), ("set", self.set_preference)):
            patcher = patch.object(ft.SharedPreferences, method, mock)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.page = TestPage()
        asyncio.run(main.page_main(self.page))

    def remember_preference(self, key, value):
        self.preferences[key] = value
        return True

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

    def test_failed_save_on_close_keeps_window_open_and_edits(self):
        self.open_folder()
        self.description().value = "Unsaved correction"
        self.page.window.on_event(SimpleNamespace(type=ft.WindowEventType.CLOSE))
        with patch.object(main, "save_rows", side_effect=main.CatalogueError("Disk full")):
            self.choose("Save")
        self.page.window.destroy.assert_not_awaited()
        self.assertEqual(self.description().value, "Unsaved correction")
        self.assertEqual(main.load_rows(self.path)[1][0]["Description"], "First box")
        self.assertIn("Disk full", self.page.dialogs[-1].content.value)

    def test_discarding_all_records_leaves_safe_empty_state(self):
        self.open_folder()
        for _ in range(2):
            self.click(self.button("Discard box"))
            self.choose("Discard box")
        self.assertEqual(main.load_rows(self.path)[1], [])
        self.assertEqual(self.description().value, "")
        self.assertTrue(self.description().disabled)
        for label in ("Save", "Discard box", "Prev", "Next"):
            self.assertTrue(self.button(label).disabled)

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

    def test_window_is_centred_shown_and_remains_usable_if_centring_fails(self):
        self.page.window.center.assert_awaited_once()
        self.assertTrue(self.page.window.visible)
        self.assertEqual((self.page.window.width, self.page.window.height), (1000, 650))
        self.page = TestPage()
        self.page.window.center.side_effect = RuntimeError("Window manager unavailable")
        with self.assertLogs(main.logger, level="WARNING"):
            asyncio.run(main.page_main(self.page))
        self.assertTrue(self.page.window.visible)
        self.open_folder()
        self.assertEqual(self.description().value, "First box")

    def test_theme_toggle_remembers_choice_without_losing_edits(self):
        self.open_folder()
        self.description().value = "Unsaved correction"
        toggle = next(c for c in self.controls() if isinstance(c, ft.IconButton))
        self.click(toggle)
        self.assertEqual(self.page.theme_mode, ft.ThemeMode.DARK)
        self.assertEqual(toggle.tooltip, "Switch to light mode")
        self.assertEqual(self.preferences[main.THEME_PREFERENCE], "dark")
        self.assertEqual(self.description().value, "Unsaved correction")
        self.click(self.button("Next"))
        self.assertEqual(self.page.dialogs[-1].title.value, "Unsaved changes")
        self.choose("Cancel")
        self.page = TestPage()
        asyncio.run(main.page_main(self.page))
        self.assertEqual(self.page.theme_mode, ft.ThemeMode.DARK)

    def test_theme_uses_system_brightness_until_an_explicit_choice(self):
        self.page.platform_brightness = ft.Brightness.DARK
        self.page.on_platform_brightness_change(None)
        toggle = next(c for c in self.controls() if isinstance(c, ft.IconButton))
        self.assertEqual(toggle.tooltip, "Switch to light mode")
        self.click(toggle)
        self.assertEqual(self.page.theme_mode, ft.ThemeMode.LIGHT)
        self.page.on_platform_brightness_change(None)
        self.assertEqual(self.page.theme_mode, ft.ThemeMode.LIGHT)

    def test_preference_failures_do_not_block_the_app_or_toggle(self):
        self.get_preference.side_effect = RuntimeError("Unavailable storage")
        self.page = TestPage()
        with self.assertLogs(main.logger, level="WARNING"):
            asyncio.run(main.page_main(self.page))
        self.assertTrue(self.page.window.visible)
        self.assertEqual(self.page.theme_mode, ft.ThemeMode.SYSTEM)
        self.set_preference.side_effect = RuntimeError("Unavailable storage")
        toggle = next(c for c in self.controls() if isinstance(c, ft.IconButton))
        with self.assertLogs(main.logger, level="WARNING"):
            self.click(toggle)
        self.assertEqual(self.page.theme_mode, ft.ThemeMode.DARK)
        self.assertFalse(toggle.disabled)
        self.assertIn("this session", self.page.dialogs[-1].content.value)

    def test_theme_failure_cannot_keep_discard_confirmation_open_or_repeat_deletion(self):
        self.open_folder()

        async def exercise():
            started = asyncio.Event()
            release = asyncio.Event()

            async def fail_later(key, value):
                started.set()
                await release.wait()
                raise RuntimeError("Unavailable storage")

            self.set_preference.side_effect = fail_later
            toggle = next(c for c in self.controls() if isinstance(c, ft.IconButton))
            task = asyncio.create_task(toggle.on_click(None))
            await asyncio.wait_for(started.wait(), timeout=1)
            self.click(self.button("Discard box"))
            confirmation = self.page.dialogs[-1]
            confirm_button = next(c for c in confirmation.actions if c.content == "Discard box")

            with self.assertLogs(main.logger, level="WARNING"):
                release.set()
                await task
            notification = self.page.dialogs[-1]
            self.assertIsInstance(notification, ft.SnackBar)
            self.click(confirm_button)
            self.assertFalse(confirmation.open)
            self.assertTrue(notification.open)
            self.assertEqual(len(main.load_rows(self.path)[1]), 1)

            # A second click can already be queued while the dialog is closing.
            self.click(confirm_button)
            self.assertEqual(len(main.load_rows(self.path)[1]), 1)

        asyncio.run(exercise())

    def test_resizing_retains_unsaved_form_values_and_flags(self):
        self.open_folder()
        description = self.description()
        description.value = "Unsaved correction"
        self.click(self.button("+ Add flag").items[0])
        for width in (640, 1000, 800):
            self.page.on_resize(SimpleNamespace(width=width))
            self.assertIs(self.description(), description)
            self.assertEqual(description.value, "Unsaved correction")
            chips = [c for c in self.controls() if isinstance(c, ft.Chip)]
            self.assertEqual([c.data for c in chips], [main.DUPLICATE_FLAG])
        self.click(self.button("Save"))
        row = main.load_rows(self.path)[1][0]
        self.assertEqual(row["Description"], "Unsaved correction")
        self.assertEqual(row[main.FLAGS_FIELD], main.DUPLICATE_FLAG)

    def test_failed_save_can_be_retried_without_losing_edits(self):
        self.open_folder()
        self.description().value = "Correction"
        with patch("main.os.replace", side_effect=PermissionError("File locked")):
            self.click(self.button("Save"))
        self.assertEqual(self.description().value, "Correction")
        self.choose("OK")
        self.click(self.button("Save"))
        self.assertEqual(main.load_rows(self.path)[1][0]["Description"], "Correction")

    def test_uppercase_reviewed_and_selected_filename_are_shown_correctly(self):
        self.write_catalogue(reviewed="TRUE")
        renamed = self.path.with_name("Catalogue.CSV")
        self.path.rename(renamed)
        self.open_folder()
        messages = [c.value for c in self.controls() if isinstance(c, ft.Text)]
        self.assertIn("All 2 records reviewed", messages)
        self.assertIn("Editing Catalogue.CSV", messages)

    def test_batch_with_hyperlink_formulas_shows_seven_images_and_two_empty_records(self):
        image = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")
        crops = self.folder / "Box Images"
        crops.mkdir()
        fields = ["Description", main.IMAGE_LINK_FIELD, main.REVIEWED_FIELD]
        with self.path.open("w", newline="", encoding="utf-8") as output:
            writer = csv.writer(output)
            writer.writerow(fields)
            for index in range(9):
                link = ""
                if index not in (1, 2):
                    (crops / f"Box {index}.png").write_bytes(image)
                    link = f'=HYPERLINK("Box Images/Box {index}.png","Box {index}")'
                writer.writerow([f"Record {index}", link, "False"])
        original_links = [row[main.IMAGE_LINK_FIELD] for row in main.load_rows(self.path)[1]]
        self.open_folder()
        image_count = empty_count = 0
        for index in range(9):
            previews = [c for c in self.controls() if isinstance(c, ft.Image)]
            if previews:
                image_count += 1
                self.assertEqual(previews[0].src, image)
            else:
                empty_count += 1
                self.assertIn("No image", [c.value for c in self.controls() if isinstance(c, ft.Text)])
            if index < 8:
                self.click(self.button("Next"))
        self.assertEqual((image_count, empty_count), (7, 2))
        self.description().value = "Correction"
        self.click(self.button("Save"))
        self.assertEqual([row[main.IMAGE_LINK_FIELD] for row in main.load_rows(self.path)[1]], original_links)

    def test_empty_and_damaged_images_have_distinct_fallbacks(self):
        self.path.write_text(self.path.read_text().replace("First box,,", "First box,crop.png,"))
        image = self.folder / "crop.png"
        image.touch()
        self.open_folder()
        self.assertTrue(any("file is empty" in (c.value or "") for c in self.controls() if isinstance(c, ft.Text)))
        image.write_bytes(b"invalid image")
        self.open_folder()
        preview = next(c for c in self.controls() if isinstance(c, ft.Image))
        self.assertIn("damaged or unsupported", preview.error_content.value)


if __name__ == "__main__":
    unittest.main()
