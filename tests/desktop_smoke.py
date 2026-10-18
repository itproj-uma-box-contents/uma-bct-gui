"""Run explicitly on a desktop: uv run python tests/desktop_smoke.py.

Uses the real Flutter renderer to catch layout and control-method failures that
the unit-test page cannot detect. All catalogue writes go to temporary folders.
"""

import asyncio
import base64
import contextlib
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import flet as ft
import flet_desktop
import openpyxl

import main


LONG_FIELD_NAME = "A catalogue column with a long heading that must not overlap nearby fields. " * 4


async def run_desktop(callback, before_main, timeout=90):
    """Bound the entire native launch and clean up only this test's client."""
    client = None
    pid_file = None
    failed = False
    open_view = flet_desktop.open_flet_view_async

    async def capture_client(*args, **kwargs):
        nonlocal client, pid_file
        client, pid_file = await open_view(*args, **kwargs)
        return client, pid_file

    try:
        with patch.object(flet_desktop, "open_flet_view_async", side_effect=capture_client):
            async with asyncio.timeout(timeout):
                await ft.run_async(callback, view=ft.AppView.FLET_APP_HIDDEN, before_main=before_main)
    except BaseException:
        failed = True
        raise
    finally:
        try:
            if client is not None:
                try:
                    flet_desktop.close_flet_view(pid_file)
                finally:
                    if client.returncode is None:
                        with contextlib.suppress(ProcessLookupError):
                            client.terminate()
                        try:
                            await asyncio.wait_for(client.wait(), timeout=3)
                        except TimeoutError:
                            with contextlib.suppress(ProcessLookupError):
                                client.kill()
                            await asyncio.wait_for(client.wait(), timeout=3)
        except Exception as error:
            print(f"Could not clean up the test client: {error}", flush=True)
            if not failed:
                raise


async def save_failure_screenshot(page):
    """Keep a diagnostic image outside the disposable catalogue folder."""
    try:
        screenshot = await asyncio.wait_for(page.take_screenshot(), timeout=3)
        folder = Path(tempfile.mkdtemp(prefix="uma-bct-desktop-failure-"))
        path = folder / "failure.png"
        path.write_bytes(screenshot)
        print(f"Native failure screenshot: {path}", flush=True)
    except Exception as error:
        print(f"Could not capture the native failure: {error}", flush=True)


def walk(control):
    yield control
    for child in getattr(control, "controls", []):
        yield from walk(child)
    child = getattr(control, "content", None)
    if child is not None and not isinstance(child, str):
        yield from walk(child)


def find_text_field(controls, label):
    return next(
        control for control in controls
        if isinstance(control, ft.TextField)
        and getattr(control.label, "value", control.label) == label
    )


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


def create_layout_batch(root):
    folder = root / "layout"
    shutil.copytree(root / "csv", folder)
    path = folder / "Catalogue.csv"
    fields, rows = main.load_rows(path)
    extra_fields = [f"Additional field {number}" for number in range(1, 5)]
    # Ensure the desktop form really overflows, so scrolling is exercised
    # even after transient notifications have disappeared.
    fields.extend([LONG_FIELD_NAME, *extra_fields, main.FLAGS_FIELD])
    for row in rows:
        row[LONG_FIELD_NAME] = "A visible value"
        for name in extra_fields:
            row[name] = "A preserved value"
        row[main.FLAGS_FIELD] = "An imported flag with a long description " * 15
    main.save_rows(path, fields, rows)
    return folder


async def resize_window(page, width, height, layout_events=None):
    if (page.window.width, page.window.height) == (width, height):
        await page.take_screenshot()
        return

    resized = asyncio.Event()
    original_handler = page.on_resize
    expected_width = width - max(0, page.window.width - page.width)
    expected_height = height - max(0, page.window.height - page.height)
    if layout_events is not None:
        while not layout_events.empty():
            layout_events.get_nowait()

    def on_resize(event):
        original_handler(event)
        if abs(event.width - expected_width) < 2 and abs(event.height - expected_height) < 2:
            resized.set()

    page.on_resize = on_resize
    try:
        page.window.width, page.window.height = width, height
        page.update()
        await asyncio.wait_for(resized.wait(), timeout=10)
        if layout_events is not None:
            async with asyncio.timeout(5):
                while True:
                    rendered_width, rendered_height = await layout_events.get()
                    if (
                        abs(rendered_width - (expected_width - main.PAGE_PADDING * 2)) < 2
                        and abs(rendered_height - (expected_height - main.PAGE_PADDING * 2)) < 2
                    ):
                        break
    finally:
        page.on_resize = original_handler
    # Allow the native resize/layout transition to paint before using its
    # newly attached scroll controllers and image methods.
    await page.take_screenshot(delay=ft.Duration(milliseconds=150))


def run():
    completed = []
    native_errors = []
    with tempfile.TemporaryDirectory(prefix="uma-bct-desktop-") as temporary:
        root = Path(temporary)
        create_batches(root)
        layout_folder = create_layout_batch(root)

        async def check_startup(page):
            # Exercise production startup without screenshot support or a native
            # preferences call from the test before page_main().
            try:
                async with asyncio.timeout(30):
                    await main.page_main(page)
                    controls = [child for control in page.controls for child in walk(control)]
                    open_folder = next(c for c in controls if getattr(c, "content", None) == "Open outputs folder")
                    await open_folder.focus()
                    with patch.object(ft.FilePicker, "get_directory_path", AsyncMock(return_value=str(root / "csv"))):
                        await open_folder.on_click(None)
                    controls = [child for control in page.controls for child in walk(control)]
                    description = find_text_field(controls, "Description")
                    await description.focus()
                    assert description.value == "Café, archive\nSecond line"
                    print("PASS: normal native startup and loaded field focus without screenshot support", flush=True)
            finally:
                await asyncio.wait_for(page.window.destroy(), timeout=3)
            completed.append("startup")

        async def check_window(page):
            preferences = ft.SharedPreferences()
            previous_theme = None
            preference_loaded = False
            layout_events = asyncio.Queue()
            original_add = page.add

            def on_layout(event):
                # This callback observes a rendered frame; it must not trigger
                # Flet's automatic update of the root subtree afterward.
                ft.context.disable_auto_update()
                layout_events.put_nowait((event.width, event.height))

            def add_with_layout_observer(control):
                # Install before mounting, so observing layout never reparents
                # the live tree. Resize metrics alone precede Flutter layout.
                control.on_size_change = on_layout
                original_add(control)

            try:
                with patch.object(page, "add", side_effect=add_with_layout_observer):
                    await main.page_main(page)
                # Drive controls after the initial window has painted, as a
                # desktop user would, rather than during its first layout.
                await page.take_screenshot(delay=ft.Duration(milliseconds=150))
                previous_theme = await asyncio.wait_for(preferences.get(main.THEME_PREFERENCE), timeout=3)
                preference_loaded = True

                def controls():
                    return [child for control in page.controls for child in walk(control)]

                def button(label):
                    return next(c for c in controls() if getattr(c, "content", None) == label)

                def arrow(key):
                    page.on_keyboard_event(SimpleNamespace(key=key, shift=False, ctrl=False, alt=False, meta=False))

                for suffix, size in (("csv", (640, 480)), ("xlsx", (1000, 650))):
                    picker = AsyncMock(return_value=str(root / suffix))
                    await button("Open outputs folder").focus()
                    with patch.object(ft.FilePicker, "get_directory_path", picker):
                        await button("Open outputs folder").on_click(None)
                    await page.take_screenshot()
                    if page.width < main.COMPACT_WIDTH:
                        # The previous record may have left the compact view at
                        # the image. Bring the field into view before focusing it.
                        await page.controls[0].controls[1].scroll_to(offset=0)
                        await page.take_screenshot()
                    description = find_text_field(controls(), "Description")
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
                    await resize_window(page, *size, layout_events=layout_events)
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
                    opening_tasks = []
                    original_run_task = page.run_task

                    def track_open_task(callback, *args):
                        task = original_run_task(callback, *args)
                        opening_tasks.append(task)
                        return task

                    # Verify the real GUI task path without opening an external
                    # application or leaving a test workbook locked on Windows.
                    with patch.object(main, "open_in_default_app", new=AsyncMock()) as opener:
                        with patch.object(page, "run_task", side_effect=track_open_task):
                            button("Open catalogue").on_click(None)
                        assert len(opening_tasks) == 1
                        await asyncio.wait_for(asyncio.wrap_future(opening_tasks[0]), timeout=5)
                        opener.assert_awaited_once_with(path)
                    images = 0
                    for index, expected in enumerate(("Saved correction — café", "Missing box", "Another box")):
                        assert description.value == expected
                        images += any(isinstance(c, ft.Image) for c in controls())
                        if index < 2:
                            button("Next").on_click(None)
                    assert images == 2
                    print(f"PASS: native {suffix.upper()} save, preview, resize, zoom, arrows/focus, and catalogue-open checks", flush=True)

                # Let the final 1.5-second Saved notification dismiss before
                # visually checking access to the footer in short windows.
                await page.take_screenshot(delay=ft.Duration(milliseconds=1600))
                await button("Open outputs folder").focus()
                with patch.object(ft.FilePicker, "get_directory_path", AsyncMock(return_value=str(layout_folder))):
                    await button("Open outputs folder").on_click(None)
                await page.take_screenshot(delay=ft.Duration(milliseconds=150))
                description = find_text_field(controls(), "Description")
                await description.focus()
                description.value = "Unsaved layout correction — café"
                page.update()
                heading = find_text_field(controls(), LONG_FIELD_NAME)
                assert heading.label.max_lines == 1 and heading.label.no_wrap
                assert heading.tooltip == LONG_FIELD_NAME

                for width, height in ((640, 360), (1000, 360), (700, 900), (1400, 500), (640, 480), (1000, 650)):
                    print(f"Checking native layout {width} × {height}", flush=True)
                    await resize_window(page, width, height, layout_events=layout_events)
                    assert description.value == "Unsaved layout correction — café"
                    review = page.controls[0]
                    content = review.controls[1]
                    if review.scroll is not None:
                        scroller = review
                    elif content.scroll is not None:
                        scroller = content
                    else:
                        scroller = content.controls[0].controls[0]
                    await scroller.scroll_to(offset=-1)
                    await page.take_screenshot()
                    for label in ("Zoom in", "Zoom out", "Reset / Fit"):
                        await button(label).on_click(None)

                await resize_window(page, 640, 360, layout_events=layout_events)
                with patch.object(page, "show_dialog", wraps=page.show_dialog) as show_dialog:
                    message = "Could not open a deeply nested folder: " + "/long folder name" * 220
                    with patch.object(ft.FilePicker, "get_directory_path", AsyncMock(side_effect=OSError(message))):
                        await button("Open outputs folder").on_click(None)
                    dialog = show_dialog.call_args.args[0]
                    assert dialog.scrollable
                    await page.take_screenshot(delay=ft.Duration(milliseconds=300))
                    next(c for c in dialog.actions if c.content == "OK").on_click(None)
                assert description.value == "Unsaved layout correction — café"
                if native_errors:
                    raise RuntimeError("The native renderer reported an error")
                print("PASS: native short, portrait and wide layouts, long labels, dialog scrolling, and edit retention", flush=True)
            except (Exception, asyncio.CancelledError):
                await save_failure_screenshot(page)
                raise
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
            completed.append("review")

        async def check(page):
            async with asyncio.timeout(60):
                await check_window(page)

        def configure_errors(page):
            def on_error(event):
                ft.context.disable_auto_update()
                native_errors.append(str(event.data))
                print(f"Native renderer error: {event.data}", flush=True)

            page.on_error = on_error

        def configure_page(page):
            # Enabling screenshots changes the native page wrapper. Configure it
            # before registration so live controls keep the same parent.
            configure_errors(page)
            page.enable_screenshots = True

        asyncio.run(run_desktop(check_startup, before_main=configure_errors))
        asyncio.run(run_desktop(check, before_main=configure_page))
    # Flet reports callback exceptions itself, so make failure visible to a shell.
    if completed != ["startup", "review"] or native_errors:
        raise SystemExit(1)


if __name__ == "__main__":
    run()
