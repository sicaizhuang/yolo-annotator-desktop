from __future__ import annotations

from pathlib import Path

from .safe_io import atomic_write_json


STATE_PATH = Path.home() / ".yolo_annotator_desktop.json"
DEFAULT_STATE = {
    "recent_projects": [],
    "last_project": "",
    "preferences": {
        "show_labels": True,
        "smooth_image": True,
        "image_browser_visible": True,
        "annotation_panel_visible": True,
        "autosave": True,
    },
}


def load_state() -> dict:
    import json

    state = {
        "recent_projects": [],
        "last_project": "",
        "preferences": dict(DEFAULT_STATE["preferences"]),
    }
    try:
        loaded = json.loads(STATE_PATH.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, TypeError):
        return state
    if isinstance(loaded, dict):
        state["last_project"] = str(loaded.get("last_project", ""))
        recent = loaded.get("recent_projects", [])
        if isinstance(recent, list):
            state["recent_projects"] = [str(item) for item in recent if item][:12]
        preferences = loaded.get("preferences", {})
        if isinstance(preferences, dict):
            state["preferences"].update(preferences)
    return state


def save_state(state: dict) -> None:
    atomic_write_json(STATE_PATH, state)


def remember_project(path: str | Path) -> dict:
    resolved = str(Path(path).resolve())
    state = load_state()
    recent = [item for item in state["recent_projects"] if item != resolved and Path(item).exists()]
    state["recent_projects"] = [resolved, *recent][:12]
    state["last_project"] = resolved
    save_state(state)
    return state


def forget_missing_projects() -> dict:
    state = load_state()
    state["recent_projects"] = [item for item in state["recent_projects"] if Path(item).exists()]
    if state["last_project"] and not Path(state["last_project"]).exists():
        state["last_project"] = ""
    save_state(state)
    return state
