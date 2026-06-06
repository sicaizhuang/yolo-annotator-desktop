from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import json
from pathlib import Path
import shutil


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


def create_project(root: str | Path, name: str, classes: list[str]) -> ProjectConfig:
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
        config_path=root_path / f"project{PROJECT_SUFFIX}",
    )
    project.save()
    return project


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
            if len(parts) != 5:
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
