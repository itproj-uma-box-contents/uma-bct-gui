# UMA Box Contents Transcription Review GUI

This repository provides a graphical user interface for manually reviewing the outputs of the [UMA Box Contents Transcription CLI](https://github.com/itproj-uma-box-contents/uma-bct-cli).

It is based on the lofi mockup [in Confluence](https://uma-box-contents.atlassian.net/wiki/x/AQC_/).

The GUI has one page only. It is shown in the following screenshot:

![Screenshot of the UMA BCT GUI](./screenshot.png)

It also allows users to zoom in on the image as shown

![Screenshot of the UMA BCT GUI with zoom engaged](./screenshot-zoomed-in.png)

The following screenshot (of the "Add flag" menu) shows the flags available and the colour-coding used:

![Screenshot of the UMA BCT GUI's "Add flag" menu](./flag-colour-coding.png)

## Setup

Use Python 3.12 or newer. Normal setup includes Flet desktop support and Excel file support:

```
uv sync --locked
```

The first launch may download the native Flet client from GitHub if it is not already available locally. Complete that first launch while online before using the app offline.

On Ubuntu desktop, the native folder picker needs Zenity, and opening a catalogue in another app uses `xdg-open` from `xdg-utils`:

```
sudo apt install zenity xdg-utils
```

## Usage

> [!NOTE]
> At a later date, we can [package this nicely](https://flet.dev/docs/publish/) so the archivists who use the GUI (who might be different from those who use the CLI) don't have to launch it through the command line anyway.

> [!NOTE]
> The GUI relies on the supplied directory having the structure that the current CLI produces. Changes in the CLI to the structure of the output directory will require (minor) changes to this GUI.

```
uv run main.py
```

For development with hot reloading, install the matching Flet CLI (`uv pip install "flet-cli==1.0.1"`) and use `uv run --no-sync flet run`.

An installed package can also be launched with `uma-bct-gui`.

The GUI opens centred at 1000 × 650 with nothing loaded. Use the "Open outputs folder" button to pick a CLI outputs directory through the OS folder picker. Names such as `catalogue.csv`, `Catalogue.csv`, and `CATALOGUE.XLSX` are recognised on every platform. If both formats exist, the newest is used (CSV wins a timestamp tie). The selected filename appears above the form; only that file is updated. Keep only one catalogue of each format in a folder.

The sun/moon button switches between light and dark mode. The first launch follows the OS theme, and subsequent launches remember your choice. The window is resizable down to 640 × 480; narrow windows stack the form and preview in a scrollable area.

Unsaved changes are checked before moving between records, opening another folder, or closing the window. Failed saves keep your edits available to retry. If another program changes the catalogue, the app asks you to reopen the folder rather than overwrite those changes.

Use the image's Zoom in, Zoom out and Reset / Fit buttons, or scroll to zoom and drag to pan. The status shows reviewed and remaining counts. If every record is reviewed when a folder opens, use "View records" to revisit them.

Use the **Left/Right arrow keys** to move through records in the same order as Prev/Next, including records without images. Navigation stops at the first and last records. Arrows keep their normal editing behavior while a text field is focused; modified arrow shortcuts and keys used in menus, dialogs, or the folder picker do not navigate records. Unsaved edits still trigger the usual save prompt.

The **Open catalogue** button opens the active CSV or XLSX in your system's default app. If you have unsaved edits, choose **Save and open**, **Open saved version**, or **Cancel**. Opening the saved version keeps unsaved GUI edits available. A failed save prevents opening, and an opening failure leaves the form available to retry. Close the spreadsheet app before continuing GUI edits; external file changes still require reopening the folder.

Image links can be relative paths, local file URLs, native Excel hyperlinks, or `HYPERLINK` formulas with literal file paths. Keep the catalogue and its `Box Images` directory together when moving a batch between computers. Windows path separators are accepted. An absolute path to a drive on another computer cannot be relocated automatically. Missing-box suggestions can legitimately have no image.

### Excel and Apple Numbers

The GUI reads and writes CSV and XLSX directly. **Excel does not need to be installed or licensed for editing.** An Excel installation that only permits viewing does not prevent the GUI from saving a writable local catalogue. Actual file permissions and file locks still apply.

Close the catalogue in Excel or Numbers before editing it in the GUI. Reopen it afterward to see saved changes. If saving fails, your current edits stay in the form: close the other application, check write permissions or storage space, and retry Save. An external edit requires reopening the folder; automatic merging is not supported. Both file formats are saved to a temporary file beside the original before replacement.

- **CSV:** use comma-separated UTF-8 files. Saves include a BOM so Excel recognises Unicode text. Readable `Reviewed` values include `TRUE`, `FALSE`, `1`, `0`, and blanks; unexpected values produce an error. CSV carries no cell-type metadata: import identifier columns as **Text** in Excel/Numbers to retain leading zeros. Spreadsheet apps may interpret text beginning with `=` as a formula; use text import or XLSX for literal transcription text. Existing image-link formulas are preserved when the GUI saves.
- **XLSX:** the `Catalogue` worksheet is selected when present, even if another tab was active when the file was saved. Otherwise the active worksheet is used. Ordinary corrections preserve existing cell types, formatting, comments, other worksheets, and image hyperlinks. Newly written reviewed values are Boolean cells. Protected worksheets must be unprotected in the spreadsheet application before GUI saves.
- **Numbers:** import a CSV or XLSX catalogue, and export back to one of those formats before reopening it in the GUI. Native `.numbers` files are not supported. Keep one table of catalogue records with its original column headings and image links.

These workflows cover generated catalogues with ordinary corrections. For workbooks containing formulas, tables, charts, merged cells, filters, or other dependent ranges, removal of records may require Excel or Numbers. The GUI refuses unsafe row deletion; it does not rewrite spreadsheet dependencies. Advanced workbook features are not guaranteed to survive openpyxl round trips—use a plain catalogue copy for files containing unsupported Excel features.

The older `uv run --extra excel main.py` command still works, but the extra is no longer required.

## Tests

```
uv run --locked python -m unittest discover -s tests -v
```

GitHub Actions is configured to run the suite on Ubuntu 24.04, Windows Server 2025, Intel macOS 15, and Apple Silicon macOS 26 with Python 3.12. Windows-only tests exercise native file locking and drive/share paths. Unit tests use real Flet controls with a test page; they do not verify native rendering or OS folder pickers.

To run the separate native rendering smoke test on a machine with a desktop session:

```
uv run --locked python tests/desktop_smoke.py
```

It opens and closes a test window, uses disposable CSV/XLSX fixtures, restores the original theme preference, and checks resizing, scrolling, image methods, arrow-handler behavior, native field focus, editing, saves, and the catalogue-open action. The native folder picker and external application opener are stubbed in this test and need the manual checks below.

Desktop verification targets Windows 11, Intel and Apple Silicon Macs, and Ubuntu desktop. The repeatable manual checks and recorded results are in [desktop verification](docs/desktop-verification.md).
