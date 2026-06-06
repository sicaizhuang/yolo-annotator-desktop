import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from yolo_annotator_desktop.project import create_project, load_project, remap_classes
from yolo_annotator_desktop.qc import export_yolo_dataset, inspect_project


class ProjectAndQCTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.project = create_project(self.root / "source", "test", ["cat", "dog"])
        for idx in range(5):
            Image.new("RGB", (80, 60), (idx * 20, 40, 80)).save(self.project.image_dir / f"image_{idx}.jpg")
        (self.project.label_dir / "image_0.txt").write_text("0 0.5 0.5 0.4 0.4\n", encoding="utf-8")
        (self.project.label_dir / "image_1.txt").write_text("1 0.5 0.5 0.2 0.2\n", encoding="utf-8")
        (self.project.label_dir / "image_2.txt").write_text("", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_project_round_trip(self):
        loaded = load_project(self.project.config_path)
        self.assertEqual(loaded.name, "test")
        self.assertEqual(loaded.class_names(), ["cat", "dog"])
        self.assertFalse(loaded.validate())

    def test_qc_counts_review_state(self):
        report = inspect_project(self.project)
        self.assertEqual(report["images"], 5)
        self.assertEqual(report["labeled_images"], 2)
        self.assertEqual(report["empty_reviewed_images"], 1)
        self.assertEqual(report["unreviewed_images"], 2)
        self.assertEqual(report["boxes"], 2)
        self.assertEqual(report["issue_count"], 0)

    def test_class_remap_creates_backup(self):
        result = remap_classes(self.project, ["dog", "cat"], {0: 1, 1: 0})
        self.assertTrue(Path(result["backup"]).exists())
        self.assertTrue(Path(result["classes_backup"]).exists())
        self.assertTrue((self.project.label_dir / "image_0.txt").read_text().startswith("1 "))
        self.assertTrue((self.project.label_dir / "image_1.txt").read_text().startswith("0 "))

    def test_export_dataset(self):
        result = export_yolo_dataset(self.project, self.root / "export", val_ratio=0.4, seed=7)
        self.assertEqual(result["train"], 3)
        self.assertEqual(result["val"], 2)
        self.assertTrue((self.root / "export" / "data.yaml").exists())
        report = json.loads((self.root / "export" / "source_qc_report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["images"], 5)


if __name__ == "__main__":
    unittest.main()
