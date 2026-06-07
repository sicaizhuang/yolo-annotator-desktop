# Changelog

## 0.5.0 - 2026-06-07

- Expanded project modes beyond Detect/OBB to include YOLO Segmentation, YOLO Pose, and YOLO Classification.
- Added a shared label-format layer for Detect, OBB, Segment polygon, Pose keypoint, and image-class labels.
- Added polygon segmentation drawing: click points, press Enter or click the first point to finish, drag vertices to refine.
- Added pose workflow: draw a box, switch to keypoint mode, then place configured keypoints in order.
- Added classification workflow where the current class can be assigned to the whole image.
- Updated quality checks to validate segment polygons, pose keypoints, classification labels, duplicate annotations, and mixed task formats.
- Added YOLO classification export using train/val class folders.
- Added `kpt_shape` output for pose `data.yaml` exports when keypoints are configured.
- Added COCO segmentation polygon import/export support and clearer VOC export rejection for non-rectangle tasks.
- Made class remapping format-agnostic so class changes work safely across Detect, OBB, Segment, Pose, and Classify labels.
- Added toolbar/menu entries for polygon and keypoint tools.
- Added tests for segmentation, pose, and classification projects.

## 0.4.1 - 2026-06-07

- Added built-in class presets for single-object, COCO 80, Pascal VOC 20, electronics starter, and defect-detection starter projects.
- Added class loading from `classes.txt`, `.names`, and YOLO `data.yaml` files in the project wizard.
- Reworked the dataset wizard as a more general import hub with clearer source choices and task-mode settings.
- Added YOLO `data.yaml` support for image-list TXT splits such as `train: train.txt`.
- Added YOLO `data.yaml` support for split lists with multiple image directories or image-list files.
- Added `yad-create` for scriptable project creation from empty workspaces, folders, class presets/files, or YOLO YAML.
- Added tests for class helpers, image-list YAML imports, and multi-directory YAML imports.

## 0.4.0 - 2026-06-07

- Redesigned the project hub around review progress, dataset metrics, recent projects, and common actions.
- Added a searchable/filterable image browser, scrollable class browser, hideable side panels, and a selected-object list.
- Added select/move mode, arrow-key nudging, copy/paste/duplicate, AABB handles, and rectangular OBB corner resizing.
- Added explicit reviewed-empty images, cursor-centered zoom, actual-pixel view, and natural image sorting.
- Made project, state, label, report, and export writes atomic; added session label backups and stale-aware project locks.
- Preserves malformed label rows during editing instead of silently discarding them.
- Added centralized crash logging and visible callback error reporting.
- Added full image decode checks, duplicate image/box detection, unused-class warnings, issue severities, and safer export blocking.
- Added nested image/label layouts and TIFF images.
- Added COCO JSON and Pascal VOC import/export, including COCO OBB round trips.
- Added project creation from empty folders, existing folders, YOLO YAML, COCO JSON, and Pascal VOC XML.
- Added deterministic YOLO export controls and protected source directories from accidental export pollution.
- Added direct project-file startup, macOS Command shortcuts, and a broader automated test suite.
- Moved full quality checks and exports to background workers so the interface remains responsive.
- Fixed single-image export so the only image remains in the training split.
- Added a quiet Windows launcher and an optional desktop-shortcut creator.

## 0.1.0 - 2026-06-07

- First open-source-ready release.
- Added project hub and portable `.yad.json` projects.
- Preserved the production-tested annotation interaction model.
- Added safe class management with backup and label-ID remapping.
- Added dataset quality checks.
- Added deterministic YOLO train/validation export.
- Added English and Simplified Chinese documentation.

## 0.2.0 - 2026-06-07

- Reworked the annotation window into a compact icon toolbar with hover tooltips and collapsible low-frequency actions.
- Added custom classes directly from the annotation workspace.
- Added three-point rotated rectangle drawing and standard YOLO OBB read/write support.
- Added dataset creation methods for empty projects, existing folders, and existing YOLO `data.yaml` splits.
- Added project-level Detect/OBB annotation type and blocked invalid mixed-format export.
- Opening a project directly now enters the annotation workspace instead of the project hub.

## 0.3.0 - 2026-06-07

- Added familiar File, Edit, View, Annotation, Dataset, and Help menus.
- Replaced font-dependent toolbar symbols with clear bitmap icons and hover explanations.
- Added direct actions for opening projects, image folders, label folders, and class files.
- Added quality check and YOLO export actions directly inside the annotation workspace.
- Simplified the toolbar so frequent actions stay visible and less-used actions live in menus.
