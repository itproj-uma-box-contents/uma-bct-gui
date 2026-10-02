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

```
uv sync
```

## Usage

> [!NOTE]
> At a later date, we can [package this nicely](https://flet.dev/docs/publish/) so the archivists who use the GUI (who might be different from those who use the CLI) don't have to launch it through the command line anyway.

> [!NOTE]
> The GUI relies on the supplied directory having the structure that the current CLI produces. Changes in the CLI to the structure of the output directory will require (minor) changes to this GUI.

```
uv run uma-bct-gui
```

The GUI opens with nothing loaded. Use the "Open outputs folder" button to pick a CLI outputs directory (one containing `catalogue.csv`) through the OS folder picker.