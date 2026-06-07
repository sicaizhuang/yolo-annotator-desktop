from __future__ import annotations

from pathlib import Path
from typing import Iterable

import yaml


COCO80 = [
    "person",
    "bicycle",
    "car",
    "motorcycle",
    "airplane",
    "bus",
    "train",
    "truck",
    "boat",
    "traffic light",
    "fire hydrant",
    "stop sign",
    "parking meter",
    "bench",
    "bird",
    "cat",
    "dog",
    "horse",
    "sheep",
    "cow",
    "elephant",
    "bear",
    "zebra",
    "giraffe",
    "backpack",
    "umbrella",
    "handbag",
    "tie",
    "suitcase",
    "frisbee",
    "skis",
    "snowboard",
    "sports ball",
    "kite",
    "baseball bat",
    "baseball glove",
    "skateboard",
    "surfboard",
    "tennis racket",
    "bottle",
    "wine glass",
    "cup",
    "fork",
    "knife",
    "spoon",
    "bowl",
    "banana",
    "apple",
    "sandwich",
    "orange",
    "broccoli",
    "carrot",
    "hot dog",
    "pizza",
    "donut",
    "cake",
    "chair",
    "couch",
    "potted plant",
    "bed",
    "dining table",
    "toilet",
    "tv",
    "laptop",
    "mouse",
    "remote",
    "keyboard",
    "cell phone",
    "microwave",
    "oven",
    "toaster",
    "sink",
    "refrigerator",
    "book",
    "clock",
    "vase",
    "scissors",
    "teddy bear",
    "hair drier",
    "toothbrush",
]


PASCAL_VOC20 = [
    "aeroplane",
    "bicycle",
    "bird",
    "boat",
    "bottle",
    "bus",
    "car",
    "cat",
    "chair",
    "cow",
    "diningtable",
    "dog",
    "horse",
    "motorbike",
    "person",
    "pottedplant",
    "sheep",
    "sofa",
    "train",
    "tvmonitor",
]


ELECTRONICS_STARTER = [
    "capacitor",
    "resistor",
    "inductor",
    "diode",
    "transistor",
    "connector",
    "switch",
    "ic_chip",
    "screw",
]


DEFECT_STARTER = [
    "scratch",
    "dent",
    "crack",
    "stain",
    "missing_part",
    "wrong_part",
    "foreign_object",
]


CLASS_PRESETS = {
    "Custom": [],
    "Single object": ["object"],
    "COCO 80": COCO80,
    "Pascal VOC 20": PASCAL_VOC20,
    "Electronics starter": ELECTRONICS_STARTER,
    "Defect detection starter": DEFECT_STARTER,
}


def normalize_class_names(names: Iterable[str]) -> list[str]:
    cleaned = [str(name).strip() for name in names if str(name).strip()]
    if not cleaned:
        raise ValueError("At least one class name is required.")
    duplicates = sorted({name for name in cleaned if cleaned.count(name) > 1})
    if duplicates:
        raise ValueError(f"Class names must be unique. Duplicate: {', '.join(duplicates)}")
    return cleaned


def parse_class_text(text: str) -> list[str]:
    tokens: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "," in stripped:
            tokens.extend(part.strip() for part in stripped.split(","))
        else:
            tokens.append(stripped)
    return normalize_class_names(tokens)


def names_from_yolo_payload(payload: dict) -> list[str]:
    raw_names = payload.get("names", [])
    if isinstance(raw_names, dict):
        return normalize_class_names(str(raw_names[key]) for key in sorted(raw_names, key=lambda value: int(value)))
    return normalize_class_names(str(name) for name in raw_names)


def load_classes_file(path: str | Path) -> list[str]:
    source = Path(path).resolve()
    if not source.is_file():
        raise ValueError(f"Class file does not exist: {source}")
    if source.suffix.lower() in {".yaml", ".yml"}:
        payload = yaml.safe_load(source.read_text(encoding="utf-8-sig")) or {}
        if not isinstance(payload, dict):
            raise ValueError("YOLO YAML class file must contain a mapping.")
        return names_from_yolo_payload(payload)
    return parse_class_text(source.read_text(encoding="utf-8-sig"))
