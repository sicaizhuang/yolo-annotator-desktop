# YOLO Annotator Desktop

Desktop YOLO annotation tool for object detection, oriented bounding boxes
(OBB), segmentation, pose keypoints, and image classification datasets.

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](pyproject.toml)
[![YOLO formats](https://img.shields.io/badge/YOLO-detect%20%7C%20OBB%20%7C%20segment%20%7C%20pose%20%7C%20classify-orange.svg)](#supported-yolo-tasks)

[简体中文](README_zh-CN.md) | [Documentation site](https://sicaizhuang.github.io/yolo-annotator-desktop/)

YOLO Annotator Desktop is a fast, local-first image labeling app for building
YOLO datasets without Docker, a browser service, an account, or uploading
private images. It supports YOLO TXT import/export, `data.yaml` project import,
COCO/VOC helpers, quality checks, class remapping, autosave, undo/redo, and
project backups.

It grew out of a real electronic-component sorting project where annotation speed,
safe autosave, precise box editing, and offline operation mattered more than a
large web platform.

## Why Use It

- Local desktop workflow for private datasets and offline labeling.
- One app for YOLO detection, OBB, segmentation, pose, and classification.
- Simple project wrapper around ordinary image folders, label folders, and class files.
- Built-in quality checks before sending data to training.
- Safer editing: atomic saves, backups, undo/redo, and preserved malformed rows.

## Supported YOLO Tasks

| Task | Label shape | Status |
|---|---|---|
| Detection | `class x_center y_center width height` | Supported |
| OBB / rotated boxes | `class x1 y1 x2 y2 x3 y3 x4 y4` | Supported |
| Segmentation | `class x1 y1 x2 y2 ...` polygon rows | Supported |
| Pose | box plus keypoints and `kpt_shape` export | Supported |
| Classification | image-level class folders on export | Supported |

## Install

From a release wheel:

```powershell
py -m pip install yolo_annotator_desktop-0.5.0-py3-none-any.whl
yolo-annotator-desktop
```

From source:

```powershell
git clone https://github.com/sicaizhuang/yolo-annotator-desktop.git
cd yolo-annotator-desktop
py -m pip install -e .
yolo-annotator-desktop
```

## Features

- Native local desktop UI with no Docker, browser, account, database, or server.
- Searchable image browser with reviewed/labeled/empty filters and explicit reviewed-empty images.
- Draw, select, move, resize, nudge, reclassify, copy, paste, and duplicate YOLO boxes.
- Three-point rotated rectangles with rectangular corner resizing and standard YOLO OBB storage.
- Polygon segmentation labels using standard YOLO segmentation TXT rows.
- Pose projects with box-plus-keypoint labels and `kpt_shape` export.
- Image classification projects with class-folder YOLO export.
- Atomic autosave, undo/redo, session backups, stale-aware project locks, and crash logs.
- Malformed label rows are preserved during editing instead of silently discarded.
- Portable `.yad.json` projects and nested image/label directory support.
- Create or import projects from folders, YOLO `data.yaml`, COCO JSON, and Pascal VOC XML.
- YOLO YAML imports support directory splits, image-list TXT splits, and multi-directory split lists.
- Built-in class presets include single-object, COCO 80, Pascal VOC 20, electronics starter, and defect-detection starter classes.
- Classes can be typed manually or loaded from `classes.txt`, `.names`, or YOLO `data.yaml`.
- Export YOLO train/validation datasets, COCO JSON, or Pascal VOC XML.
- Quality checks cover corrupt images, invalid geometry/classes, mixed formats, duplicate boxes/images, orphan labels, and unused classes.
- Blocking errors and non-blocking warnings are reported separately.
- Safe class add/rename/delete/reorder with complete backups and ID remapping.
- Supports JPG, JPEG, PNG, BMP, WebP, TIFF, and nested datasets.

## Windows Quick Start

Double-click `run_windows.cmd`. On first launch it creates a local virtual
environment and installs the runtime dependencies.

After the first launch, double-click `launch_windows.vbs` for a quiet desktop
start. Run `create_desktop_shortcut.cmd` once to add a desktop shortcut.

Or run manually:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m yolo_annotator_desktop
```

Open a project directly:

```powershell
.\.venv\Scripts\python.exe -m yolo_annotator_desktop path\to\project.yad.json
```

Create a project from the command line:

```powershell
# Empty managed dataset with COCO classes
.\.venv\Scripts\yad-create.exe D:\datasets\my_project --preset "COCO 80"

# Existing image and label folders
.\.venv\Scripts\yad-create.exe D:\datasets\wrapped --images D:\data\images --labels D:\data\labels --classes-file D:\data\classes.txt

# YOLO data.yaml, including train.txt image lists and multi-directory splits
.\.venv\Scripts\yad-create.exe D:\datasets\from_yaml --yolo-yaml D:\data\data.yaml --split train
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
  "annotation_mode": "detect",
  "keypoints": "",
  "version": 1
}
```

Paths may be relative to the project file or absolute. Labels use standard YOLO
text format:

```text
class_id x_center y_center width height
```

All coordinates are normalized to `0..1`.

Rotated rectangles use standard YOLO OBB format:

```text
class_id x1 y1 x2 y2 x3 y3 x4 y4
```

Segmentation polygons use standard YOLO segmentation format:

```text
class_id x1 y1 x2 y2 x3 y3 ...
```

Pose labels use Ultralytics-style box plus keypoints:

```text
class_id x_center y_center width height kpt_x kpt_y visible ...
```

Classification projects store one class ID per image in the project labels and
export to the usual YOLO classification folder layout.

## Import Sources

The app always creates or opens a `.yad.json` project wrapper, but the source can
be many things:

- Empty managed workspace.
- Existing image folder, with optional existing labels.
- YOLO `data.yaml` with `train`, `val`, or `test` pointing to one directory.
- YOLO `data.yaml` where a split points to an image-list TXT file.
- YOLO `data.yaml` where a split is a list of directories and/or image-list TXT files.
- COCO JSON plus an image root.
- Pascal VOC XML folder plus an image root.

When importing external data, source images are kept in place. For image-list
and multi-directory YAML splits, the project writes a small local order file so
only the selected split is shown.

## Controls

| Action | Control |
|---|---|
| Select/move | `V`; drag a selected box |
| Draw box | `B`; left-drag anywhere on the image |
| Standard rectangle mode | `B` or the rectangle toolbar icon |
| Three-point rotated rectangle | `R` or the rotated-rectangle toolbar icon; drag first edge, release, move to set width, click |
| Polygon segmentation | `P`; click vertices, press `Enter` or click the first point to finish |
| Pose keypoints | Draw/select a pose box, press `K`, then click keypoints in order |
| Select box | Left-click box, right-click box, or use list |
| Resize selected box | Drag white handles, including OBB corners |
| Nudge selected box | Arrow keys; hold `Shift` for 10 pixels |
| Copy / paste / duplicate | `Ctrl+C` / `Ctrl+V` / `Ctrl+D` |
| Pan | Right-drag or middle-drag |
| Zoom | Mouse wheel |
| Previous / next | `A` / `D`; arrow keys navigate when no box is selected |
| Next unreviewed | `U` |
| Mark reviewed empty | `N` |
| Reclassify selected box | Choose class, then `C` |
| Undo / redo | `Ctrl+Z` / `Ctrl+Y` |
| Hide labels | `H` |
| Save | `Ctrl+S` |
| Delete selected | `Delete` |

## Safety

Labels, projects, preferences, and reports use atomic writes. The first edit to
each label in a session creates a recovery copy. Class-ID changes create a
complete backup before remapping. Export never edits source images or labels and
refuses destinations inside source image/label folders.

## Development

```powershell
py -m pip install -e .
py -m unittest discover -s tests -v
```

See [CONTRIBUTING.md](CONTRIBUTING.md) before submitting changes.

## Search Keywords

YOLO annotation tool, YOLO labeling tool, YOLO dataset editor, bounding box
annotation, rotated bounding box annotation, OBB labeling, image segmentation
annotation, pose keypoint annotation, classification dataset tool, COCO to YOLO,
Pascal VOC to YOLO, Ultralytics YOLO dataset, local image annotation.

## License

MIT
