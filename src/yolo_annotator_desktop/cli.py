from __future__ import annotations

import argparse
import json
from pathlib import Path

from .formats import export_coco, export_pascal_voc
from .presets import CLASS_PRESETS, load_classes_file, parse_class_text
from .project import create_project, create_project_from_folders, create_project_from_yolo_yaml, load_project
from .qc import export_yolo_dataset, inspect_project
from .safe_io import atomic_write_text


def qc_main():
    parser = argparse.ArgumentParser(description="Inspect a YOLO Annotator Desktop project.")
    parser.add_argument("project", help="Path to a .yad.json project")
    parser.add_argument("--output", help="Optional JSON report output path")
    parser.add_argument("--strict", action="store_true", help="Return a non-zero exit code for warnings as well as errors.")
    args = parser.parse_args()
    report = inspect_project(load_project(args.project))
    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)
    if args.output:
        atomic_write_text(Path(args.output), text + "\n")
    failed = report["issue_count"] if args.strict else report["blocking_issue_count"]
    raise SystemExit(1 if failed else 0)


def export_main():
    parser = argparse.ArgumentParser(description="Export a YOLO Annotator Desktop project.")
    parser.add_argument("project", help="Path to a .yad.json project")
    parser.add_argument("output", help="Export destination")
    parser.add_argument("--format", choices=("yolo", "coco", "voc"), default="yolo")
    parser.add_argument("--val-ratio", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    project = load_project(args.project)
    if args.format == "coco":
        result = export_coco(project, Path(args.output))
    elif args.format == "voc":
        result = export_pascal_voc(project, Path(args.output))
    else:
        result = export_yolo_dataset(project, Path(args.output), args.val_ratio, args.seed)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def create_main():
    parser = argparse.ArgumentParser(description="Create a YOLO Annotator Desktop project wrapper.")
    parser.add_argument("workspace", help="New empty project workspace")
    parser.add_argument("--name", default="dataset", help="Project name")
    parser.add_argument("--mode", choices=("detect", "obb"), default="detect", help="Annotation mode")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--yolo-yaml", help="Import a YOLO data.yaml")
    source.add_argument("--images", help="Use an existing image folder")
    parser.add_argument("--split", default="train", help="YOLO YAML split to open")
    parser.add_argument("--labels", default="", help="Existing label folder for --images")
    classes = parser.add_mutually_exclusive_group()
    classes.add_argument("--classes", default="", help="Comma-separated or newline-separated class names")
    classes.add_argument("--classes-file", default="", help="classes.txt, .names, or data.yaml file")
    classes.add_argument("--preset", choices=tuple(CLASS_PRESETS), default="", help="Built-in class preset")
    args = parser.parse_args()

    if args.yolo_yaml:
        project = create_project_from_yolo_yaml(args.workspace, args.yolo_yaml, args.split, args.mode)
    else:
        if args.classes_file:
            names = load_classes_file(args.classes_file)
        elif args.preset:
            names = CLASS_PRESETS[args.preset]
            if not names:
                raise SystemExit("The Custom preset requires --classes or --classes-file.")
        else:
            names = parse_class_text(args.classes or "object")
        if args.images:
            labels = args.labels or str(Path(args.images).resolve().parent / "labels")
            project = create_project_from_folders(args.workspace, args.name, args.images, labels, names, args.mode)
        else:
            project = create_project(args.workspace, args.name, names, args.mode)
    print(json.dumps({"project": str(project.config_path), "mode": project.annotation_mode}, ensure_ascii=False, indent=2))
