from __future__ import annotations

import math


def polygon_area(points: list[tuple[float, float]]) -> float:
    if len(points) < 3:
        return 0.0
    return sum(
        points[idx][0] * points[(idx + 1) % len(points)][1]
        - points[(idx + 1) % len(points)][0] * points[idx][1]
        for idx in range(len(points))
    ) / 2


def parse_label_line(
    line: str,
    *,
    mode: str,
    class_count: int,
    image_size: tuple[int, int] | None = None,
) -> tuple[dict | None, str | None]:
    parts = line.strip().split()
    if not parts:
        return None, None
    try:
        class_id = int(float(parts[0]))
    except (ValueError, OverflowError):
        return None, "invalid_number"
    if class_id < 0 or class_id >= class_count:
        return None, "invalid_class"

    if mode == "classify":
        if len(parts) != 1:
            return None, "invalid_columns"
        return {"kind": "classify", "cls": class_id}, None

    try:
        values = [float(value) for value in parts[1:]]
    except (ValueError, OverflowError):
        return None, "invalid_number"
    if not all(math.isfinite(value) for value in values):
        return None, "invalid_number"

    width, height = image_size or (1, 1)
    if mode == "segment":
        if len(values) < 6 or len(values) % 2:
            return None, "invalid_columns"
        if any(value < 0 or value > 1 for value in values):
            return None, "invalid_bounds"
        points = [(values[idx] * width, values[idx + 1] * height) for idx in range(0, len(values), 2)]
        if abs(polygon_area(points)) <= 1e-8:
            return None, "degenerate_polygon"
        return {"kind": "polygon", "cls": class_id, "points": points}, None

    if mode == "pose":
        if len(values) < 7 or (len(values) - 4) % 3:
            return None, "invalid_columns"
        box_error = _validate_normalized_box(values[:4])
        if box_error:
            return None, box_error
        xc, yc, bw, bh = values[:4]
        keypoints = []
        for idx in range(4, len(values), 3):
            x, y, visible = values[idx], values[idx + 1], values[idx + 2]
            if visible not in (0, 1, 2):
                return None, "invalid_keypoint_visibility"
            if visible and not (0 <= x <= 1 and 0 <= y <= 1):
                return None, "invalid_keypoint_bounds"
            keypoints.append((x * width, y * height, int(visible)))
        return {
            "kind": "pose",
            "cls": class_id,
            "x1": (xc - bw / 2) * width,
            "y1": (yc - bh / 2) * height,
            "x2": (xc + bw / 2) * width,
            "y2": (yc + bh / 2) * height,
            "keypoints": keypoints,
        }, None

    if mode == "obb":
        if len(values) != 8:
            return None, "invalid_columns"
        if any(value < 0 or value > 1 for value in values):
            return None, "obb_point_outside_image"
        points = [(values[idx] * width, values[idx + 1] * height) for idx in range(0, 8, 2)]
        if abs(polygon_area(points)) <= 1e-8:
            return None, "degenerate_obb"
        return {"kind": "obb", "cls": class_id, "points": points}, None

    if len(values) != 4:
        return None, "invalid_columns"
    box_error = _validate_normalized_box(values)
    if box_error:
        return None, box_error
    xc, yc, bw, bh = values
    return {
        "kind": "aabb",
        "cls": class_id,
        "x1": (xc - bw / 2) * width,
        "y1": (yc - bh / 2) * height,
        "x2": (xc + bw / 2) * width,
        "y2": (yc + bh / 2) * height,
    }, None


def _validate_normalized_box(values: list[float]) -> str | None:
    if len(values) != 4:
        return "invalid_columns"
    xc, yc, bw, bh = values
    if not (0 <= xc <= 1 and 0 <= yc <= 1 and 0 < bw <= 1 and 0 < bh <= 1):
        return "invalid_bounds"
    if xc - bw / 2 < -1e-6 or yc - bh / 2 < -1e-6 or xc + bw / 2 > 1 + 1e-6 or yc + bh / 2 > 1 + 1e-6:
        return "box_outside_image"
    return None


def infer_label_mode(parts: list[str], preferred_mode: str = "detect") -> str | None:
    count = len(parts)
    if count == 1:
        return "classify"
    if preferred_mode == "segment" and count >= 7 and (count - 1) % 2 == 0:
        return "segment"
    if preferred_mode == "pose" and count >= 8 and (count - 5) % 3 == 0:
        return "pose"
    if count == 5:
        return "detect"
    if count == 9:
        return "obb"
    if count >= 7 and (count - 1) % 2 == 0:
        return "segment"
    if count >= 8 and (count - 5) % 3 == 0:
        return "pose"
    return None


def serialize_annotation(box: dict, image_size: tuple[int, int], expected_keypoints: int = 0) -> str | None:
    width, height = image_size
    kind = box.get("kind", "aabb")
    if kind == "classify":
        return str(box["cls"])
    if kind in {"obb", "polygon"}:
        points = box.get("points", [])
        if len(points) < (4 if kind == "obb" else 3):
            return None
        flat = " ".join(f"{value:.6f}" for x, y in points for value in (x / width, y / height))
        return f"{box['cls']} {flat}"
    if kind == "pose":
        base = _serialize_box_prefix(box, width, height)
        if base is None:
            return None
        keypoints = list(box.get("keypoints", []))
        target = max(expected_keypoints, len(keypoints))
        values = []
        for idx in range(target):
            if idx < len(keypoints):
                x, y, visible = keypoints[idx]
                values.extend([x / width, y / height, int(visible)])
            else:
                values.extend([0.0, 0.0, 0])
        return f"{base} " + " ".join(f"{value:.6f}" if isinstance(value, float) else str(value) for value in values)
    return _serialize_box_prefix(box, width, height)


def _serialize_box_prefix(box: dict, width: int, height: int) -> str | None:
    x1 = max(0, min(width, box["x1"]))
    y1 = max(0, min(height, box["y1"]))
    x2 = max(0, min(width, box["x2"]))
    y2 = max(0, min(height, box["y2"]))
    if x2 <= x1 or y2 <= y1:
        return None
    xc = ((x1 + x2) / 2) / width
    yc = ((y1 + y2) / 2) / height
    bw = (x2 - x1) / width
    bh = (y2 - y1) / height
    return f"{box['cls']} {xc:.6f} {yc:.6f} {bw:.6f} {bh:.6f}"
