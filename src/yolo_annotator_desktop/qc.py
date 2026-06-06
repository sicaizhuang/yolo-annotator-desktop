from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import random
import shutil

from .project import ProjectConfig


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def find_images(image_dir: Path) -> list[Path]:
    return [
        path
        for path in sorted(image_dir.rglob("*"))
        if path.is_file()
        and path.suffix.lower() in IMAGE_EXTS
        and not any(part.startswith("_") for part in path.parts)
    ]


def inspect_project(project: ProjectConfig) -> dict:
    classes = project.class_names()
    images = find_images(project.image_dir)
    image_stems = Counter(path.stem for path in images)
    label_files = sorted(project.label_dir.rglob("*.txt"))
    class_counts = Counter()
    issues: list[dict] = []
    labeled = empty = 0

    for stem, count in image_stems.items():
        if count > 1:
            issues.append({"type": "duplicate_image_stem", "file": stem, "detail": f"{count} images share this stem"})

    for image in images:
        label = project.label_dir / f"{image.stem}.txt"
        if not label.exists():
            continue
        text = label.read_text(encoding="utf-8-sig").strip()
        if not text:
            empty += 1
            continue
        labeled += 1
        for line_number, line in enumerate(text.splitlines(), 1):
            parts = line.split()
            if len(parts) != 5:
                issues.append({"type": "invalid_columns", "file": str(label), "line": line_number, "detail": line})
                continue
            try:
                class_id = int(float(parts[0]))
                xc, yc, width, height = map(float, parts[1:])
            except ValueError:
                issues.append({"type": "invalid_number", "file": str(label), "line": line_number, "detail": line})
                continue
            if class_id < 0 or class_id >= len(classes):
                issues.append({"type": "invalid_class", "file": str(label), "line": line_number, "detail": class_id})
                continue
            class_counts[classes[class_id]] += 1
            if not (0 <= xc <= 1 and 0 <= yc <= 1 and 0 < width <= 1 and 0 < height <= 1):
                issues.append({"type": "invalid_bounds", "file": str(label), "line": line_number, "detail": line})
            if xc - width / 2 < -1e-6 or yc - height / 2 < -1e-6 or xc + width / 2 > 1 + 1e-6 or yc + height / 2 > 1 + 1e-6:
                issues.append({"type": "box_outside_image", "file": str(label), "line": line_number, "detail": line})

    valid_stems = set(image_stems)
    for label in label_files:
        if label.stem not in valid_stems:
            issues.append({"type": "orphan_label", "file": str(label), "detail": "No matching image stem"})

    return {
        "project": project.name,
        "images": len(images),
        "labeled_images": labeled,
        "empty_reviewed_images": empty,
        "unreviewed_images": len(images) - labeled - empty,
        "boxes": sum(class_counts.values()),
        "class_counts": dict(class_counts),
        "issues": issues,
        "issue_count": len(issues),
    }


def write_report(project: ProjectConfig, output: Path) -> dict:
    report = inspect_project(project)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def export_yolo_dataset(project: ProjectConfig, output: Path, val_ratio: float = 0.2, seed: int = 42) -> dict:
    output = output.resolve()
    images = find_images(project.image_dir)
    rng = random.Random(seed)
    rng.shuffle(images)
    val_count = max(1, round(len(images) * val_ratio)) if len(images) > 1 else len(images)
    val_stems = {path.stem for path in images[:val_count]}

    for split in ("train", "val"):
        (output / "images" / split).mkdir(parents=True, exist_ok=True)
        (output / "labels" / split).mkdir(parents=True, exist_ok=True)

    copied = Counter()
    for image in images:
        split = "val" if image.stem in val_stems else "train"
        shutil.copy2(image, output / "images" / split / image.name)
        source_label = project.label_dir / f"{image.stem}.txt"
        target_label = output / "labels" / split / f"{image.stem}.txt"
        if source_label.exists():
            shutil.copy2(source_label, target_label)
        else:
            target_label.write_text("", encoding="utf-8")
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
    (output / "data.yaml").write_text("\n".join(yaml_lines) + "\n", encoding="utf-8")
    report = inspect_project(project)
    (output / "source_qc_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return {"train": copied["train"], "val": copied["val"], "output": str(output)}
