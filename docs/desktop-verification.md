# Desktop verification

## Recorded checks — 16–18 October 2026

Local environment: Apple Silicon, macOS 26.4, Python 3.12.13, Flet/desktop 1.0.4, openpyxl 3.1.5. The 16–17 October checks used Flet/desktop 1.0.1.

| Check | Result |
| --- | --- |
| Unit regressions | 104 cases: 101 passed; 3 Windows-only cases skipped on macOS. Includes queued button/close events, inactive-record actions, lossless numeric edits, oversized XLSX text, long CSV fields, read-only files, malformed workbooks, nonregular image paths, and short-window layouts. |
| Native Mac startup and folder picker, 16 October | App launched at the requested size; native folder selection opened a temporary batch copy. Native centring returned successfully. Multi-monitor placement still needs manual verification. |
| Supplied batch copy | All seven image references resolved and two records intentionally had no image. Native preview rendering was inspected. Original batch files were not edited. |
| Native CSV and XLSX review | Saves, navigation, unsaved-edit cancellation, and image previews passed with the real Flutter client. XLSX opened the Catalogue worksheet while Notes was active. |
| Compact and wide layout | Inspected at 640 × 480 and 1000 × 650. Edits survived resizing; scrolling and zoom in/out/reset worked after layout changes. |
| Extended layout audit, 18 October | The smoke test covers outer window sizes 640 × 360, 1000 × 360, 700 × 900, 1400 × 500, 640 × 480, and 1000 × 650. Completed runs on 1.0.1 exercised scrolling, long headings/tooltips, long dialogs, retained edits, and image methods. Repeated verification on 1.0.4 remains intermittent; see the limitation below. |
| Themes | Light/dark rendering and persistent preference writes passed in the native client. The original preference was restored after testing. |
| Keyboard and catalogue-open additions | Unit checks cover Prev/Next ordering, boundaries, typing focus, modifiers, menus/picker/dialogs, failed saves, active XLSX selection, opening saved data without discarding edits, and duplicate-click protection. Native CSV/XLSX smoke checks passed through the normal launcher, exercising the keyboard handler with actual field focus and the scheduled open action through a test opener. Physical keyboard input still needs the OS checks below. |
| macOS file opener, 17 October | The real native helper successfully handed disposable CSV and XLSX paths to macOS. The exact XLSX appeared in Excel's recent files and was opened for inspection in viewing mode. CSV contents in its default app were not visually verified. |
| macOS launch verification, 17 October | Corrected the smoke driver to enable screenshot support before client registration, avoiding a change to the wrapper around live controls. Removed its preference read before production startup. Three consecutive runs passed normal startup and loaded-field focus without screenshots, followed by full CSV/XLSX checks with screenshots. The stock LaunchServices launcher is used throughout; the earlier launcher limitation is resolved in these checks. |
| Excel 16.114, viewing-only installation | Opened an XLSX fixture and confirmed `0007`, Unicode and multiline text. Excel displayed “Subscription Required to Edit and Save.” After closing the workbook, the GUI catalogue code saved a correction; reopening in Excel displayed it. Excel-originated save/export round trips were not tested because editing is unavailable in this installation. |
| Numbers | Native import/export checks remain pending; Numbers was not available in the local test setup. |
| Cross-platform unit CI | [CI run 39024927631](https://github.com/itproj-uma-box-contents/uma-bct-gui/actions/runs/39024927631) passed at commit `618f38e` on Windows, Ubuntu, Intel Mac, and Apple Silicon Mac. The current audit changes require a new CI run after pushing. Native desktop verification on Windows, Intel Mac, and Ubuntu remains pending. |

### Remaining automated native-test limitation

Repeated Mac smoke runs can leave the rendered window on an earlier screen, followed by a field-focus timeout or a detached scroll-controller error. This also reproduced against an exported copy of committed `452727e` with the same runtime. Successful and failing runs emitted the same catalogue-load state; independent real Flet session/MessagePack checks retained the correct control IDs. Direct-client launches, startup waits, and isolated source changes did not make the full test repeatable. No speculative production workaround was retained. The user reports normal use works. This remains an automated native-verification gap, not a passing desktop result or an established root cause.

The lockfile now uses stable Flet/desktop 1.0.4. Its [official changelog](https://github.com/flet-dev/flet/blob/v1.0.4/packages/flet/CHANGELOG.md) includes child-control identity fixes and a desktop monitor-brightness dependency fix. The update alone did not resolve the intermittent test failure.

The smoke driver now puts a 90-second deadline around each asynchronous launch, cleans up only the client it captured, and saves a diagnostic screenshot on review-phase failure. Cold startup remains screenshot-free. Flet's synchronous first-use client download is outside that asynchronous deadline; prepare the cached client while online first.

The scripted native checks invoke the app's event handlers and real client methods. They complement checks through the OS UI; they do not simulate every keyboard, trackpad, window manager, or spreadsheet application. Tests of the Windows/macOS/Linux opener branches use mocked native calls; they do not establish that another operating system's app associations are configured correctly. Computer Use could select or open disconnected Flet instances during interactive checks, so no physical-keyboard pass is claimed from those attempts.

Three separate audits covered layout, interaction state, and catalogue/file handling; a fresh final auditor implemented confirmed findings, followed by independent code and Python reviews. Native resize checks observe the root's post-layout size event before using scroll controllers; the earlier window-resize event alone did not establish that a new scroll wrapper was attached. Measurements use client logical pixels without applying display scaling a second time. Native window frames and file pickers retain each operating system's appearance.

The current Flet API does not expose the monitor work area, so automatic fitting to every scaled desktop or monitor configuration is not claimed. The smaller minimum height and whole-page scrolling support short workspaces; multi-monitor startup placement and 125–200% scaling still need checks on the target systems.

## Repeatable checks

Use copies of batch folders. Record OS/version, CPU architecture, display scaling, Python/Flet versions, and spreadsheet application/version. On Ubuntu, record the desktop and whether it uses X11 or Wayland; install Zenity for the native folder picker and xdg-utils for opening catalogues.

1. Run `uv sync --locked`, the unit suite, and `uv run --locked python tests/desktop_smoke.py` in a desktop session.
2. Launch normally with `uv run main.py`. Check initial placement, including an external monitor and a subsequent launch after disconnecting it. Resize to 640 × 320 and 1000 × 360, then portrait and wide windows, and restore 1000 × 650. Scroll to the action buttons and back. Check 100%, 125%, 150%, and 200% scaling where supported, including long headings and dialogs.
3. Open a batch using the native folder picker. Cancel the picker once, then open CSV and XLSX batches. Confirm the selected filename; when both formats exist, verify only the newer catalogue changes on save.
4. Check a crop image, a missing-image record, a missing file, and a damaged file. Test mouse-wheel/trackpad zoom, dragging, zoom buttons, and Reset / Fit in both layouts.
5. Edit text, add/remove flags, and change reviewed status. Navigate, switch folders, and close with unsaved changes. Exercise Cancel, Save, and Don't save. Confirm cancellation preserves the form. Test rapid repeated navigation/discard/close actions and verify a confirmation never changes target. After deleting the last row, verify queued Save/discard actions are harmless.
6. Switch themes with unsaved edits, restart, and verify the selected theme persists. Check text, flags, disabled controls, dialogs, and the theme button with keyboard navigation and a screen reader.
7. Exercise a save failure using a locked file on Windows or a non-writable test folder. Confirm the original bytes survive, the form stays editable, no temporary catalogue remains, and retry works after the restriction is removed. Modify the file externally and confirm the GUI refuses to overwrite it.
8. In Excel/Numbers, import fixtures containing Unicode, quoted commas, multiline text, text identifiers with leading zeros, flags, image links, and reviewed values. For CSV, select text import for identifier columns. Close the spreadsheet app, edit/save in the GUI, and reopen to check values. Then export ordinary corrections back to CSV/XLSX and reopen in the GUI. Keep the original headers and image folder alongside the catalogue.
9. Confirm unsafe XLSX row deletion is refused for retained formulas, charts, tables, named ranges, or other dependent ranges, including references on other worksheets. Confirm ordinary corrections and row removal in plain catalogues still work.
10. Press Left/Right outside a text field and confirm the record follows Prev/Next, including image-less records and boundaries. In a text field, confirm arrows move the cursor and do not change records. Check modifier combinations, an open flag menu, the folder picker, and a confirmation dialog. Cancel or fail a save during keyboard navigation and confirm the current record and edits remain intact.
11. Use Open catalogue with active CSV and XLSX files, including folders with spaces and Unicode. Exercise Save and open, Open saved version, and Cancel. Confirm the expected file opens in the default app, the saved version does not discard GUI edits, failed saves do not open a file, and missing files/apps show a recoverable error. Check a catalogue with no records or all records reviewed, and confirm repeated clicks during opening do not launch duplicate applications.
12. Save and reopen long CSV fields and XLSX corrections containing leading zeros, long identifiers, and literal `NaN`/`Infinity` text. Attempt an oversized XLSX edit and verify the original bytes and form edits survive. Open malformed workbooks and nonregular image paths using disposable fixtures; errors must be recoverable without losing the previous form. Make a catalogue read-only, verify Save refuses it, restore write access, and retry.

## Scope of support

The supported workflow is a generated catalogue with ordinary corrections. Native Numbers files, encrypted workbooks, advanced Excel feature preservation, concurrent spreadsheet editing, and automatic dependency rewriting are outside this workflow. A local Excel licence restriction does not prevent the GUI from writing a file; actual filesystem permissions and locks still apply.
