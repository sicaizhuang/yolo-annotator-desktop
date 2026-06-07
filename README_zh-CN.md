# YOLO Annotator Desktop

一个快速、本地优先、无需 Docker 的 YOLO 桌面标注工具。

它来自真实的元器件识别与抓取项目，但开源版面向更通用的目标检测、旋转框检测和数据集整理流程：标注要顺手，保存要安全，导入导出要尽量兼容常见 YOLO 数据集。

## 主要功能

- 完全本地运行，不需要浏览器、账号、数据库或服务器。
- 支持普通 YOLO Detect 矩形框和 Ultralytics YOLO OBB 旋转框。
- 图片列表支持搜索、筛选、审核状态、已标注状态和空图确认。
- 支持框选、选择、移动、拉伸、微调、复制、粘贴、重复、改类别和删除。
- 三点式旋转框：拖出第一条边，松开后移动鼠标确定宽度，再单击完成。
- 自动保存使用原子写入；支持撤销/重做、会话备份、项目锁和崩溃日志。
- 遇到异常标签行会保留原始内容，不会在保存时悄悄丢弃。
- 支持便携 `.yad.json` 项目和嵌套图片/标签目录。
- 可从空项目、已有目录、YOLO `data.yaml`、COCO JSON、Pascal VOC XML 创建或导入。
- YOLO YAML 支持单目录 split、`train.txt` 图片清单 split、多目录 split。
- 类别可手填，也可从 `classes.txt`、`.names`、YOLO `data.yaml` 读取。
- 内置类别模板：单类别、COCO 80、Pascal VOC 20、电子元件入门、工业缺陷入门。
- 可导出 YOLO train/val 数据集、COCO JSON、Pascal VOC XML。
- 质量检查覆盖损坏图片、非法几何、类别错误、格式混用、重复框、重复图片、孤立标签和未使用类别。
- 类别管理支持添加、重命名、删除、排序；修改 ID 前会完整备份并安全重映射。
- 支持 JPG、JPEG、PNG、BMP、WebP、TIF、TIFF。

## Windows 快速开始

双击 `run_windows.cmd`。首次运行会创建本地虚拟环境并安装依赖。

首次运行完成后，可以双击 `launch_windows.vbs` 静默启动。运行一次 `create_desktop_shortcut.cmd` 可以创建桌面快捷方式。

也可以手动运行：

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m yolo_annotator_desktop
```

直接打开指定项目：

```powershell
.\.venv\Scripts\python.exe -m yolo_annotator_desktop path\to\project.yad.json
```

命令行创建项目：

```powershell
# 用 COCO 类别新建空项目
.\.venv\Scripts\yad-create.exe D:\datasets\my_project --preset "COCO 80"

# 接管已有图片和标签目录
.\.venv\Scripts\yad-create.exe D:\datasets\wrapped --images D:\data\images --labels D:\data\labels --classes-file D:\data\classes.txt

# 从 YOLO data.yaml 导入，支持 train.txt 和多目录 split
.\.venv\Scripts\yad-create.exe D:\datasets\from_yaml --yolo-yaml D:\data\data.yaml --split train
```

## 项目格式

每个项目使用一个小型 JSON 文件：

```json
{
  "name": "example",
  "images": "images",
  "labels": "labels",
  "classes": "classes.txt",
  "keep_empty": true,
  "order_file": "",
  "filter_order": false,
  "annotation_mode": "detect",
  "version": 1
}
```

普通 YOLO Detect 标签格式：

```text
class_id x_center y_center width height
```

YOLO OBB 旋转框格式：

```text
class_id x1 y1 x2 y2 x3 y3 x4 y4
```

所有坐标均归一化到 `0..1`。

## 导入来源

软件内部总是用 `.yad.json` 项目来管理状态，但数据来源不必一开始就是项目：

- 空白托管数据集。
- 已有图片目录，可选已有标签目录。
- YOLO `data.yaml`，split 指向单个图片目录。
- YOLO `data.yaml`，split 指向 `train.txt` / `val.txt` 图片清单。
- YOLO `data.yaml`，split 是多个图片目录或图片清单文件。
- COCO JSON + 图片根目录。
- Pascal VOC XML 文件夹 + 图片根目录。

导入外部数据时不会修改源图片。对于图片清单和多目录 split，软件会在项目工作目录里写一个小的顺序文件，只显示被选中的 split。

## 常用操作

| 操作 | 按键 |
|---|---|
| 选择/移动 | `V`，然后拖动框 |
| 普通矩形框 | `B`，按住左键拖动 |
| 三点式旋转框 | `R`，拖出第一条边，松开后移动鼠标确定宽度，再单击 |
| 选中框 | 左键点击、右键点击，或从对象列表选择 |
| 拉伸框 | 拖动白色控制点 |
| 微调选中框 | 方向键；按住 `Shift` 每次移动 10 像素 |
| 复制/粘贴/重复 | `Ctrl+C` / `Ctrl+V` / `Ctrl+D` |
| 缩放/平移 | 鼠标滚轮 / 右键或中键拖动 |
| 上一张/下一张 | `A` / `D` |
| 下一张未审核 | `U` |
| 标记为空图 | `N` |
| 撤销/重做 | `Ctrl+Z` / `Ctrl+Y` |
| 隐藏/显示标签文字 | `H` |
| 保存 | `Ctrl+S` |
| 删除选中框 | `Delete` |

## 数据安全

标签、项目、偏好和报告都使用原子写入。每次会话首次修改某个标签前会自动创建恢复副本。类别 ID 修改前会完整备份。导出不会修改源图片或源标签，也不允许把导出目录放进源图片或源标签目录。

## 开发

```powershell
py -m pip install -e .
py -m unittest discover -s tests -v
```

许可证：MIT。
