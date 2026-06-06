from __future__ import annotations

import argparse
import json
from pathlib import Path

from .formats import export_coco, export_pascal_voc
from .project import load_project
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
