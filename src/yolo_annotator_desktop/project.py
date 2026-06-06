from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import json
from pathlib import Path
import shutil
import yaml


PROJECT_SUFFIX = ".yad.json"


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

    def class_names(self) -> list[str]:
        if not self.classes_path.exists():
            return []
        return [
            line.strip()
            for line in self.classes_path.read_text(encoding="utf-8-sig").splitlines()
            if line.strip()
        ]

    def validate(self) -> list[str]:
        errors = []
        if self.annotation_mode not in {"detect", "obb"}:
            errors.append(f"Unsupported annotation mode: {self.annotation_mode}")
        if not self.image_dir.is_dir():
            errors.append(f"Image directory does not exist: {self.image_dir}")
        if not self.label_dir.is_dir():
            errors.append(f"Label directory does not exist: {self.label_dir}")
        if not self.classes_path.is_file():
            errors.append(f"Classes file does not exist: {self.classes_path}")
        elif not self.class_names():
            errors.append(f"Classes file is empty: {self.classes_path}")
        if self.order_file and not self.order_path.exists():
            errors.append(f"Order file does not exist: {self.order_path}")
        return errors

    def save(self, path: Path | None = None) -> Path:
        target = Path(path or self.config_path or f"{self.name}{PROJECT_SUFFIX}").resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(self)
        payload.pop("config_path", None)
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.config_path = target
        return target


def load_project(path: str | Path) -> ProjectConfig:
    config_path = Path(path).resolve()
    payload = json.loads(config_path.read_text(encoding="utf-8-sig"))
    project = ProjectConfig(**payload)
    project.config_path = config_path
    return project


def create_project(root: str | Path, name: str, classes: list[str], annotation_mode: str = "detect") -> ProjectConfig:
    root_path = Path(root).resolve()
    image_dir = root_path / "images"
    label_dir = root_path / "labels"
    image_dir.mkdir(parents=True, exist_ok=True)
    label_dir.mkdir(parents=True, exist_ok=True)
    classes_path = root_path / "classes.txt"
    classes_path.write_text("\n".join(classes) + "\n", encoding="utf-8")
    project = ProjectConfig(
        name=name.strip() or root_path.name,
        images="images",
        labels="labels",
        classes="classes.txt",
        annotation_mode=annotation_mode,
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
) -> ProjectConfig:
    workspace_path = Path(workspace).resolve()
    workspace_path.mkdir(parents=True, exist_ok=True)
    labels = Path(label_dir).resolve()
    labels.mkdir(parents=True, exist_ok=True)
    classes_path = workspace_path / "classes.txt"
    classes_path.write_text("\n".join(classes) + "\n", encoding="utf-8")
    project = ProjectConfig(
        name=name.strip() or workspace_path.name,
        images=str(Path(image_dir).resolve()),
        labels=str(labels),
        classes="classes.txt",
        annotation_mode=annotation_mode,
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
    root_value = data.get("path", yaml_file.parent)
    dataset_root = Path(root_value)
    if not dataset_root.is_absolute():
        dataset_root = (yaml_file.parent / dataset_root).resolve()
    split_value = data.get(split)
    if isinstance(split_value, list):
        if len(split_value) != 1:
            raise ValueError("This version can open one image directory per project. Choose a YAML split with one directory.")
        split_value = split_value[0]
    if not split_value:
        raise ValueError(f"The YAML file has no '{split}' split.")
    image_dir = Path(split_value)
    if not image_dir.is_absolute():
        image_dir = (dataset_root / image_dir).resolve()
    if image_dir.is_file():
        raise ValueError("Image-list TXT splits are not supported yet. Use a split that points to an image directory.")

    parts = list(image_dir.parts)
    if "images" in parts:
        idx = len(parts) - 1 - parts[::-1].index("images")
        parts[idx] = "labels"
        label_dir = Path(*parts)
    else:
        label_dir = image_dir.parent / "labels" / image_dir.name

    raw_names = data.get("names", [])
    if isinstance(raw_names, dict):
        names = [str(raw_names[key]) for key in sorted(raw_names, key=lambda value: int(value))]
    else:
        names = [str(name) for name in raw_names]
    if not names:
        raise ValueError("The YAML file does not contain class names.")
    return create_project_from_folders(workspace, f"{yaml_file.stem}-{split}", image_dir, label_dir, names, annotation_mode)


def remap_classes(project: ProjectConfig, names: list[str], old_to_new: dict[int, int]) -> dict:
    if not names or len(names) != len(set(names)):
        raise ValueError("Class names must be non-empty and unique.")

    label_files = sorted(project.label_dir.rglob("*.txt"))
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
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
            if len(parts) not in (5, 9):
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
            label.write_text(("\n".join(output) + "\n") if output else "", encoding="utf-8")

    project.classes_path.write_text("\n".join(names) + "\n", encoding="utf-8")
    return {
        "backup": str(backup) if label_files else "",
        "classes_backup": str(classes_backup),
        "changed_files": changed_files,
        "dropped_boxes": dropped_boxes,
        "remapped_boxes": remapped_boxes,
    }
