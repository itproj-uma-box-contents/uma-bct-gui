# Desktop verification

## Recorded checks — 16 October 2026

Local environment: Apple Silicon, macOS 26.4, Python 3.12.13, Flet/desktop 1.0.1, openpyxl 3.1.5.

| Check | Result |
| --- | --- |
| Unit regressions | 64 cases: 61 passed; 3 Windows-only cases skipped on macOS. |
| Native Mac startup and folder picker | App launched at the requested size; native folder selection opened a temporary batch copy. Native centring returned successfully. Multi-monitor placement still needs manual verification. |
| Supplied batch copy | All seven image references resolved and two records intentionally had no image. Native preview rendering was inspected. Original batch files were not edited. |
| Native CSV and XLSX review | Saves, navigation, unsaved-edit cancellation, and image previews passed with the real Flutter client. XLSX opened the Catalogue worksheet while Notes was active. |
| Compact and wide layout | Inspected at 640 × 480 and 1000 × 650. Edits survived resizing; scrolling and zoom in/out/reset worked after layout changes. |
| Themes | Light/dark rendering and persistent preference writes passed in the native client. The original preference was restored after testing. |
| Excel 16.114, viewing-only installation | Opened an XLSX fixture and confirmed `0007`, Unicode and multiline text. Excel displayed “Subscription Required to Edit and Save.” After closing the workbook, the GUI catalogue code saved a correction; reopening in Excel displayed it. Excel-originated save/export round trips were not tested because editing is unavailable in this installation. |
| Numbers | Native import/export checks remain pending; Numbers was not available in the local test setup. |
| Windows, Intel Mac, Ubuntu | CI matrix configured. Its remote results and native desktop verification remain pending. |

The scripted native checks invoke the app's event handlers and real client methods. They complement checks through the OS UI; they do not simulate every keyboard, trackpad, window manager, or spreadsheet application.

## Repeatable checks

Use copies of batch folders. Record OS/version, CPU architecture, display scaling, Python/Flet versions, and spreadsheet application/version. On Ubuntu, record the desktop and whether it uses X11 or Wayland; install Zenity for the native folder picker.

1. Run `uv sync --locked`, the unit suite, and `uv run --locked python tests/desktop_smoke.py` in a desktop session.
2. Launch normally with `uv run main.py`. Check initial placement, including an external monitor and a subsequent launch after disconnecting it. Resize to 640 × 480, restore a larger window, and check 100%, 125%, and 150% scaling where supported.
3. Open a batch using the native folder picker. Cancel the picker once, then open CSV and XLSX batches. Confirm the selected filename; when both formats exist, verify only the newer catalogue changes on save.
4. Check a crop image, a missing-image record, a missing file, and a damaged file. Test mouse-wheel/trackpad zoom, dragging, zoom buttons, and Reset / Fit in both layouts.
5. Edit text, add/remove flags, and change reviewed status. Navigate, switch folders, and close with unsaved changes. Exercise Cancel, Save, and Don't save. Confirm cancellation preserves the form. Test discarding a row and the final row using disposable data.
6. Switch themes with unsaved edits, restart, and verify the selected theme persists. Check text, flags, disabled controls, dialogs, and the theme button with keyboard navigation and a screen reader.
7. Exercise a save failure using a locked file on Windows or a non-writable test folder. Confirm the original bytes survive, the form stays editable, no temporary catalogue remains, and retry works after the restriction is removed. Modify the file externally and confirm the GUI refuses to overwrite it.
8. In Excel/Numbers, import fixtures containing Unicode, quoted commas, multiline text, text identifiers with leading zeros, flags, image links, and reviewed values. For CSV, select text import for identifier columns. Close the spreadsheet app, edit/save in the GUI, and reopen to check values. Then export ordinary corrections back to CSV/XLSX and reopen in the GUI. Keep the original headers and image folder alongside the catalogue.
9. Confirm unsafe XLSX row deletion is refused for retained formulas, charts, tables, named ranges, or other dependent ranges, including references on other worksheets. Confirm ordinary corrections and row removal in plain catalogues still work.

## Scope of support

The supported workflow is a generated catalogue with ordinary corrections. Native Numbers files, encrypted workbooks, advanced Excel feature preservation, concurrent spreadsheet editing, and automatic dependency rewriting are outside this workflow. A local Excel licence restriction does not prevent the GUI from writing a file; actual filesystem permissions and locks still apply.
