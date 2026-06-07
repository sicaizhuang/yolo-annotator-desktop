from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from PIL import Image

from .label_formats import parse_label_line
from .project import ProjectConfig
from .qc import assert_exportable, find_images, inspect_project, validate_export_directory
from .safe_io import atomic_write_text


def _parse_label(project: ProjectConfig, image: Path) -> list[dict]:
    label = project.label_path_for(image)
    if not label.exists():
        return []
    parsed = []
    with Image.open(image) as source:
        image_size = source.size
    for line in label.read_text(encoding="utf-8-sig").splitlines():
        box, _error = parse_label_line(line, mode=project.annotation_mode, class_count=len(project.class_names()), image_size=image_size)
        if box is not None:
            parsed.append(box)
    return parsed


def export_coco(project: ProjectConfig, output_json: str | Path) -> dict:
    assert_exportable(inspect_project(project))
    if project.annotation_mode == "classify":
        raise ValueError("COCO JSON export is not suitable for image classification datasets. Export YOLO instead.")
    output = Path(output_json).resolve()
    images_payload = []
    annotations = []
    annotation_id = 1
    for image_id, image_path in enumerate(find_images(project.image_dir), 1):
        with Image.open(image_path) as source:
            width, height = source.size
        relative = image_path.relative_to(project.image_dir).as_posix()
        images_payload.append({"id": image_id, "file_name": relative, "width": width, "height": height})
        for box in _parse_label(project, image_path):
            class_id = box["cls"]
            if box.get("kind") in {"aabb", "pose"}:
                x1, y1, x2, y2 = box["x1"], box["y1"], box["x2"], box["y2"]
                bbox = [x1, y1, x2 - x1, y2 - y1]
                segmentation = []
                area = bbox[2] * bbox[3]
            elif box.get("kind") in {"obb", "polygon"}:
                points = box["points"]
                xs = [point[0] for point in points]
                ys = [point[1] for point in points]
                bbox = [min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)]
                segmentation = [[value for point in points for value in point]]
                area = abs(
                    sum(
                        points[idx][0] * points[(idx + 1) % len(points)][1]
                        - points[(idx + 1) % len(points)][0] * points[idx][1]
                        for idx in range(len(points))
                    )
                    / 2
                )
            else:
                continue
            annotations.append(
                {
                    "id": annotation_id,
                    "image_id": image_id,
                    "category_id": class_id + 1,
                    "bbox": [round(value, 4) for value in bbox],
                    "area": round(area, 4),
                    "iscrowd": 0,
                    "segmentation": segmentation,
                }
            )
            annotation_id += 1
    payload = {
        "info": {
            "description": project.name,
            "date_created": datetime.now(timezone.utc).isoformat(),
        },
        "images": images_payload,
        "annotations": annotations,
        "categories": [
            {"id": idx + 1, "name": name, "supercategory": "object"}
            for idx, name in enumerate(project.class_names())
        ],
    }
    atomic_write_text(output, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return {"images": len(images_payload), "annotations": len(annotations), "output": str(output)}


def export_pascal_voc(project: ProjectConfig, output_dir: str | Path) -> dict:
    report = inspect_project(project)
    assert_exportable(report)
    unsupported = set(report["format_counts"]) - {"detect"}
    if unsupported:
        raise ValueError("Pascal VOC XML can only preserve axis-aligned detect boxes. Export YOLO or COCO instead.")
    output = validate_export_directory(project, Path(output_dir))
    output.mkdir(parents=True, exist_ok=True)
    count = 0
    for image_path in find_images(project.image_dir):
        with Image.open(image_path) as source:
            width, height = source.size
            depth = len(source.getbands())
        root = ET.Element("annotation")
        ET.SubElement(root, "folder").text = str(image_path.parent.name)
        ET.SubElement(root, "filename").text = image_path.name
        ET.SubElement(root, "path").text = image_path.relative_to(project.image_dir).as_posix()
        size = ET.SubElement(root, "size")
        ET.SubElement(size, "width").text = str(width)
        ET.SubElement(size, "height").text = str(height)
        ET.SubElement(size, "depth").text = str(depth)
        ET.SubElement(root, "segmented").text = "0"
        for box in _parse_label(project, image_path):
            if box.get("kind") != "aabb":
                continue
            class_id = box["cls"]
            obj = ET.SubElement(root, "object")
            ET.SubElement(obj, "name").text = project.class_names()[class_id]
            ET.SubElement(obj, "pose").text = "Unspecified"
            ET.SubElement(obj, "truncated").text = "0"
            ET.SubElement(obj, "difficult").text = "0"
            bounds = ET.SubElement(obj, "bndbox")
            ET.SubElement(bounds, "xmin").text = str(max(0, round(box["x1"])))
            ET.SubElement(bounds, "ymin").text = str(max(0, round(box["y1"])))
            ET.SubElement(bounds, "xmax").text = str(min(width, round(box["x2"])))
            ET.SubElement(bounds, "ymax").text = str(min(height, round(box["y2"])))
        relative = image_path.relative_to(project.image_dir).with_suffix(".xml")
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        xml = ET.tostring(root, encoding="unicode")
        atomic_write_text(target, '<?xml version="1.0" encoding="utf-8"?>\n' + xml + "\n")
        count += 1
    return {"images": count, "output": str(output)}
