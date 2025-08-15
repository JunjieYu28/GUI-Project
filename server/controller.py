import requests, json, time, logging
from pathlib import Path
from PIL import Image, ImageDraw
from utils import COLORS

# ---------------- logging ----------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------- 常量 ----------------
B_COLORS = {idx: c for idx, c in enumerate(COLORS.keys())}
ENABLED_TYPES = [
    'ButtonControl', 'CheckBoxControl', 'ComboBoxControl', 'ScrollBarControl',
    'RadioButtonControl', 'HyperlinkControl', 'MenuItemControl', 'PaneControl',
    'TextControl', 'JavaControl', 'SwingControl', 'UwpButton', 'UwpText'
]
CLICK_TYPES = [
    'ButtonControl', 'CheckBoxControl', 'ComboBoxControl', 'ScrollBarControl', 
    'RadioButtonControl', 'HyperlinkControl'
]

# ---------------- 绘制辅助 ----------------
def draw_ui_on_screenshot(ui_tree, png_path):
    """在截屏上绘制 UI 边框，保存 *_overlay.png 并返回所有元素信息"""
    img = Image.open(png_path)
    draw = ImageDraw.Draw(img)
    all_elements = []

    def _traverse(node):
        if not node or not node.get('rect'):
            return
        bbox = node['rect']
        depth = min(node['depth'], len(B_COLORS) - 1)
        ctype = node['control_type']
        visible = not node.get('is_offscreen', False)

        if ctype in ENABLED_TYPES and visible:
            try:
                draw.rectangle([bbox['left'], bbox['top'],
                                bbox['right'], bbox['bottom']],
                               outline=B_COLORS[depth])
                draw.text((bbox['left'], bbox['top']), ctype,
                          fill=B_COLORS[depth])
                all_elements.append({
                    "name": node['name'],
                    "type": ctype,
                    "bbox": bbox,
                    "depth": node['depth'],
                    "clickable": node['clickable'],
                })
            except Exception as e:
                logger.error(f"Draw error: {e}")

        for child in node.get('children', []):
            _traverse(child)

    _traverse(ui_tree)
    overlay_path = Path(png_path).with_stem(Path(png_path).stem + "_overlay")
    img.save(overlay_path)
    logger.info(f"Overlay saved: {overlay_path}")
    return all_elements

# ---------------- 主类 ----------------
class UI_Extractor:
    def __init__(self, vm_ip="127.0.0.1"):
        self.vm_ip = vm_ip

    # ---------- 配置 ----------
    def set_app(self, cfg):
        self.app_name = cfg.get("app_name", "app")
        self.exe_path = cfg.get("exe_path")
        self.wait_time = cfg.get("wait_time", 3)

    # ---------- 基础 RPC ----------
    def _post(self, route, payload=None):
        return requests.post(f"http://{self.vm_ip}:5000/{route}", json=payload or {})

    def open_app(self):  # 启动
        r = self._post("open_app", {"path": self.exe_path}).json()
        if r.get('status') == 'error':
            logger.error(f"Launch failed: {r.get('error')}")
            return None
        logger.info(f"Launched {r['path']}  PID={r['pid']}")
        return r

    def close_app(self, pid):  # 结束
        self._post("close_app", {"pid": pid})

    def capture_screenshot(self):  # 远程抓图
        return self._post("screenshot").json()

    def fetch_ui_tree(self, app_meta):
        r = self._post("get_ui_tree", app_meta).json()
        return r.get('ui_tree') if r.get('status') == 'ok' else None

    # ---------- 流程 ----------
    def init_task(self):
        meta = self.open_app()
        if not meta:
            return False
        self.pid = meta['pid']
        time.sleep(self.wait_time)
        return True

    def run_task(self):
        # 1) 创建本地存储目录
        BASE_DIR = Path(__file__).resolve().parent.parent
        DATA_ROOT = BASE_DIR / "data"

        ts = time.strftime("%Y%m%d_%H%M%S")
        data_dir = DATA_ROOT / self.app_name
        data_dir.mkdir(parents=True, exist_ok=True)

        # 2) 抓图并下载
        ss_info = self.capture_screenshot()
        if not ss_info or ss_info.get('status') != 'ok':
            logger.error("Screenshot failed")
            return
        img_bytes = requests.get(ss_info['url']).content
        ss_path = data_dir / f"{ts}_screenshot.png"
        with open(ss_path, "wb") as f:
            f.write(img_bytes)
        logger.info(f"Screenshot saved: {ss_path}")

        # 3) 获取 UI 树
        ui_tree = self.fetch_ui_tree({
            "name": self.app_name,
            "path": self.exe_path,
            "pid": self.pid
        })
        if not ui_tree:
            logger.error("UI tree fetch failed")
            return

        # 4) 保存 UI 树 JSON
        layout_path = data_dir / f"{ts}_layout.json"
        with open(layout_path, "w", encoding="utf-8") as f:
            json.dump(ui_tree, f, ensure_ascii=False, indent=2)
        logger.info(f"Layout saved: {layout_path}")

        # 5) 可选：绘制可视化
        draw_ui_on_screenshot(ui_tree, ss_path)

        logger.info(f"All data written under: {data_dir}")

    def end_task(self):
        if hasattr(self, 'pid'):
            self.close_app(self.pid)
            logger.info(f"Closed PID {self.pid}")

if __name__ == "__main__":
    # # win32
    # app_infos = {
    #     "app_name": "Notepad",
    #     "exe_path": r"C:\Windows\System32\notepad.exe",
    #     "wait_time": 5
    # }
    # # electron
    # app_infos = {
    #     "app_name": "code",
    #     "exe_path": r"D:\Program Files (AC)\vscode\Microsoft VS Code\Code.exe",
    #     "wait_time": 5
    # }
    # # uwp
    # app_infos = {
    #     "app_name": "calculator",
    #     "exe_path": r"C:\Windows\System32\calc.exe",
    #     "wait_time": 5
    # }
    # # qt
    app_infos = {
        "app_name": "qqmusic",
        "exe_path": r"D:\Program Files\QQMusic\QQMusic.exe",
        "wait_time": 5
    }
    ## 奇怪的点在于我在未开启qq音乐的情况下，程序打开QQ音乐，但不能够获取到qq音乐的ui信息；但我在打开QQ音乐的前提下，程序能够正常运行
    # # java
    # app_infos = {
    #     "app_name": "xmind",
    #     "exe_path": r"C:\Users\lenovo\AppData\Local\Programs\Xmind\Xmind.exe",
    #     "wait_time": 5
    # }
    # # electron
    # app_infos = {
    #     "app_name": "iqiyi",
    #     "exe_path": r"D:\Program Files\爱奇艺\IQIYI Video\LStyle\QyClient.exe",
    #     "wait_time": 5
    # }
    # # qt
    # app_infos = {
    #     "app_name": "wemeet",
    #     "exe_path": r"D:\Program Files (AC)\腾讯会议\WeMeet\wemeetapp.exe",
    #     "wait_time": 5
    # }
    # # qt
    # app_infos = {
    #     "app_name": "bilibili",
    #     "exe_path": r"D:\Program Files\bilibili\哔哩哔哩.exe",
    #     "wait_time": 5
    # }
    # qt
    # app_infos = {
    #     "app_name": "wmplayer",
    #     "exe_path": r"C:\Program Files (x86)\Windows Media Player\wmplayer.exe",
    #     "wait_time": 5
    # }
    # app_infos = {
    #     "app_name": "vmware",
    #     "exe_path": r"D:\Program Files (AC)\VMware\vmware.exe",
    #     "wait_time": 5
    # }
    # app_infos = {
    #     "app_name": "terminal",
    #     "exe_path": r"C:\Program Files\WindowsApps\Microsoft.WindowsTerminal_1.22.11141.0_x64__8wekyb3d8bbwe\WindowsTerminal.exe",
    #     "wait_time": 5
    # }
    # app_infos = {
    #     "app_name": "cs2",
    #     "exe_path": r"D:\Program Files\Steam\steamapps\common\Counter-Strike Global Offensive\game\bin\win64\cs2.exe",
    #     "wait_time": 5
    # }
    # app_infos = {
    #     "app_name": "ultimate_chicken_horse",
    #     "exe_path": r"D:\Program Files\Steam\steamapps\common\Ultimate Chicken Horse\UltimateChickenHorse.exe",
    #     "wait_time": 5
    # }
    # app_infos = {
    #     "app_name": "ultimate_chicken_horse",
    #     "exe_path": r"D:\Program Files\Steam\steam.exe",
    #     "wait_time": 5
    # }
    ui_agent = UI_Extractor(vm_ip="127.0.0.1")
    ui_agent.set_app(app_infos)
    if ui_agent.init_task():
        ui_agent.run_task()
        ui_agent.end_task()