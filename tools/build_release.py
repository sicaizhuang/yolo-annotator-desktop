from __future__ import annotations

import argparse
from pathlib import Path
import zipfile


EXCLUDED_PARTS = {
    ".git",
    ".github-cache",
    ".idea",
    ".pytest_cache",
    ".venv",
    ".vscode",
    "__pycache__",
    "build",
    "dist",
    "projects",
}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".log"}
EXCLUDED_NAMES = {"run_ocg_project.cmd", "ocg_qc_report.json"}
FORBIDDEN_TEXT = (
    "D:" + "\\MODEL\\YOLO_Tutorial",
    "C:" + "\\Users\\CHASER",
    "192.168." + "0.177",
)


def is_public_file(path: Path, root: Path) -> bool:
    relative = path.relative_to(root)
    if any(part in EXCLUDED_PARTS or part.endswith(".egg-info") for part in relative.parts):
        return False
    if path.name in EXCLUDED_NAMES or path.suffix.lower() in EXCLUDED_SUFFIXES:
        return False
    return path.is_file()


def validate_text(path: Path):
    if path.suffix.lower() not in {".py", ".md", ".toml", ".txt", ".json", ".yml", ".yaml", ".cmd", ".ps1"}:
        return
    text = path.read_text(encoding="utf-8-sig", errors="ignore")
    for forbidden in FORBIDDEN_TEXT:
        if forbidden in text:
            raise RuntimeError(f"Private value found in public file {path}: {forbidden}")


def build_release(root: Path, output: Path):
    files = [path for path in sorted(root.rglob("*")) if is_public_file(path, root)]
    for path in files:
        validate_text(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            archive.write(path, Path("YOLO_Annotator_Desktop") / path.relative_to(root))
    return files


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    files = build_release(root, Path(args.output).resolve())
    print(f"release={Path(args.output).resolve()}")
    print(f"files={len(files)}")


if __name__ == "__main__":
    main()
