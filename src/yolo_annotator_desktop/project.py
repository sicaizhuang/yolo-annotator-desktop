from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET
import yaml

from PIL import Image

from .presets import names_from_yolo_payload
from .safe_io import atomic_write_json, atomic_write_text


PROJECT_SUFFIX = ".yad.json"
CURRENT_PROJECT_VERSION = 1
SUPPORTED_ANNOTATION_MODES = {"detect", "obb", "segment", "pose", "classify"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}


@dataclass
class ProjectConfig:
    name: str
    images: str
    labels: str
    classes: str
    keep_empty: bool = True
    order_file: str = ""
    filter_order: bool = False
    annotation_mode: str = "detect"
    keypoints: str = ""
    version: int = 1
    config_path: Path | None = None

    def resolve(self, value: str) -> Path:
        path = Path(value).expanduser()
        if path.is_absolute() or self.config_path is None:
            return path
        return (self.config_path.parent / path).resolve()

    @property
    def image_dir(self) -> Path:
        return self.resolve(self.images)

    @property
    def label_dir(self) -> Path:
        return self.resolve(self.labels)

    @property
    def classes_path(self) -> Path:
        return self.resolve(self.classes)

    @property
    def order_path(self) -> Path | None:
        return self.resolve(self.order_file) if self.order_file else None

    def label_path_for(self, image_path: str | Path, prefer_existing: bool = True) -> Path:
        return label_path_for_image(image_path, self.image_dir, self.label_dir, prefer_existing=prefer_existing)

    def class_names(self) -> list[str]:
        if not self.classes_path.exists():
            return []
        return [
            line.strip()
            for line in self.classes_path.read_text(encoding="utf-8-sig").splitlines()
            if line.strip()
        ]

    def keypoint_names(self) -> list[str]:
        if not self.keypoints:
            return []
        return [
            item.strip()
            for line in str(self.keypoints).splitlines()
            for item in line.split(",")
            if item.strip()
        ]

    def validate(self) -> list[str]:
        errors = []
        if not self.name.strip():
            errors.append("Project name is empty.")
        if self.annotation_mode not in SUPPORTED_ANNOTATION_MODES:
            errors.append(f"Unsupported annotation mode: {self.annotation_mode}")
        if not self.image_dir.is_dir():
            errors.append(f"Image directory does not exist: {self.image_dir}")
        elif not os.access(self.image_dir, os.R_OK):
            errors.append(f"Image directory is not readable: {self.image_dir}")
        if not self.label_dir.is_dir():
            errors.append(f"Label directory does not exist: {self.label_dir}")
        elif not os.access(self.label_dir, os.W_OK):
            errors.append(f"Label directory is not writable: {self.label_dir}")
        if not self.classes_path.is_file():
            errors.append(f"Classes file does not exist: {self.classes_path}")
        else:
            names = self.class_names()
            if not names:
                errors.append(f"Classes file is empty: {self.classes_path}")
            elif len(names) != len(set(names)):
                errors.append(f"Classes file contains duplicate names: {self.classes_path}")
        if self.order_file and not self.order_path.exists():
            errors.append(f"Order file does not exist: {self.order_path}")
        return errors

    def save(self, path: Path | None = None) -> Path:
        target = Path(path or self.config_path or f"{self.name}{PROJECT_SUFFIX}").resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(self)
        payload.pop("config_path", None)
        atomic_write_json(target, payload)
        self.config_path = target
        return target


def label_path_for_image(
    image_path: str | Path,
    image_dir: str | Path,
    label_dir: str | Path,
    *,
    prefer_existing: bool = True,
) -> Path:
    """Mirror nested image folders into labels while preserving legacy flat labels."""
    image = Path(image_path).resolve()
    image_root = Path(image_dir).resolve()
    label_root = Path(label_dir).resolve()
    try:
        relative = image.relative_to(image_root).with_suffix(".txt")
    except ValueError:
        relative = Path(f"{image.stem}.txt")
    mirrored = label_root / relative
    flat = label_root / f"{image.stem}.txt"
    if prefer_existing and relative.parent == Path(".") and not mirrored.exists() and flat.exists():
        return flat
    return mirrored


def load_project(path: str | Path) -> ProjectConfig:
    config_path = Path(path).resolve()
    payload = json.loads(config_path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError("Project file must contain a JSON object.")
    required = {"name", "images", "labels", "classes"}
    missing = sorted(required - payload.keys())
    if missing:
        raise ValueError(f"Project file is missing required fields: {', '.join(missing)}")
    known = {field.name for field in ProjectConfig.__dataclass_fields__.values()} - {"config_path"}
    project = ProjectConfig(**{key: value for key, value in payload.items() if key in known})
    if project.version > CURRENT_PROJECT_VERSION:
        raise ValueError(
            f"Project file version {project.version} is newer than this application supports "
            f"(maximum {CURRENT_PROJECT_VERSION})."
        )
    project.config_path = config_path
    return project


def ensure_new_project_workspace(root: str | Path) -> Path:
    root_path = Path(root).resolve()
    conflicts = []
    for candidate in (root_path / f"project{PROJECT_SUFFIX}", root_path / "classes.txt"):
        if candidate.exists():
            conflicts.append(candidate)
    for folder_name in ("images", "labels"):
        folder = root_path / folder_name
        if folder.is_dir() and any(folder.iterdir()):
            conflicts.append(folder)
    if conflicts:
        raise ValueError(
            "Project workspace already contains project data. Choose a new empty workspace to avoid overwriting:\n"
            + "\n".join(str(path) for path in conflicts)
        )
    return root_path


def create_project(
    root: str | Path,
    name: str,
    classes: list[str],
    annotation_mode: str = "detect",
    keypoints: str = "",
) -> ProjectConfig:
    if annotation_mode not in SUPPORTED_ANNOTATION_MODES:
        raise ValueError(f"Unsupported annotation mode: {annotation_mode}")
    root_path = ensure_new_project_workspace(root)
    image_dir = root_path / "images"
    label_dir = root_path / "labels"
    image_dir.mkdir(parents=True, exist_ok=True)
    label_dir.mkdir(parents=True, exist_ok=True)
    classes_path = root_path / "classes.txt"
    atomic_write_text(classes_path, "\n".join(classes) + "\n")
    project = ProjectConfig(
        name=name.strip() or root_path.name,
        images="images",
        labels="labels",
        classes="classes.txt",
        annotation_mode=annotation_mode,
        keypoints=keypoints,
        config_path=root_path / f"project{PROJECT_SUFFIX}",
    )
    project.save()
    return project


def create_project_from_folders(
    workspace: str | Path,
    name: str,
    image_dir: str | Path,
    label_dir: str | Path,
    classes: list[str],
    annotation_mode: str = "detect",
    keypoints: str = "",
) -> ProjectConfig:
    if annotation_mode not in SUPPORTED_ANNOTATION_MODES:
        raise ValueError(f"Unsupported annotation mode: {annotation_mode}")
    workspace_path = ensure_new_project_workspace(workspace)
    workspace_path.mkdir(parents=True, exist_ok=True)
    labels = Path(label_dir).resolve()
    labels.mkdir(parents=True, exist_ok=True)
    classes_path = workspace_path / "classes.txt"
    atomic_write_text(classes_path, "\n".join(classes) + "\n")
    project = ProjectConfig(
        name=name.strip() or workspace_path.name,
        images=str(Path(image_dir).resolve()),
        labels=str(labels),
        classes="classes.txt",
        annotation_mode=annotation_mode,
        keypoints=keypoints,
        config_path=workspace_path / f"project{PROJECT_SUFFIX}",
    )
    project.save()
    return project


def create_project_from_yolo_yaml(
    workspace: str | Path,
    yaml_path: str | Path,
    split: str = "train",
    annotation_mode: str = "detect",
) -> ProjectConfig:
    yaml_file = Path(yaml_path).resolve()
    data = yaml.safe_load(yaml_file.read_text(encoding="utf-8-sig")) or {}
    if not isinstance(data, dict):
        raise ValueError("YOLO YAML must contain a mapping.")
    root_value = data.get("path", yaml_file.parent)
    dataset_root = Path(root_value)
    if not dataset_root.is_absolute():
        dataset_root = (yaml_file.parent / dataset_root).resolve()
    split_value = data.get(split)
    if not split_value:
        raise ValueError(f"The YAML file has no '{split}' split.")
    names = names_from_yolo_payload(data)
    keypoints = _keypoints_from_yolo_payload(data) if annotation_mode == "pose" else ""

    split_items = split_value if isinstance(split_value, list) else [split_value]
    resolved_items = [_resolve_yolo_path(item, dataset_root, yaml_file.parent) for item in split_items]

    if len(resolved_items) == 1 and resolved_items[0].is_dir():
        image_dir = resolved_items[0]
        return create_project_from_folders(
            workspace,
            f"{yaml_file.stem}-{split}",
            image_dir,
            _infer_yolo_label_root(image_dir),
            names,
            annotation_mode,
            keypoints,
        )

    image_paths: list[Path] = []
    for item in resolved_items:
        if item.is_dir():
            image_paths.extend(_find_images(item))
        elif item.is_file():
            image_paths.extend(_read_yolo_image_list(item, dataset_root, yaml_file.parent))
        else:
            raise ValueError(f"YOLO split path does not exist: {item}")
    image_paths = sorted(dict.fromkeys(path.resolve() for path in image_paths))
    if not image_paths:
        raise ValueError(f"The YAML '{split}' split contains no supported images.")

    image_root = _choose_image_root(image_paths)
    project = create_project_from_folders(
        workspace,
        f"{yaml_file.stem}-{split}",
        image_root,
        _infer_yolo_label_root(image_root),
        names,
        annotation_mode,
        keypoints,
    )
    order_path = project.config_path.parent / f"{split}_order.txt"
    order_lines = []
    for image in image_paths:
        try:
            order_lines.append(image.relative_to(image_root).as_posix())
        except ValueError:
            order_lines.append(image.as_posix())
    atomic_write_text(order_path, "\n".join(order_lines) + "\n")
    project.order_file = order_path.name
    project.filter_order = True
    project.save()
    return project


def _resolve_yolo_path(value: str | Path, dataset_root: Path, yaml_dir: Path) -> Path:
    candidate = Path(str(value)).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    for root in (dataset_root, yaml_dir):
        resolved = (root / candidate).resolve()
        if resolved.exists():
            return resolved
    return (dataset_root / candidate).resolve()


def _find_images(root: Path) -> list[Path]:
    return [path for path in sorted(root.rglob("*")) if path.is_file() and path.suffix.lower() in IMAGE_EXTS]


def _read_yolo_image_list(list_file: Path, dataset_root: Path, yaml_dir: Path) -> list[Path]:
    images: list[Path] = []
    for raw_line in list_file.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip().strip('"').strip("'")
        if not line or line.startswith("#"):
            continue
        candidate = Path(line).expanduser()
        if candidate.is_absolute():
            resolved = candidate.resolve()
        else:
            probes = [
                (dataset_root / candidate).resolve(),
                (list_file.parent / candidate).resolve(),
                (yaml_dir / candidate).resolve(),
            ]
            resolved = next((probe for probe in probes if probe.exists()), probes[0])
        if resolved.suffix.lower() in IMAGE_EXTS:
            images.append(resolved)
    missing = [path for path in images if not path.exists()]
    if missing:
        preview = "\n".join(str(path) for path in missing[:10])
        raise ValueError(f"YOLO image list contains missing images:\n{preview}")
    return images


def _choose_image_root(image_paths: list[Path]) -> Path:
    images = [path.resolve() for path in image_paths]
    image_roots = []
    for image in images:
        parts_lower = [part.lower() for part in image.parts]
        if "images" in parts_lower:
            idx = len(parts_lower) - 1 - parts_lower[::-1].index("images")
            image_roots.append(Path(*image.parts[: idx + 1]))
    if image_roots and len({root.resolve() for root in image_roots}) == 1:
        return image_roots[0].resolve()
    return Path(os.path.commonpath([str(path.parent) for path in images])).resolve()


def _infer_yolo_label_root(image_dir: Path) -> Path:
    parts = list(image_dir.parts)
    lowered = [part.lower() for part in parts]
    if "images" in lowered:
        idx = len(lowered) - 1 - lowered[::-1].index("images")
        parts[idx] = "labels"
        return Path(*parts)
    return image_dir.parent / "labels" / image_dir.name


def _keypoints_from_yolo_payload(data: dict) -> str:
    names = data.get("keypoints") or data.get("keypoint_names") or data.get("kpt_names")
    if isinstance(names, dict):
        return ", ".join(str(names[key]) for key in sorted(names, key=lambda value: int(value)))
    if isinstance(names, list):
        return ", ".join(str(name) for name in names)
    shape = data.get("kpt_shape")
    if isinstance(shape, list) and shape:
        try:
            count = int(shape[0])
        except (TypeError, ValueError):
            count = 0
        if count > 0:
            return ", ".join(f"keypoint_{idx + 1}" for idx in range(count))
    return ""


def create_project_from_coco(
    workspace: str | Path,
    coco_json: str | Path,
    image_dir: str | Path,
    annotation_mode: str = "detect",
    keypoints: str = "",
) -> ProjectConfig:
    if annotation_mode not in SUPPORTED_ANNOTATION_MODES:
        raise ValueError(f"Unsupported annotation mode: {annotation_mode}")
    source = Path(coco_json).resolve()
    images_root = Path(image_dir).resolve()
    payload = json.loads(source.read_text(encoding="utf-8-sig"))
    categories = sorted(payload.get("categories", []), key=lambda item: int(item["id"]))
    if not categories:
        raise ValueError("COCO JSON contains no categories.")
    category_map = {int(item["id"]): idx for idx, item in enumerate(categories)}
    names = [str(item["name"]) for item in categories]
    project = create_project_from_folders(
        workspace,
        source.stem,
        images_root,
        Path(workspace).resolve() / "labels",
        names,
        annotation_mode,
        keypoints,
    )
    image_records = {int(item["id"]): item for item in payload.get("images", [])}
    grouped: dict[int, list[str]] = {}
    for annotation in payload.get("annotations", []):
        image_id = int(annotation["image_id"])
        category_id = int(annotation["category_id"])
        if image_id not in image_records or category_id not in category_map:
            continue
        record = image_records[image_id]
        width, height = float(record["width"]), float(record["height"])
        bbox = annotation.get("bbox", [])
        if len(bbox) != 4 or width <= 0 or height <= 0:
            continue
        x, y, box_width, box_height = map(float, bbox)
        if annotation_mode in {"obb", "segment"}:
            segmentation = annotation.get("segmentation", [])
            polygon = segmentation[0] if isinstance(segmentation, list) and segmentation else []
            if annotation_mode == "segment" and isinstance(polygon, list) and len(polygon) >= 6 and len(polygon) % 2 == 0:
                coords = [
                    value / (width if idx % 2 == 0 else height)
                    for idx, value in enumerate(map(float, polygon))
                ]
            elif annotation_mode == "obb" and isinstance(polygon, list) and len(polygon) == 8:
                coords = [
                    value / (width if idx % 2 == 0 else height)
                    for idx, value in enumerate(map(float, polygon))
                ]
            else:
                coords = [
                    x / width,
                    y / height,
                    (x + box_width) / width,
                    y / height,
                    (x + box_width) / width,
                    (y + box_height) / height,
                    x / width,
                    (y + box_height) / height,
                ]
            grouped.setdefault(image_id, []).append(
                f"{category_map[category_id]} " + " ".join(f"{value:.6f}" for value in coords)
            )
        else:
            grouped.setdefault(image_id, []).append(
                f"{category_map[category_id]} {(x + box_width / 2) / width:.6f} "
                f"{(y + box_height / 2) / height:.6f} {box_width / width:.6f} {box_height / height:.6f}"
            )
    for image_id, record in image_records.items():
        image_path = images_root / str(record["file_name"])
        if not image_path.exists():
            raise ValueError(f"COCO image is missing: {image_path}")
        label = project.label_path_for(image_path, prefer_existing=False)
        lines = grouped.get(image_id, [])
        atomic_write_text(label, ("\n".join(lines) + "\n") if lines else "")
    return project


def create_project_from_pascal_voc(
    workspace: str | Path,
    xml_dir: str | Path,
    image_dir: str | Path,
) -> ProjectConfig:
    xml_root = Path(xml_dir).resolve()
    images_root = Path(image_dir).resolve()
    records = []
    names = []
    for xml_path in sorted(xml_root.rglob("*.xml")):
        root = ET.parse(xml_path).getroot()
        filename = root.findtext("filename")
        if not filename:
            continue
        image_path = images_root / filename
        if not image_path.exists():
            matches = list(images_root.rglob(filename))
            if len(matches) != 1:
                raise ValueError(f"Pascal VOC image is missing or ambiguous: {filename}")
            image_path = matches[0]
        size = root.find("size")
        width = int(size.findtext("width", "0")) if size is not None else 0
        height = int(size.findtext("height", "0")) if size is not None else 0
        if width <= 0 or height <= 0:
            with Image.open(image_path) as source:
                width, height = source.size
        objects = []
        for obj in root.findall("object"):
            name = (obj.findtext("name") or "").strip()
            bounds = obj.find("bndbox")
            if not name or bounds is None:
                continue
            if name not in names:
                names.append(name)
            objects.append(
                (
                    name,
                    float(bounds.findtext("xmin", "0")),
                    float(bounds.findtext("ymin", "0")),
                    float(bounds.findtext("xmax", "0")),
                    float(bounds.findtext("ymax", "0")),
                )
            )
        records.append((image_path, width, height, objects))
    if not records:
        raise ValueError("No usable Pascal VOC XML annotations were found.")
    if not names:
        raise ValueError("Pascal VOC XML files contain no classes.")
    project = create_project_from_folders(
        workspace,
        xml_root.name,
        images_root,
        Path(workspace).resolve() / "labels",
        names,
        "detect",
    )
    name_to_id = {name: idx for idx, name in enumerate(names)}
    for image_path, width, height, objects in records:
        lines = []
        for name, x1, y1, x2, y2 in objects:
            lines.append(
                f"{name_to_id[name]} {((x1 + x2) / 2) / width:.6f} {((y1 + y2) / 2) / height:.6f} "
                f"{(x2 - x1) / width:.6f} {(y2 - y1) / height:.6f}"
            )
        atomic_write_text(
            project.label_path_for(image_path, prefer_existing=False),
            ("\n".join(lines) + "\n") if lines else "",
        )
    return project


def remap_classes(project: ProjectConfig, names: list[str], old_to_new: dict[int, int]) -> dict:
    if not names or len(names) != len(set(names)):
        raise ValueError("Class names must be non-empty and unique.")

    label_files = sorted(project.label_dir.rglob("*.txt"))
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup = project.label_dir.parent / f"{project.label_dir.name}_backup_classes_{timestamp}"
    classes_backup = project.classes_path.with_name(f"{project.classes_path.stem}_backup_{timestamp}{project.classes_path.suffix}")
    if label_files:
        shutil.copytree(project.label_dir, backup)
    if project.classes_path.exists():
        shutil.copy2(project.classes_path, classes_backup)

    changed_files = dropped_boxes = remapped_boxes = 0
    for label in label_files:
        output = []
        changed = False
        for raw_line in label.read_text(encoding="utf-8-sig").splitlines():
            parts = raw_line.split()
            if not parts:
                output.append(raw_line)
                continue
            try:
                old_id = int(float(parts[0]))
            except ValueError:
                output.append(raw_line)
                continue
            if old_id not in old_to_new:
                dropped_boxes += 1
                changed = True
                continue
            new_id = old_to_new[old_id]
            if new_id != old_id:
                remapped_boxes += 1
                changed = True
            output.append(" ".join([str(new_id), *parts[1:]]))
        if changed:
            changed_files += 1
            atomic_write_text(label, ("\n".join(output) + "\n") if output else "")

    atomic_write_text(project.classes_path, "\n".join(names) + "\n")
    return {
        "backup": str(backup) if label_files else "",
        "classes_backup": str(classes_backup),
        "changed_files": changed_files,
        "dropped_boxes": dropped_boxes,
        "remapped_boxes": remapped_boxes,
    }
