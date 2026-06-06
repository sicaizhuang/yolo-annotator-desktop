# Changelog

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
