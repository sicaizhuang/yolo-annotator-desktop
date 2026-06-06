# Product Audit

YOLO Annotator Desktop is intentionally a small, local-first annotation tool. Its
goal is not to reproduce a server platform. It should make the common image
labeling loop fast, predictable, recoverable, and easy to learn.

## Strengths To Preserve

- Opens a portable project directly into the annotation workspace.
- No account, browser, Docker, database, or server is required.
- Edits are saved beside standard YOLO labels.
- Three-point OBB drawing is faster than a generic polygon workflow.
- Class-ID remapping creates backups before destructive changes.

## Resolved In 0.4.0

- Atomic writes, session backups, stale-aware project locks, and crash logs.
- Nested datasets, corrupt-image verification, duplicate checks, issue severity,
  and export protection.
- Image browser, status filters, explicit empty review, move/nudge/copy/paste,
  AABB and OBB resizing, and typing-safe shortcuts.
- Progress-oriented project hub and recent-project state.
- COCO/VOC import and export, COCO OBB round trips, TIFF images, and direct
  project-file startup.

## Remaining Risks And Roadmap

- The annotation window is intentionally lightweight but remains a large Tk
  module; future work should split canvas, dataset state, and commands without
  changing interaction behavior.
- Full quality checks and exports run in background workers, but progress is
  currently indeterminate and jobs cannot yet be cancelled safely.
- The visible interface is currently Simplified Chinese. A translation catalog
  is needed before claiming full internationalization.
- Multi-object selection, polygon/segmentation tasks, video annotation, and
  model-assisted pre-labeling remain outside the current bounding-box scope.
- Exact duplicate images are detected; near-duplicate clustering and
  leakage-aware train/validation grouping remain future dataset-science work.

## Benchmark Lessons

- CVAT separates the canvas, object list, tools, navigation, and settings. It
  also treats review and quality control as explicit workflows.
- Roboflow Annotate uses distinct tool modes, a null/empty-image action, and
  shortcuts optimized for repeated labeling.
- LabelImg remains useful because opening directories, copying boxes, and
  keyboard nudging are immediate and understandable.
- Label Studio emphasizes import/export compatibility and model-assisted
  pre-labeling, but its server setup is intentionally outside this app's scope.

## Product Direction

1. Make every write atomic and every destructive operation recoverable.
2. Add a dataset-oriented project dashboard and recent-project workflow.
3. Add an image browser, review states, status filters, and explicit empty-image review.
4. Add professional box editing: move, nudge, duplicate, copy/paste, and precise geometry.
5. Broaden import/export formats without making the default workflow heavier.
6. Keep the annotation canvas visually quiet and reserve visible controls for
   frequent actions.
7. Verify each release with unit tests, temporary-project GUI smoke tests, the
   real OCG dataset, and a clean public-release audit.
