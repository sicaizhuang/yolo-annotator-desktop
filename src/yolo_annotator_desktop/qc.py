from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import shutil

from PIL import Image, UnidentifiedImageError

from .label_formats import infer_label_mode, parse_label_line
from .project import ProjectConfig
from .safe_io import atomic_write_text


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}
IGNORED_DIR_NAMES = {".git", ".yad_backups", "__pycache__"}
EXPORT_BLOCKING_ISSUES = {
    "mixed_annotation_formats",
    "annotation_mode_mismatch",
    "corrupt_image",
    "invalid_columns",
    "invalid_number",
    "invalid_class",
    "invalid_bounds",
    "box_outside_image",
    "obb_point_outside_image",
    "degenerate_obb",
    "degenerate_polygon",
    "invalid_keypoint_bounds",
    "invalid_keypoint_visibility",
    "duplicate_label_target",
    "exact_duplicate_box",
}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def find_images(image_dir: Path) -> list[Path]:
    return [
        path
        for path in sorted(image_dir.rglob("*"))
        if path.is_file()
        and path.suffix.lower() in IMAGE_EXTS
        and not any(
            part.startswith(".") or part in IGNORED_DIR_NAMES
            for part in path.relative_to(image_dir).parts[:-1]
        )
    ]


def inspect_project(project: ProjectConfig, verify_images: bool = True) -> dict:
    classes = project.class_names()
    images = find_images(project.image_dir)
    expected_label_paths = Counter(str(project.label_path_for(path, prefer_existing=False).resolve()) for path in images)
    label_files = sorted(project.label_dir.rglob("*.txt"))
    class_counts = Counter()
    format_counts = Counter()
    issues: list[dict] = []
    labeled = empty = 0
    image_sizes = Counter()
    image_hashes: dict[str, Path] = {}

    for label_path, count in expected_label_paths.items():
        if count > 1:
            issues.append({"type": "duplicate_label_target", "file": label_path, "detail": f"{count} images map to this label"})

    for image in images:
        if verify_images:
            try:
                with Image.open(image) as source:
                    source.verify()
                with Image.open(image) as source:
                    image_sizes[f"{source.width}x{source.height}"] += 1
                digest = file_sha256(image)
                if digest in image_hashes:
                    issues.append(
                        {
                            "type": "duplicate_image_content",
                            "file": str(image),
                            "detail": f"Exact duplicate of {image_hashes[digest]}",
                        }
                    )
                else:
                    image_hashes[digest] = image
            except (OSError, UnidentifiedImageError) as exc:
                issues.append({"type": "corrupt_image", "file": str(image), "detail": str(exc)})
        label = project.label_path_for(image)
        if not label.exists():
            continue
        text = label.read_text(encoding="utf-8-sig").strip()
        if not text:
            empty += 1
            continue
        labeled += 1
        seen_boxes = set()
        image_size = None
        if verify_images:
            try:
                with Image.open(image) as source:
                    image_size = source.size
            except (OSError, UnidentifiedImageError):
                image_size = None
        for line_number, line in enumerate(text.splitlines(), 1):
            parts = line.split()
            detected_mode = infer_label_mode(parts, project.annotation_mode)
            parsed, error = parse_label_line(
                line,
                mode=project.annotation_mode,
                class_count=len(classes),
                image_size=image_size,
            )
            if parsed is None:
                issues.append({"type": error or "invalid_columns", "file": str(label), "line": line_number, "detail": line})
                if detected_mode:
                    format_counts[detected_mode] += 1
                continue
            class_id = parsed["cls"]
            duplicate_key = (project.annotation_mode, *(parts))
            if duplicate_key in seen_boxes:
                issues.append({"type": "exact_duplicate_box", "file": str(label), "line": line_number, "detail": line})
                continue
            seen_boxes.add(duplicate_key)
            class_counts[classes[class_id]] += 1
            format_counts[project.annotation_mode] += 1

    valid_label_paths = {
        project.label_path_for(image).resolve()
        for image in images
    } | {
        project.label_path_for(image, prefer_existing=False).resolve()
        for image in images
    }
    for label in label_files:
        if label.resolve() not in valid_label_paths:
            issues.append({"type": "orphan_label", "file": str(label), "detail": "No matching image stem"})

    used_formats = [name for name, count in format_counts.items() if count]
    if len(used_formats) > 1:
        issues.append(
            {
                "type": "mixed_annotation_formats",
                "file": str(project.config_path or ""),
                "detail": "Standard detect boxes and YOLO OBB boxes cannot normally train in one YOLO task.",
            }
        )
    elif used_formats and used_formats[0] != project.annotation_mode:
        issues.append(
            {
                "type": "annotation_mode_mismatch",
                "file": str(project.config_path or ""),
                "detail": f"Project mode is {project.annotation_mode}, but labels contain {used_formats[0]} boxes.",
            }
        )

    for name in classes:
        if class_counts[name] == 0:
            issues.append(
                {
                    "type": "unused_class",
                    "file": str(project.classes_path),
                    "detail": f"No boxes use class: {name}",
                }
            )

    for issue in issues:
        issue["severity"] = "error" if issue["type"] in EXPORT_BLOCKING_ISSUES else "warning"
    issue_type_counts = Counter(issue["type"] for issue in issues)
    severity_counts = Counter(issue["severity"] for issue in issues)
    return {
        "project": project.name,
        "images": len(images),
        "labeled_images": labeled,
        "empty_reviewed_images": empty,
        "unreviewed_images": len(images) - labeled - empty,
        "boxes": sum(class_counts.values()),
        "class_counts": dict(class_counts),
        "format_counts": dict(format_counts),
        "image_sizes": dict(image_sizes),
        "issue_types": dict(issue_type_counts),
        "severity_counts": dict(severity_counts),
        "blocking_issue_count": severity_counts["error"],
        "warning_count": severity_counts["warning"],
        "issues": issues,
        "issue_count": len(issues),
    }


def write_report(project: ProjectConfig, output: Path) -> dict:
    report = inspect_project(project)
    output.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(output, json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report


def assert_exportable(report: dict) -> None:
    if report["images"] == 0:
        raise ValueError("Dataset export blocked because the project contains no images.")
    blocking = [issue for issue in report["issues"] if issue["type"] in EXPORT_BLOCKING_ISSUES]
    if not blocking:
        return
    summary = Counter(issue["type"] for issue in blocking)
    raise ValueError(
        "Dataset export blocked by quality issues: "
        + ", ".join(f"{name} ({count})" for name, count in sorted(summary.items()))
        + ". Run Quality Check and fix these issues first."
    )


def validate_export_directory(project: ProjectConfig, output: Path) -> Path:
    output = output.resolve()
    for source in (project.image_dir.resolve(), project.label_dir.resolve()):
        if output == source or source in output.parents:
            raise ValueError(
                f"Export destination cannot be inside the source image or label directory: {output}"
            )
    if output.exists() and not output.is_dir():
        raise ValueError("Export destination must be a directory.")
    if output.exists() and any(output.iterdir()):
        raise ValueError("Export destination is not empty. Choose a new or empty directory to avoid stale files.")
    return output


def export_yolo_dataset(project: ProjectConfig, output: Path, val_ratio: float = 0.2, seed: int = 42) -> dict:
    source_report = inspect_project(project)
    assert_exportable(source_report)
    output = validate_export_directory(project, output)
    if not 0 < val_ratio < 1 and len(find_images(project.image_dir)) > 1:
        raise ValueError("Validation ratio must be greater than 0 and less than 1.")
    images = find_images(project.image_dir)
    rng = random.Random(seed)
    rng.shuffle(images)
    val_count = max(1, min(len(images) - 1, round(len(images) * val_ratio))) if len(images) > 1 else 0
    val_images = {path.resolve() for path in images[:val_count]}

    if project.annotation_mode == "classify":
        return _export_yolo_classification(project, output, images, val_images, source_report)

    for split in ("train", "val"):
        (output / "images" / split).mkdir(parents=True, exist_ok=True)
        (output / "labels" / split).mkdir(parents=True, exist_ok=True)

    copied = Counter()
    for image in images:
        split = "val" if image.resolve() in val_images else "train"
        relative = image.relative_to(project.image_dir)
        target_image = output / "images" / split / relative
        target_image.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(image, target_image)
        source_label = project.label_path_for(image)
        target_label = output / "labels" / split / relative.with_suffix(".txt")
        target_label.parent.mkdir(parents=True, exist_ok=True)
        if source_label.exists():
            shutil.copy2(source_label, target_label)
        else:
            atomic_write_text(target_label, "")
        copied[split] += 1

    names = project.class_names()
    yaml_lines = [
        f"path: {output.as_posix()}",
        "train: images/train",
        "val: images/val",
        f"nc: {len(names)}",
        "names:",
        *[f"  {idx}: {json.dumps(name, ensure_ascii=False)}" for idx, name in enumerate(names)],
    ]
    if project.annotation_mode == "pose":
        keypoints = project.keypoint_names()
        if keypoints:
            yaml_lines.insert(-1 - len(names), f"kpt_shape: [{len(keypoints)}, 3]")
    atomic_write_text(output / "data.yaml", "\n".join(yaml_lines) + "\n")
    atomic_write_text(
        output / "source_qc_report.json",
        json.dumps(source_report, ensure_ascii=False, indent=2) + "\n",
    )
    return {"train": copied["train"], "val": copied["val"], "output": str(output)}


def _export_yolo_classification(project: ProjectConfig, output: Path, images: list[Path], val_images: set[Path], source_report: dict) -> dict:
    names = project.class_names()
    copied = Counter()
    for image in images:
        label = project.label_path_for(image)
        class_id = None
        if label.exists():
            text = label.read_text(encoding="utf-8-sig").strip()
            if text:
                parsed, _error = parse_label_line(text.splitlines()[0], mode="classify", class_count=len(names))
                if parsed is not None:
                    class_id = parsed["cls"]
        if class_id is None:
            continue
        split = "val" if image.resolve() in val_images else "train"
        try:
            relative = image.relative_to(project.image_dir)
        except ValueError:
            relative = Path(image.name)
        target = output / split / names[class_id] / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(image, target)
        copied[split] += 1
    atomic_write_text(
        output / "source_qc_report.json",
        json.dumps(source_report, ensure_ascii=False, indent=2) + "\n",
    )
    return {"train": copied["train"], "val": copied["val"], "output": str(output)}
