from __future__ import annotations

import argparse
import json
from pathlib import Path

from .project import load_project
from .qc import export_yolo_dataset, inspect_project


def qc_main():
    parser = argparse.ArgumentParser(description="Inspect a YOLO Annotator Desktop project.")
    parser.add_argument("project", help="Path to a .yad.json project")
    parser.add_argument("--output", help="Optional JSON report output path")
    args = parser.parse_args()
    report = inspect_project(load_project(args.project))
    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    raise SystemExit(1 if report["issue_count"] else 0)


def export_main():
    parser = argparse.ArgumentParser(description="Export a YOLO Annotator Desktop project.")
    parser.add_argument("project", help="Path to a .yad.json project")
    parser.add_argument("output", help="Export destination")
    parser.add_argument("--val-ratio", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    result = export_yolo_dataset(load_project(args.project), Path(args.output), args.val_ratio, args.seed)
    print(json.dumps(result, ensure_ascii=False, indent=2))
