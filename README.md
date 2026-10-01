# UMA Box Contents Transcription Review GUI

This repository provides a graphical user interface for manually reviewing the outputs of the [UMA Box Contents Transcription CLI](https://github.com/itproj-uma-box-contents/uma-bct-cli).

It is based on the lofi mockup [in Confluence](https://uma-box-contents.atlassian.net/wiki/x/AQC_/).

The GUI has one page only. It is shown in the following screenshot:

![Screenshot of the UMA BCT GUI](./screenshot.png)

It also allows users to zoom in on the image as shown

![Screenshot of the UMA BCT GUI with zoom engaged](./screenshot-zoomed-in.png)


## Why is this a separate repository?

The GUI has been separated completely from the CLI because of how the client intends to use the software. Recall that the client has mentioned that the main purpose of the GUI is for speeding up the process of manually reviewing the program's outputs. Due to how long the solution takes to run, it's unlikely that this manual review process will start as soon as transcription finishes. Therefore, it doesn't really make sense for the reviewing component of the solution to run in the same process as the transcription component, or for these two components to share an interface.

I also thought about adding another module into the existing repository rather than creating a brand new one, but due to the very different dependencies of the two parts of the project (this GUI depends only on the `flet` package, which is not needed for the CLI, and the CLI has 7 dependencies, none of which are necessary for this), I think having this as a completely separate repository makes the most sense. The archivists could all have this GUI on their own computers (without having to install the CLI, Ollama, or the Qwen model), and everything else could just run on the workstations that are already set up in the archives.

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