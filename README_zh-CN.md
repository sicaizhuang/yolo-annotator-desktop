# YOLO Annotator Desktop

一个本地优先的桌面 YOLO 标注工具，面向目标检测、旋转框 OBB、分割、多关键点姿态和图像分类数据集。

[English](README.md) | [在线文档](https://sicaizhuang.github.io/yolo-annotator-desktop/)

YOLO Annotator Desktop 不需要 Docker、浏览器服务、账号、数据库或上传图片。它适合在本地整理和标注私有数据集，支持 YOLO TXT 导入导出、`data.yaml` 导入、COCO/VOC 辅助转换、质量检查、类别重映射、自动保存、撤销/重做和项目备份。

这个工具最初来自一个真实的电子元器件识别和分拣项目：标注速度、保存安全、框选手感、离线运行和训练前质检，比搭一个大型网页平台更重要。开源版本已经整理为更通用的 YOLO 数据集标注软件。

## 为什么用它

- 完全本地运行，适合私有数据集和离线标注。
- 一个软件覆盖 YOLO 检测框、旋转框、分割、多关键点和分类。
- 用小型 `.yad.json` 项目文件管理普通图片目录、标签目录和类别文件。
- 训练前可以做质量检查，提前发现坏图、错类、异常几何和重复标注。
- 编辑更安全：原子保存、自动备份、撤销/重做，并保留异常标签行。

## 支持的 YOLO 任务

| 任务 | 标签形态 | 状态 |
|---|---|---|
| Detection 检测框 | `class x_center y_center width height` | 支持 |
| OBB 旋转框 | `class x1 y1 x2 y2 x3 y3 x4 y4` | 支持 |
| Segmentation 分割 | `class x1 y1 x2 y2 ...` 多边形 | 支持 |
| Pose 姿态 | 检测框加关键点，并导出 `kpt_shape` | 支持 |
| Classification 分类 | 导出为 YOLO 分类目录结构 | 支持 |

## 快速开始

从 Release 下载 wheel 后安装：

```powershell
py -m pip install yolo_annotator_desktop-0.5.0-py3-none-any.whl
yolo-annotator-desktop
```

从源码运行：

```powershell
git clone https://github.com/sicaizhuang/yolo-annotator-desktop.git
cd yolo-annotator-desktop
py -m pip install -e .
yolo-annotator-desktop
```

Windows 用户也可以直接双击 `run_windows.cmd`。第一次运行会自动创建本地虚拟环境并安装依赖。之后可以双击 `launch_windows.vbs` 静默启动，或者运行一次 `create_desktop_shortcut.cmd` 创建桌面快捷方式。

## 主要功能

- 本地桌面 UI，不需要 Docker、浏览器、账号、数据库或服务器。
- 图片列表支持搜索、已审核/已标注/空图过滤，并能显式标记已审核空图。
- 支持绘制、选择、移动、缩放、微调、改类别、复制、粘贴、重复和删除框。
- 支持三点式旋转矩形，按标准 YOLO OBB 四点格式保存。
- 支持 YOLO 分割多边形标签。
- 支持 YOLO Pose 检测框加关键点标签，并能导出 `kpt_shape`。
- 支持图像分类项目，并导出为 YOLO 分类文件夹结构。
- 自动保存使用原子写入，支持撤销/重做、会话备份、项目锁和崩溃日志。
- 遇到异常标签行会保留原始内容，不会在保存时悄悄丢弃。
- 支持便携 `.yad.json` 项目和嵌套图片/标签目录。
- 可从空项目、已有图片目录、YOLO `data.yaml`、COCO JSON、Pascal VOC XML 创建或导入项目。
- YOLO YAML 导入支持普通目录 split、`train.txt` 图片清单 split 和多目录 split。
- 内置类别模板：单类别、COCO 80、Pascal VOC 20、电子元器件入门、工业缺陷入门。
- 类别可以手动输入，也可以从 `classes.txt`、`.names` 或 YOLO `data.yaml` 读取。
- 可导出 YOLO train/val 数据集、COCO JSON 或 Pascal VOC XML。
- 质量检查覆盖损坏图片、非法几何、类别错误、格式混用、重复框、重复图片、孤立标签和未使用类别。
- 类别管理支持添加、重命名、删除、排序；修改 ID 前会完整备份并安全重映射。
- 支持 JPG、JPEG、PNG、BMP、WebP、TIFF 和嵌套数据集。

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
  "keypoints": "",
  "version": 1
}
```

路径可以是相对项目文件的路径，也可以是绝对路径。普通 YOLO Detect 标签格式：

```text
class_id x_center y_center width height
```

YOLO OBB 旋转框格式：

```text
class_id x1 y1 x2 y2 x3 y3 x4 y4
```

YOLO 分割格式：

```text
class_id x1 y1 x2 y2 x3 y3 ...
```

Pose 标签格式：

```text
class_id x_center y_center width height kpt_x kpt_y visible ...
```

所有坐标都归一化到 `0..1`。

## 常用操作

| 操作 | 控制 |
|---|---|
| 选择/移动 | `V`，然后拖动选中的对象 |
| 普通矩形框 | `B`，按住左键拖动 |
| 三点式旋转框 | `R`，拖出第一条边，松开后移动鼠标确定宽度，再单击 |
| 分割多边形 | `P`，逐点点击，按 `Enter` 或点击第一个点完成 |
| 姿态关键点 | 先绘制或选中姿态框，再按 `K` 依次点击关键点 |
| 选中框 | 左键、右键或从对象列表选择 |
| 拉伸框 | 拖动白色控制点 |
| 微调选中框 | 方向键；按住 `Shift` 每次移动 10 像素 |
| 复制/粘贴/重复 | `Ctrl+C` / `Ctrl+V` / `Ctrl+D` |
| 缩放/平移 | 鼠标滚轮 / 右键或中键拖动 |
| 上一张/下一张 | `A` / `D` |
| 下一张未审核 | `U` |
| 标记为空图 | `N` |
| 改类别 | 选择类别后按 `C` |
| 撤销/重做 | `Ctrl+Z` / `Ctrl+Y` |
| 隐藏标签文字 | `H` |
| 保存 | `Ctrl+S` |
| 删除选中对象 | `Delete` |

## 数据安全

标签、项目、偏好和报告都使用原子写入。每次会话首次修改某个标签前会自动创建恢复副本。类别 ID 修改前会完整备份。导出不会修改源图片或源标签，也不允许把导出目录放进源图片或源标签目录。

## 开发

```powershell
py -m pip install -e .
py -m unittest discover -s tests -v
```

贡献前请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 搜索关键词

YOLO 标注工具、YOLO 数据集编辑器、目标检测标注、旋转框标注、OBB 标注、图像分割标注、姿态关键点标注、分类数据集工具、COCO 转 YOLO、VOC 转 YOLO、Ultralytics YOLO 数据集、本地图像标注。

## 许可证

MIT
