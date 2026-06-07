# YOLO Annotator Desktop

Desktop YOLO annotation tool for detection, OBB, segmentation, pose, and classification datasets.

YOLO Annotator Desktop is a local-first image labeling app for people who want
to build YOLO datasets without uploading private images to a hosted service. It
uses ordinary image folders, label folders, class files, and a small `.yad.json`
project wrapper.

## What It Supports

| Workflow | Supported |
|---|---|
| YOLO detection boxes | Yes |
| Ultralytics YOLO OBB rotated boxes | Yes |
| YOLO segmentation polygons | Yes |
| YOLO pose keypoints | Yes |
| YOLO classification folders | Yes |
| YOLO `data.yaml` import/export | Yes |
| COCO JSON helpers | Yes |
| Pascal VOC XML helpers | Yes |
| Local quality checks | Yes |

## Install

Download the latest release from:

<https://github.com/sicaizhuang/yolo-annotator-desktop/releases>

Install a wheel:

```powershell
py -m pip install yolo_annotator_desktop-0.5.0-py3-none-any.whl
yolo-annotator-desktop
```

Or run from source:

```powershell
git clone https://github.com/sicaizhuang/yolo-annotator-desktop.git
cd yolo-annotator-desktop
py -m pip install -e .
yolo-annotator-desktop
```

## Typical Uses

- Label a new object-detection dataset for YOLOv5, YOLOv8, YOLOv10, YOLOv11,
  and other standard YOLO TXT workflows.
- Review and clean existing labels before training.
- Convert COCO or Pascal VOC projects into YOLO-friendly project folders.
- Build local datasets where images should not be uploaded to a web service.
- Annotate rotated objects with OBB labels.
- Prototype segmentation, pose, or classification datasets in the same desktop app.

## Project Links

- GitHub repository: <https://github.com/sicaizhuang/yolo-annotator-desktop>
- Latest release: <https://github.com/sicaizhuang/yolo-annotator-desktop/releases/tag/v0.5.0>
- English README: <https://github.com/sicaizhuang/yolo-annotator-desktop/blob/main/README.md>
- Chinese README: <https://github.com/sicaizhuang/yolo-annotator-desktop/blob/main/README_zh-CN.md>

