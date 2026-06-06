# YOLO Annotator Desktop

A fast, local-first desktop bounding-box annotator for YOLO datasets.

It grew out of a real electronic-component sorting project where annotation speed,
safe autosave, precise box editing, and offline operation mattered more than a
large web platform.

## Features

- Native desktop UI with no Docker, browser, account, or server.
- Draw, select, resize, reclassify, and delete YOLO bounding boxes.
- Autosave after every edit.
- Undo/redo, zoom around cursor, right-drag pan, and hideable labels.
- Jump to an image or move directly to the next unreviewed image.
- Portable `.yad.json` project files.
- Safe class add/rename/delete/reorder with label backup and ID remapping.
- Dataset quality checks for invalid labels, bounds, orphan labels, and duplicate stems.
- Deterministic train/validation export with a ready-to-use `data.yaml`.
- Supports JPG, JPEG, PNG, BMP, and WebP.

## Windows Quick Start

Double-click `run_windows.cmd`. On first launch it creates a local virtual
environment and installs the only runtime dependency, Pillow.

Or run manually:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m yolo_annotator_desktop
```

## Project Format

Each project uses a small JSON file:

```json
{
  "name": "example",
  "images": "images",
  "labels": "labels",
  "classes": "classes.txt",
  "keep_empty": true,
  "order_file": "",
  "filter_order": false,
  "version": 1
}
```

Paths may be relative to the project file or absolute. Labels use standard YOLO
text format:

```text
class_id x_center y_center width height
```

All coordinates are normalized to `0..1`.

## Controls

| Action | Control |
|---|---|
| Draw box | Left-drag empty image area |
| Select box | Left-click box, right-click box, or use list |
| Resize selected box | Drag white handles |
| Pan | Right-drag |
| Zoom | Mouse wheel |
| Previous / next | `A` / `D` or arrow keys |
| Next unreviewed | `U` |
| Reclassify selected box | Choose class, then `C` |
| Undo / redo | `Ctrl+Z` / `Ctrl+Y` |
| Hide labels | `H` |
| Save | `Ctrl+S` |
| Delete selected | `Delete` |

## Safety

The class manager creates a complete label-folder backup before changing class
IDs. Dataset export never edits source images or labels.

## Development

```powershell
py -m pip install -e .
py -m unittest discover -s tests -v
```

See [CONTRIBUTING.md](CONTRIBUTING.md) before submitting changes.

## License

MIT
