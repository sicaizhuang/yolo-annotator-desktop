# Architecture

YOLO Annotator Desktop is a small local application. It deliberately stores
standard files rather than introducing a database or server.

## Main Boundaries

- `app.py`: project hub and application entry workflow.
- `annotator.py`: interactive canvas, image navigation, and annotation commands.
- `project.py`: portable project configuration and import conversion.
- `qc.py`: dataset inspection and YOLO train/validation export.
- `formats.py`: COCO JSON and Pascal VOC interchange.
- `safe_io.py`: atomic text and JSON replacement.
- `state.py`: recent projects and user preferences.
- `diagnostics.py`: callback crash logging.

## Data Safety Rules

1. Source images are never modified.
2. Labels and configuration are replaced atomically.
3. The first modified label in a session is backed up.
4. Class-ID remapping creates a complete backup first.
5. Malformed label rows are preserved during interactive editing.
6. Blocking quality issues prevent export.
7. Export destinations cannot live inside source image or label directories.

## Compatibility

Projects use portable `.yad.json` files and standard YOLO Detect or YOLO OBB
text labels. Import/export adapters support YOLO YAML, COCO JSON, and Pascal VOC
XML. Nested image folders mirror into nested label folders.

## Testing Strategy

Pure data behavior is covered by `unittest`. Release verification also includes
syntax compilation, GUI smoke tests on temporary projects, a full quality check
of the production OCG dataset, and a public-release archive audit.
