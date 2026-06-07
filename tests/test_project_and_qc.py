import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from yolo_annotator_desktop.annotator import Annotator, natural_sort_key, process_is_running
from yolo_annotator_desktop.formats import export_coco, export_pascal_voc
from yolo_annotator_desktop.presets import load_classes_file, parse_class_text
from yolo_annotator_desktop.project import (
    create_project,
    create_project_from_coco,
    create_project_from_pascal_voc,
    create_project_from_yolo_yaml,
    load_project,
    remap_classes,
)
from yolo_annotator_desktop.qc import export_yolo_dataset, inspect_project
from yolo_annotator_desktop.safe_io import atomic_write_text
from yolo_annotator_desktop import state as state_module
from yolo_annotator_desktop.widgets import fit_window


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

    def test_project_loader_ignores_unknown_fields_and_rejects_future_version(self):
        payload = json.loads(self.project.config_path.read_text(encoding="utf-8"))
        payload["future_optional_field"] = "ignored"
        self.project.config_path.write_text(json.dumps(payload), encoding="utf-8")
        self.assertEqual(load_project(self.project.config_path).name, "test")
        payload["version"] = 999
        self.project.config_path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaises(ValueError):
            load_project(self.project.config_path)

    def test_project_creation_refuses_to_overwrite_workspace(self):
        with self.assertRaises(ValueError):
            create_project(self.project.config_path.parent, "overwrite", ["new"])

    def test_project_validation_reports_duplicate_classes(self):
        self.project.classes_path.write_text("cat\ncat\n", encoding="utf-8")
        self.assertTrue(any("duplicate" in error.lower() for error in self.project.validate()))

    def test_qc_counts_review_state(self):
        report = inspect_project(self.project)
        self.assertEqual(report["images"], 5)
        self.assertEqual(report["labeled_images"], 2)
        self.assertEqual(report["empty_reviewed_images"], 1)
        self.assertEqual(report["unreviewed_images"], 2)
        self.assertEqual(report["boxes"], 2)
        self.assertEqual(report["issue_count"], 0)

    def test_class_remap_creates_backup(self):
        (self.project.label_dir / "image_3.txt").write_text(
            "0 0.2 0.2 0.4 0.2 0.4 0.4 0.2 0.4\n",
            encoding="utf-8",
        )
        result = remap_classes(self.project, ["dog", "cat"], {0: 1, 1: 0})
        self.assertTrue(Path(result["backup"]).exists())
        self.assertTrue(Path(result["classes_backup"]).exists())
        self.assertTrue((self.project.label_dir / "image_0.txt").read_text().startswith("1 "))
        self.assertTrue((self.project.label_dir / "image_1.txt").read_text().startswith("0 "))
        self.assertTrue((self.project.label_dir / "image_3.txt").read_text().startswith("1 "))

    def test_export_dataset(self):
        result = export_yolo_dataset(self.project, self.root / "export", val_ratio=0.4, seed=7)
        self.assertEqual(result["train"], 3)
        self.assertEqual(result["val"], 2)
        self.assertTrue((self.root / "export" / "data.yaml").exists())
        report = json.loads((self.root / "export" / "source_qc_report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["images"], 5)

    def test_export_refuses_destination_inside_source_images(self):
        with self.assertRaises(ValueError):
            export_yolo_dataset(self.project, self.project.image_dir / "bad_export")
        with self.assertRaises(ValueError):
            export_pascal_voc(self.project, self.project.label_dir / "bad_voc")

    def test_single_image_export_keeps_a_training_image(self):
        single = create_project(self.root / "single", "single", ["object"])
        Image.new("RGB", (20, 20), "white").save(single.image_dir / "only.jpg")
        result = export_yolo_dataset(single, self.root / "single_export")
        self.assertEqual(result["train"], 1)
        self.assertEqual(result["val"], 0)

    def test_qc_accepts_yolo_obb(self):
        self.project.annotation_mode = "obb"
        (self.project.label_dir / "image_0.txt").unlink()
        (self.project.label_dir / "image_1.txt").unlink()
        (self.project.label_dir / "image_3.txt").write_text(
            "0 0.2 0.2 0.4 0.2 0.4 0.4 0.2 0.4\n",
            encoding="utf-8",
        )
        report = inspect_project(self.project)
        self.assertEqual(report["blocking_issue_count"], 0)
        self.assertEqual(report["boxes"], 1)

    def test_qc_blocks_mixed_detect_and_obb_export(self):
        (self.project.label_dir / "image_3.txt").write_text(
            "0 0.2 0.2 0.4 0.2 0.4 0.4 0.2 0.4\n",
            encoding="utf-8",
        )
        report = inspect_project(self.project)
        self.assertIn("mixed_annotation_formats", [issue["type"] for issue in report["issues"]])
        with self.assertRaises(ValueError):
            export_yolo_dataset(self.project, self.root / "mixed_export")

    def test_import_yolo_yaml(self):
        dataset = self.root / "dataset"
        (dataset / "images" / "train").mkdir(parents=True)
        (dataset / "labels" / "train").mkdir(parents=True)
        yaml_path = dataset / "data.yaml"
        yaml_path.write_text(
            "path: .\ntrain: images/train\nval: images/val\nnames:\n  0: cat\n  1: dog\n",
            encoding="utf-8",
        )
        imported = create_project_from_yolo_yaml(self.root / "imported", yaml_path, "train")
        self.assertEqual(imported.class_names(), ["cat", "dog"])
        self.assertEqual(imported.image_dir, (dataset / "images" / "train").resolve())
        self.assertEqual(imported.label_dir, (dataset / "labels" / "train").resolve())

    def test_import_yolo_yaml_image_list_split(self):
        dataset = self.root / "list_dataset"
        (dataset / "images" / "train").mkdir(parents=True)
        (dataset / "labels" / "train").mkdir(parents=True)
        for name in ("a.jpg", "b.jpg"):
            Image.new("RGB", (20, 20), "white").save(dataset / "images" / "train" / name)
        (dataset / "labels" / "train" / "a.txt").write_text("0 0.5 0.5 0.4 0.4\n", encoding="utf-8")
        (dataset / "train.txt").write_text("images/train/a.jpg\nimages/train/b.jpg\n", encoding="utf-8")
        (dataset / "data.yaml").write_text(
            "path: .\ntrain: train.txt\nnames: [part]\n",
            encoding="utf-8",
        )
        imported = create_project_from_yolo_yaml(self.root / "list_import", dataset / "data.yaml", "train")
        self.assertEqual(imported.image_dir, (dataset / "images").resolve())
        self.assertEqual(imported.label_dir, (dataset / "labels").resolve())
        self.assertTrue(imported.filter_order)
        self.assertEqual(imported.order_path.read_text(encoding="utf-8").splitlines(), ["train/a.jpg", "train/b.jpg"])
        self.assertEqual(inspect_project(imported)["images"], 2)

    def test_import_yolo_yaml_multi_directory_split(self):
        dataset = self.root / "multi_dataset"
        for folder in ("batch_a", "batch_b"):
            (dataset / "images" / folder).mkdir(parents=True)
            (dataset / "labels" / folder).mkdir(parents=True)
            Image.new("RGB", (20, 20), "white").save(dataset / "images" / folder / f"{folder}.jpg")
        (dataset / "data.yaml").write_text(
            "path: .\ntrain:\n  - images/batch_a\n  - images/batch_b\nnames:\n  0: part\n",
            encoding="utf-8",
        )
        imported = create_project_from_yolo_yaml(self.root / "multi_import", dataset / "data.yaml", "train")
        self.assertEqual(imported.image_dir, (dataset / "images").resolve())
        self.assertEqual(imported.label_dir, (dataset / "labels").resolve())
        self.assertEqual(inspect_project(imported)["images"], 2)

    def test_class_helpers_accept_common_inputs(self):
        self.assertEqual(parse_class_text("cat, dog\n# comment\nbird"), ["cat", "dog", "bird"])
        classes_file = self.root / "classes.names"
        classes_file.write_text("widget\npart\n", encoding="utf-8")
        self.assertEqual(load_classes_file(classes_file), ["widget", "part"])

    def test_nested_images_use_mirrored_labels_and_export(self):
        nested_image = self.project.image_dir / "batch_a" / "nested.jpg"
        nested_image.parent.mkdir()
        Image.new("RGB", (40, 30), "white").save(nested_image)
        nested_label = self.project.label_path_for(nested_image, prefer_existing=False)
        nested_label.parent.mkdir(parents=True)
        nested_label.write_text("0 0.5 0.5 0.4 0.4\n", encoding="utf-8")
        report = inspect_project(self.project)
        self.assertEqual(report["images"], 6)
        self.assertEqual(report["boxes"], 3)
        export_yolo_dataset(self.project, self.root / "nested_export", val_ratio=0.2, seed=3)
        exported = list((self.root / "nested_export" / "labels").rglob("batch_a/nested.txt"))
        self.assertEqual(len(exported), 1)

    def test_nested_duplicate_stems_map_to_distinct_labels(self):
        for folder in ("a", "b"):
            image = self.project.image_dir / folder / "same.jpg"
            image.parent.mkdir()
            Image.new("RGB", (20, 20), "white").save(image)
            label = self.project.label_path_for(image, prefer_existing=False)
            label.parent.mkdir(parents=True)
            label.write_text("0 0.5 0.5 0.5 0.5\n", encoding="utf-8")
        report = inspect_project(self.project)
        self.assertNotIn("duplicate_label_target", report["issue_types"])
        self.assertEqual(report["boxes"], 4)

    def test_underscore_image_directory_is_not_silently_skipped(self):
        folder = self.project.image_dir / "_camera_1"
        folder.mkdir()
        Image.new("RGB", (20, 20), "white").save(folder / "visible.jpg")
        self.assertEqual(inspect_project(self.project)["images"], 6)

    def test_tiff_images_are_supported(self):
        Image.new("RGB", (20, 20), "white").save(self.project.image_dir / "visible.tiff")
        self.assertEqual(inspect_project(self.project)["images"], 6)

    def test_qc_reports_corrupt_image(self):
        (self.project.image_dir / "broken.jpg").write_bytes(b"not an image")
        report = inspect_project(self.project)
        self.assertIn("corrupt_image", report["issue_types"])
        with self.assertRaises(ValueError):
            export_yolo_dataset(self.project, self.root / "blocked_export")

    def test_qc_reports_degenerate_obb(self):
        self.project.annotation_mode = "obb"
        for path in self.project.label_dir.glob("*.txt"):
            path.unlink()
        (self.project.label_dir / "image_0.txt").write_text(
            "0 0.2 0.2 0.3 0.3 0.4 0.4 0.5 0.5\n",
            encoding="utf-8",
        )
        report = inspect_project(self.project)
        self.assertIn("degenerate_obb", report["issue_types"])

    def test_qc_reports_exact_duplicate_box_and_blocks_export(self):
        (self.project.label_dir / "image_0.txt").write_text(
            "0 0.5 0.5 0.4 0.4\n0 0.5 0.5 0.4 0.4\n",
            encoding="utf-8",
        )
        report = inspect_project(self.project)
        self.assertEqual(report["issue_types"]["exact_duplicate_box"], 1)
        with self.assertRaises(ValueError):
            export_yolo_dataset(self.project, self.root / "duplicate_export")

    def test_qc_reports_duplicate_image_content_as_warning(self):
        duplicate = self.project.image_dir / "duplicate.jpg"
        duplicate.write_bytes((self.project.image_dir / "image_0.jpg").read_bytes())
        report = inspect_project(self.project)
        self.assertIn("duplicate_image_content", report["issue_types"])
        self.assertEqual(report["severity_counts"]["warning"], 1)
        self.assertEqual(report["blocking_issue_count"], 0)

    def test_qc_reports_unused_class_as_warning(self):
        self.project.classes_path.write_text("cat\ndog\nunused\n", encoding="utf-8")
        report = inspect_project(self.project)
        self.assertIn("unused_class", report["issue_types"])
        self.assertEqual(report["blocking_issue_count"], 0)

    def test_atomic_write_text_replaces_complete_file(self):
        target = self.root / "atomic.txt"
        target.write_text("old", encoding="utf-8")
        atomic_write_text(target, "new\ncontent\n")
        self.assertEqual(target.read_text(encoding="utf-8"), "new\ncontent\n")
        self.assertFalse(list(self.root.glob(".atomic.txt.*.tmp")))

    def test_recent_project_state_round_trip(self):
        original = state_module.STATE_PATH
        state_module.STATE_PATH = self.root / "state.json"
        try:
            state_module.remember_project(self.project.config_path)
            loaded = state_module.load_state()
            self.assertEqual(loaded["last_project"], str(self.project.config_path.resolve()))
            self.assertEqual(loaded["recent_projects"][0], str(self.project.config_path.resolve()))
        finally:
            state_module.STATE_PATH = original

    def test_export_coco(self):
        result = export_coco(self.project, self.root / "coco.json")
        payload = json.loads((self.root / "coco.json").read_text(encoding="utf-8"))
        self.assertEqual(result["images"], 5)
        self.assertEqual(result["annotations"], 2)
        self.assertEqual([item["name"] for item in payload["categories"]], ["cat", "dog"])

    def test_coco_round_trip_import(self):
        export_coco(self.project, self.root / "coco.json")
        imported = create_project_from_coco(self.root / "coco_import", self.root / "coco.json", self.project.image_dir)
        report = inspect_project(imported)
        self.assertEqual(report["images"], 5)
        self.assertEqual(report["boxes"], 2)
        self.assertEqual(imported.class_names(), ["cat", "dog"])

    def test_coco_obb_round_trip_preserves_rotation_format(self):
        self.project.annotation_mode = "obb"
        for path in self.project.label_dir.glob("*.txt"):
            path.unlink()
        (self.project.label_dir / "image_0.txt").write_text(
            "0 0.2 0.2 0.5 0.3 0.4 0.6 0.1 0.5\n",
            encoding="utf-8",
        )
        export_coco(self.project, self.root / "obb.json")
        imported = create_project_from_coco(
            self.root / "coco_obb_import",
            self.root / "obb.json",
            self.project.image_dir,
            "obb",
        )
        label = imported.label_dir / "image_0.txt"
        self.assertEqual(len(label.read_text(encoding="utf-8").split()), 9)
        self.assertEqual(inspect_project(imported)["blocking_issue_count"], 0)

    def test_export_pascal_voc(self):
        result = export_pascal_voc(self.project, self.root / "voc")
        self.assertEqual(result["images"], 5)
        self.assertTrue((self.root / "voc" / "image_0.xml").exists())

    def test_pascal_voc_round_trip_import(self):
        export_pascal_voc(self.project, self.root / "voc")
        imported = create_project_from_pascal_voc(self.root / "voc_import", self.root / "voc", self.project.image_dir)
        report = inspect_project(imported)
        self.assertEqual(report["images"], 5)
        self.assertEqual(report["boxes"], 2)

    def test_export_pascal_voc_rejects_obb(self):
        self.project.annotation_mode = "obb"
        for path in self.project.label_dir.glob("*.txt"):
            path.unlink()
        (self.project.label_dir / "image_0.txt").write_text(
            "0 0.2 0.2 0.4 0.2 0.4 0.4 0.2 0.4\n",
            encoding="utf-8",
        )
        with self.assertRaises(ValueError):
            export_pascal_voc(self.project, self.root / "voc_obb")

    def test_obb_corner_resize_preserves_rectangle(self):
        box = {"kind": "obb", "cls": 0, "points": [(10.0, 10.0), (30.0, 10.0), (30.0, 20.0), (10.0, 20.0)]}
        Annotator.resize_obb_corner(box, 0, (5.0, 7.0))
        p0, p1, p2, p3 = box["points"]
        self.assertEqual(p0, (5.0, 7.0))
        self.assertEqual(p2, (30.0, 20.0))
        edge_a = (p1[0] - p0[0], p1[1] - p0[1])
        edge_b = (p3[0] - p0[0], p3[1] - p0[1])
        self.assertAlmostEqual(edge_a[0] * edge_b[0] + edge_a[1] * edge_b[1], 0.0, places=6)

    def test_natural_sort_key_orders_numbered_images(self):
        values = ["image_10.jpg", "image_2.jpg", "image_1.jpg"]
        self.assertEqual(sorted(values, key=natural_sort_key), ["image_1.jpg", "image_2.jpg", "image_10.jpg"])

    def test_current_process_is_reported_running(self):
        import os

        self.assertTrue(process_is_running(os.getpid()))

    def test_label_text_contrast(self):
        self.assertEqual(Annotator.contrast_text_color("#ffffff"), "#111111")
        self.assertEqual(Annotator.contrast_text_color("#002244"), "#ffffff")

    def test_window_size_fits_small_screen(self):
        class FakeWindow:
            geometry_value = ""
            minimum = ()

            @staticmethod
            def winfo_screenwidth():
                return 800

            @staticmethod
            def winfo_screenheight():
                return 600

            def geometry(self, value):
                self.geometry_value = value

            def minsize(self, width, height):
                self.minimum = (width, height)

        window = FakeWindow()
        size = fit_window(window, (1380, 900), minimum=(880, 560), margin=(100, 160))
        self.assertEqual(size, (700, 440))
        self.assertEqual(window.minimum, (700, 440))

    def test_annotator_preserves_invalid_label_rows_when_saving(self):
        label = self.project.label_dir / "image_0.txt"
        invalid = "broken label row"
        label.write_text(f"0 0.5 0.5 0.4 0.4\n{invalid}\n", encoding="utf-8")
        annotator = Annotator.__new__(Annotator)
        annotator.img = Image.new("RGB", (80, 60), "white")
        annotator.classes = ["cat", "dog"]
        annotator.current_label_path = lambda: label
        annotator.boxes = annotator.load_labels()
        self.assertEqual(len(annotator.boxes), 1)
        self.assertEqual(annotator.preserved_label_lines, [invalid])

        annotator.images = [self.project.image_dir / "image_0.jpg"]
        annotator.dirty = False
        annotator.keep_empty = True
        annotator.image_status_cache = {}
        annotator.current_image_path = lambda: annotator.images[0]
        annotator.refresh_image_browser = lambda: None
        annotator.update_info = lambda *_args: None
        annotator.save_labels(silent=True)
        self.assertIn(invalid, label.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
