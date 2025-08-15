## 面向「GUI Agent」的训练数据生产

我们希望最终得到一个能够像用户一样自动操作桌面应用（App）的「GUI Agent」。其核心能力包括理解界面、定位并选择正确控件、执行点击/输入/拖拽等操作并完成目标任务。为达成这一目标，第一阶段的任务定义为：

训练一个模型：
- 模型输入：某个应用在某个页面的「截图」
- 模型输出：页面上「所有可交互元素（如按钮）」的精准定位（边界框/坐标）与语义功能（类别/名称/上下文）

而本项目的核心目标，是为该模型的训练提供高质量数据。
为此，本项目提供了端到端的数据采集能力（启动应用 → 截屏 → 拉取 UI 树 → 存盘 → 可视化），并约定了数据字段与目录结构，便于后续标注、清洗与训练。具体如下：

- 目标：构建「截图 → 元素检测与功能识别」的数据集与生产流程
- 手段：在被控 Windows 端运行自动化服务，远程启动应用、抓取屏幕并抽取 UI 树；在主控端批量驱动与落盘
- 产物：成对的截图与结构化 UI 元素（矩形框、类型、名称、上下文等），并提供可视化 Overlay 用于质检
- 范围：优先覆盖常见应用技术栈（Win32/UWP/Electron/Qt/Java 等）与高频场景，逐步扩展规模与多样性


## GUI Project Controller — Windows 远程 GUI 自动化与采集

一个基于 FastAPI 的「客户端-服务端」架构，用于在目标 Windows 机器上远程启动应用、抓取屏幕、提取 UI 控件树并执行基础交互（点击、关闭等），并在控制端保存截图与 UI 结构标注。你主要会使用以下两个入口：

- `client/windows_automation_server.py`：运行在被控 Windows 机器的 HTTP 服务（FastAPI）
- `server/click.py`：运行在主控端的示例控制脚本（发起请求、保存数据、绘制可视化）

### 关键特性

- 启动/检测应用：按可执行文件路径启动或复用已运行进程，精确匹配 UI 主窗口 PID
- UI 树提取：递归导出控件树（名称、类型、可见性、矩形、可点击等）
- 截屏与下载：服务端抓图并可通过 URL 下载，控制端自动保存
- 交互控制：坐标点击、优雅关闭（Close/WM_CLOSE/kill）单进程或进程树
- 进程辅助：按 exe 路径列举进程、收集子进程，按 PID/关键字回溯窗口
- 可视化：把 UI 控件框绘制到截图上，输出带标注的 overlay 图片

### 目录结构

```text
GUI_project_cont/
  client/
    windows_automation_server.py    # FastAPI 服务端：UI 自动化与截图的实际执行者
    start_server.bat                # Windows 一键启动脚本（uvicorn）
    start_script.sh                 # 兼容的 shell 启动脚本
  server/
    click.py                        # 主控示例：打开应用、抓图、拉取 UI 树并保存与可视化
    controller.py                   # 扩展示例：批量点击/采集逻辑（更完整的流程控制）
    utils.py                        # 颜色等辅助常量
  environment.yml                   # Conda 环境定义（Python 3.11 + FastAPI 等依赖）
  README.md                         # 本说明文件
  todolist.md                       # 待办与改进点
```

---

## 快速开始（建议）

下述步骤分别在「被控端（Windows 客户端）」与「主控端」执行。两端可以是同一台电脑（本地回环 127.0.0.1），也可以是不同机器（请替换为被控端的 IP）。

### 1) 准备运行环境

依赖已在 `environment.yml` 中定义：

- Python 3.11
- FastAPI、Uvicorn
- Pillow、python-multipart
- pywinauto、uiautomation、psutil、requests

创建并激活 Conda 环境：

```bash
conda env create -f environment.yml
conda activate win-gui
# 后续如需加包：conda env update -f environment.yml
```

必要的系统前提（Windows 被控端）：

- 以「管理员权限」运行终端，以便自动化框架能操控受 UAC 保护的程序
- 建议在被控端提前创建目录 `D:\screenshots`（见下文截图存储说明）

### 2) 启动被控端 HTTP 服务（Client）

有两种方式：

- 方式 A：一键脚本（使用 uvicorn 的模块加载方式）
  - 双击或在命令行运行：`client/start_server.bat`
  - 默认监听 `0.0.0.0:5000`
  - 截图保存目录使用代码顶部常量 `SHARED_DIR = D:\\screenshots`，因此请确保该目录存在

- 方式 B：以脚本形式运行（可自定义截图共享目录）
  - 在命令行运行：
    ```bash
    python client/windows_automation_server.py --shared-dir D:\screenshots
    ```
  - 同样会监听 `0.0.0.0:5000`

验证服务是否就绪（本机示例）：

```bash
curl -X POST http://127.0.0.1:5000/screenshot
```

若返回 JSON 且包含下载 URL（如 `http://<ip>:5000/screenshot/xxx.png`），即表示服务正常。

### 3) 运行主控端示例（Server）

编辑 `server/click.py` 末尾的 `app_infos`，设置目标应用信息（示例）：

```python
app_infos = {
    "app_name": "notepad",
    "exe_path": r"C:\\Windows\\System32\\notepad.exe",
    "wait_time": 5
}
```

运行：

```bash
python server/click.py
```

运行完成后，可在 `data/<app_name>/` 下看到：

- 原始截图：`*_screenshot.png`
- UI 结构 JSON：`*_layout.json`
- 带 UI 边框与类型标注的截图：`*_overlay.png`

> 说明：`server/controller.py` 提供了更完整的批量流程（如更稳健的 PID 跟踪、批量关闭等），可根据需要使用。

---

## 客户端 API（FastAPI）

基地址：`http://<client-ip>:5000/`

- POST `/open_app`
  - 入参：`{ "path": "C:\\Path\\To\\YourApp.exe" }`
  - 返回：`{ status, path, pid, window_title }`

- POST `/screenshot`
  - 入参：无
  - 返回：`{ status: "ok", filename, path, url }`
  - GET `/screenshot/{filename}` 直接下载图片

- POST `/get_ui_tree`
  - 入参：
    ```json
    {
      "name": "app_name",
      "path": "C:\\Path\\To\\YourApp.exe",
      "pids": [1234, 5678]
    }
    ```
  - 返回：`{ status: "ok", ui_tree }`（树形结构，包含控件 `name`、`control_type`、`rect`、`depth`、`is_offscreen`、`clickable`、`children` 等）

- POST `/close_app`
  - 入参：`{ "pid": 1234 }`
  - 返回：`{ status, pid, message }`（内部依次尝试 `WindowControl.Close()`、`WM_CLOSE`、`taskkill/psutil`）

- POST `/close_apps`
  - 入参：`{ "pids": [1234, 5678] }`
  - 返回：`{ results: [ { pid, status, message }, ... ] }`

- POST `/get_processes_by_exe`
  - 入参：`{ "path": "C:\\Path\\To\\YourApp.exe" }`
  - 返回：匹配该 exe 的所有进程列表（含 `pid`、`name`、`exe`、`create_time`）

- POST `/get_ui`
  - 入参：`{ "pid": 1234 }`
  - 返回：简单版 UI 列表（目标窗口的直接子节点，调试用）

- POST `/click`
  - 入参：`{ "x": 100, "y": 200 }`
  - 返回：`{ status: "clicked", x, y }`

跨域：已全量开启 CORS（`allow_origins=["*"]`）。如在生产使用，请按需收紧。

---

### 数据输出目录结构

运行主控脚本后，数据会生成在仓库根目录的 `data/<app_name>/` 下（两类来源）：

- 来自 `server/click.py`：
  - `YYYYmmdd_HHMMSS_screenshot.png`
  - `YYYYmmdd_HHMMSS_layout.json`
  - `YYYYmmdd_HHMMSS_screenshot_overlay.png`（在截图上绘制 UI 框，仅用于质检，不作为训练输入）

- 来自 `server/controller.py` 的 `AutoClicker`：
  - `initial_click_0_<ts>_screenshot.png`
  - `initial_click_0_<ts>_layout.json`
  - `after_click_<i>_<ts>_screenshot.png`
  - `after_click_<i>_<ts>_layout.json`
  - 对应的 `_overlay.png` 文件

> 说明：overlay 仅用于可视化/质检，请勿作为训练输入。

### UI 树与元素字段（用于生成标注）

服务端返回的 UI 树是一个递归结构，核心字段如下（均保存于 `*_layout.json`）：

- `app_name`：应用名
- `page_tag`：页面层次标记（便于区分上下文）
- `name`：控件显示名称/文本（若有）
- `control_type`：控件类型（如 `ButtonControl`、`TextControl`、`MenuItemControl` 等）
- `automation_id`：Automation 唯一标识（若有）
- `is_enabled`：是否可用
- `is_offscreen`：是否在屏幕外（不可见）
- `depth`：树深度
- `rect`：控件矩形，包含 `left/top/right/bottom`
- `clickable`：由底层自动化框架给出的可点击信息（如果可得）
- `children`：子节点数组

建议将 `*_layout.json` 扁平化为元素列表，用于训练样本的标注（常用筛选条件）：

- 仅保留 `is_offscreen == False` 的可见元素
- 仅保留 `rect` 面积大于 0 的元素
- 仅保留候选交互类型（例如：`ButtonControl`、`CheckBoxControl`、`ComboBoxControl`、`MenuItemControl`、`ListItemControl`、`TreeItemControl`、`HyperlinkControl` 等）

可参考 `server/controller.py` 的 `get_clickable_elements` 逻辑（示例实现）。

### 训练样本定义（建议格式）

为便于与常见目标检测/检测+描述任务兼容，推荐将每张截图配套导出一个标注文件（例如 `COCO` 风格或简化 `YOLO` 风格）。也可以采用项目内原生 JSON 的简化版，以元素为单位记录：

```json
{
  "image": "YYYYmmdd_HHMMSS_screenshot.png",
  "width": 1920,
  "height": 1080,
  "elements": [
    {
      "bbox": [left, top, width, height],
      "category": "ButtonControl",
      "name": "确定",
      "automation_id": "okButton",
      "depth": 3,
      "parent_path": ["Window", "Pane", "Dialog"],
      "clickable": true
    }
  ]
}
```

字段解释：

- `bbox`：从 `rect` 转换为 `[x, y, w, h]`
- `category`：来自 `control_type`，用于类别监督
- `name`/`automation_id`/`parent_path`：提供语义功能与上下文（可用于多任务训练，如“功能识别”/“描述生成”）

### 数据采集建议流程

1) 梳理应用清单与入口路径（见 `server/click.py` 和 `server/controller.py` 末尾的 `app_infos` 示例）
2) 对每个应用设定 `wait_time`，确保首屏元素稳定
3) 运行主控脚本：
   - 基础采集：`python server/click.py`
   - 批量采集：`python server/controller.py`（可扩展点击遍历逻辑，逐状态采集更多页面）
4) 采集后执行数据清洗：
   - 去重：对 `*_screenshot.png` 计算感知哈希，保留唯一样本
   - 过滤：剔除元素为空或全部越界的样本
   - 一致性：保证 `screenshot` 与 `layout.json` 一一对应
5) 导出训练标注：
   - 将 UI 树扁平化，生成检测标注（`bbox + category + name`）
   - 可选导出关系/层级/context（`parent_path`、`depth` 等）

### 数据集拆分与规模建议

- 拆分：按应用与时间戳分层随机 `train/val/test = 8/1/1`，避免同一窗口的相邻帧泄漏
- 规模：优先覆盖广谱应用类型（UWP/Win32/Electron/Qt/Java 等），每类应用建议 ≥1k 张，逐步扩张
- 多样性：改变窗口尺寸、主题、语言、账号态、数据内容，提升泛化能力

### 质量控制与评测

- 离线质检：随机抽样查看 `*_overlay.png` 与 `*_layout.json` 是否对齐；覆盖率检查（每张至少若干可交互元素）
- 训练评测（建议指标）：
  - 定位：mAP@IoU（标准检测指标）
  - 语义：元素类别/名称 Top-k 准确率；可选进阶为文本描述 BLEU/CIDEr
  - 端到端（后续阶段）：操作成功率、任务完成率

### 常见问题（与数据相关）

- 某些应用无 UI 树或元素为空：
  - 提升权限（管理员运行）；适当延长 `wait_time`；
  - 不同技术栈（如 OpenGL 游戏）对 UIA 的支持差，建议先集中在办公/工具/媒体类应用。
- 边框错位（如在爱奇艺等）：
  - 为后处理增加边界修正或过滤异常矩形；
  - 收集“错位样本”单独标记，便于后续学习鲁棒映射或训练矫正子模型。

---

## 典型用法示例（主控端最小可用片段）

```python
import requests, time

BASE = "http://127.0.0.1:5000"

# 1) 启动或复用应用
r = requests.post(f"{BASE}/open_app", json={"path": r"C:\\Windows\\System32\\notepad.exe"}).json()
pid = r["pid"]

# 2) 截图
ss = requests.post(f"{BASE}/screenshot").json()
img = requests.get(ss["url"]).content
open("notepad.png", "wb").write(img)

# 3) 拉取 UI 树（注意传入 pids 列表）
ui = requests.post(f"{BASE}/get_ui_tree", json={
    "name": "notepad", "path": r"C:\\Windows\\System32\\notepad.exe", "pids": [pid]
}).json()

# 4) 关闭应用
requests.post(f"{BASE}/close_app", json={"pid": pid})
```

---

## 设计与实现要点

- 窗口定位：
  - 首选前台窗口与 PID 精确匹配；
  - 遍历顶层窗口筛选可见者；
  - 回退到名称关键字映射（`KEYWORD_MAP`）以提高鲁棒性。
- 优雅退出：
  - 依次尝试 `WindowControl.Close()`、发送 `WM_CLOSE`、`taskkill /T /F`；
  - 对失败场景采用 `psutil` 强制结束进程树。
- 截图与共享：
  - 默认目录 `D:\screenshots`；脚本方式可用 `--shared-dir` 自定义；
  - 通过 HTTP 静态路径下载。
- 可视化：
  - 控制端将 UI 树遍历绘制到截图上（`server/click.py` 与 `server/controller.py` 皆支持）。

---

## 故障排查（FAQ）

- 422 验证失败（`/get_ui_tree`）：
  - 请确认请求体包含 `pids: [ ... ]`（列表），而不是单个 `pid` 字段。
  - 如使用 `server/click.py` 的早期版本，请将入参从 `pid` 改为 `pids`（列表）。

- 截图失败或 URL 404：
  - 确认 `D:\screenshots` 已存在（或以脚本模式传入 `--shared-dir` 并确保目录存在且可写）。

- 无法操控某些窗口/控件：
  - 以管理员权限运行；
  - UWP/Electron/游戏等应用可能对 UI 自动化支持不一致，必要时延长 `wait_time`；
  - 可扩展 `KEYWORD_MAP` 或在服务端增加特定控件类型到 `enabled_types`。

- 端口占用（5000）：
  - 修改 `client/start_server.bat` 中的 `--port`，或以脚本运行时调整 `uvicorn.run` 的端口。

---

## 规划与改进

参见 `todolist.md`：

- 结束应用偶发需手动退出
- 在爱奇艺等应用中标注不对齐
- 细化/拓展功能
- 启动程序时自动写入路径字典

欢迎提交 Issue/PR 共同完善。

---

## 许可与致谢

- 许可：当前仓库未显式声明许可证，如需开源复用请先与作者沟通
- 第三方依赖：FastAPI、Uvicorn、Pillow、pywinauto、uiautomation、psutil、requests 等

---

## 致开发者的小贴士

- 若你主要操作为两步：「启动客户端服务」+「运行 `server/click.py`」即可获得截图、UI 树与带框标注；
- 如需更复杂的流程（批量点击、数据集采集），参考 `server/controller.py` 的 `AutoClicker` 类实现；
- 生产使用请收紧 CORS、校验来源并限制可访问的可执行文件集合。
