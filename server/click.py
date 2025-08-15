import random
import time
import json
from pathlib import Path
import requests
import uiautomation as uiauto
from PIL import ImageGrab
import psutil
import os

class AutoClicker:
    def __init__(self, vm_ip="127.0.0.1", app_config=None):
        self.vm_ip = vm_ip
        self.app_config = app_config
        self.pid = None
        self.data_dir = None
        self.related_pids = set()
        self.app_exe_path = None
        self.enabled_types = [
            'ButtonControl', 'CheckBoxControl', 'ComboBoxControl', 'ScrollBarControl',
            'RadioButtonControl', 'HyperlinkControl', 'MenuItemControl', 'PaneControl',
            'TextControl', 'JavaControl', 'SwingControl', 'UwpButton', 'UwpText', 'TreeItemControl'
        ]

    def set_app(self, app_config):
        self.app_config = app_config

    def _post(self, route, payload=None):
        return requests.post(f"http://{self.vm_ip}:5000/{route}", json=payload or {})

    def _get_processes_by_exe(self, exe_path):
        exe_name = os.path.basename(exe_path).lower()
        pids = set()
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                if proc.info['name'] and proc.info['name'].lower() == exe_name:
                    pids.add(proc.info['pid'])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return pids

    def _update_related_pids(self):
        if self.app_exe_path:
            pids = self._get_processes_by_exe(self.app_exe_path)
            self.related_pids.update(pids)

    def _wait_for_process_and_ui(self, max_wait_time=10):
        """Wait for the process to start and UI to be available."""
        start_time = time.time()
        
        while time.time() - start_time < max_wait_time:
            self._update_related_pids()
            
            if self.related_pids:
                print(f"Found processes: {self.related_pids}")
                time.sleep(1)  # Wait for UI to load
                
                ui_tree = self.fetch_ui_tree()
                if ui_tree:
                    print("UI tree successfully retrieved")
                    return True
                else:
                    print("UI tree not available yet, continuing to wait...")
            
            time.sleep(0.5)
        
        return False

    def open_app(self):
        self.app_exe_path = self.app_config["exe_path"]
        before = self._get_processes_by_exe(self.app_exe_path)

        r = self._post("open_app", {"path": self.app_exe_path})
        data = r.json()
        if data.get('status') not in ('launched', 'already running'):
            print("Launch failed:", data)
            return None

        self.pid = data['pid']
        self.related_pids = {self.pid}
        time.sleep(2)
        # 收集所有相关进程
        self.related_pids |= self._get_processes_by_exe(self.app_exe_path) - before
        print(f"Tracking PIDs: {self.related_pids}")
        return data

    def close_app(self):
        if not self.related_pids and self.pid:
            self.related_pids = {self.pid}

        exe_name = os.path.basename(self.app_exe_path) if self.app_exe_path else None
        for pid in list(self.related_pids):
            payload = {"pid": pid, **({"exe_name": exe_name} if exe_name else {})}
            r = self._post("close_app", payload)
            print(f"close_app→ PID {pid}: {r.json()}")

        time.sleep(2)
        # 强杀残留进程
        rem = self._get_processes_by_exe(self.app_exe_path)
        if rem:
            print("Force killing remaining:", rem)
            for pid in rem:
                try:
                    psutil.Process(pid).kill()
                except Exception:
                    pass

        self.related_pids.clear()
        self.pid = None

    def capture_screenshot(self):
        """Capture a screenshot of the current screen."""
        try:
            response = self._post("screenshot")
            if response.status_code == 200:
                return response.json()
            else:
                print(f"Screenshot failed: {response.status_code}")
                return None
        except Exception as e:
            print(f"Error capturing screenshot: {e}")
            return None

    def fetch_ui_tree(self):
        """Fetch the UI tree of the application."""
        try:
            if not self.related_pids:
                self._update_related_pids()
                
            if not self.related_pids:
                print("No related PIDs found for UI tree fetching")
                return None
                
            r = self._post("get_ui_tree", {
                "name": self.app_config["app_name"],
                "path": self.app_exe_path,
                "pids": list(self.related_pids)
            })
            
            if r.status_code != 200:
                print(f"UI tree request failed: {r.status_code}")
                return None
                
            response_data = r.json()
            if response_data.get('status') == 'ok':
                return response_data.get('ui_tree')
            else:
                print(f"UI tree fetch failed: {response_data.get('error', 'Unknown error')}")
                return None
                
        except Exception as e:
            print(f"Error fetching UI tree: {e}")
            return None

    def get_clickable_elements(self, ui_tree):
        """Extract clickable elements from the UI tree, ignoring empty rects."""
        clickable_types = [
            'ButtonControl', 'CheckBoxControl', 'ComboBoxControl', 'ScrollBarControl',
            'RadioButtonControl', 'HyperlinkControl','ListItemControl','MenuItemControl','TreeItemControl'
        ]
        elements = []

        def traverse(node):
            if not node or not node.get('rect'):
                return
            ctype = node['control_type']
            visible = not node.get('is_offscreen', False)
            rect = node['rect']
            width  = rect['right']  - rect['left']
            height = rect['bottom'] - rect['top']

            # only keep if it’s a real, non‑zero‑sized control
            if (ctype in clickable_types
                    and visible
                    and width  > 0
                    and height > 0):
                elements.append(node)

            for child in node.get('children', []):
                traverse(child)

        traverse(ui_tree)
        return elements


    def click_element(self, element):
        """Simulate a click on the given element."""
        rect = element['rect']
        x = (rect['left'] + rect['right']) // 2
        y = (rect['top'] + rect['bottom']) // 2
        
        pids_before_click = self._get_processes_by_exe(self.app_exe_path) if self.app_exe_path else set()
        
        try:
            uiauto.Click(x, y)
            print(f"Clicked at ({x}, {y})")
            
            time.sleep(1)
            
            if self.app_exe_path:
                pids_after_click = self._get_processes_by_exe(self.app_exe_path)
                new_pids = pids_after_click - pids_before_click
                if new_pids:
                    print(f"New processes detected after click: {new_pids}")
                    self.related_pids.update(new_pids)
            
            return True
        except Exception as e:
            print(f"Click failed: {e}")
            return False

    def save_data(self, ui_tree, ss_info, state, click_num):
        """Save the UI tree and screenshot for a specific state and click number."""
        ts = time.strftime("%Y%m%d_%H%M%S")
        ss_path = self.data_dir / f"{state}_click_{click_num}_{ts}_screenshot.png"
        layout_path = self.data_dir / f"{state}_click_{click_num}_{ts}_layout.json"

        try:
            img_bytes = requests.get(ss_info['url']).content
            with open(ss_path, "wb") as f:
                f.write(img_bytes)
            print(f"Screenshot saved: {ss_path}")

            with open(layout_path, "w", encoding="utf-8") as f:
                json.dump(ui_tree, f, ensure_ascii=False, indent=2)
            print(f"Layout saved: {layout_path}")

            self.draw_ui_on_screenshot(ui_tree, ss_path)
        except Exception as e:
            print(f"Error saving data: {e}")

    def draw_ui_on_screenshot(self, ui_tree, png_path):
        """Draw UI elements on the screenshot and save as an overlay."""
        from PIL import Image, ImageDraw
        import os
        from pathlib import Path

        try:
            img = Image.open(png_path).convert("RGB")
            draw = ImageDraw.Draw(img)
            
            font = None
            COLORS = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0), (255, 0, 255), (0, 255, 255)]

            def _traverse(node):
                if not node or not node.get('rect'):
                    return
                bbox = node['rect']
                depth = node.get('depth', 0)
                ctype = node.get('control_type', 'Unknown')
                visible = not node.get('is_offscreen', False)

                if ctype in self.enabled_types and visible:
                    try:
                        left, top, right, bottom = bbox['left'], bbox['top'], bbox['right'], bbox['bottom']
                        if (left < 0 or top < 0 or right > img.width or bottom > img.height):
                            print(f"Skipping element with out-of-bounds coordinates: {bbox}")
                            return
                        
                        color = COLORS[depth % len(COLORS)]
                        draw.rectangle([left, top, right, bottom], outline=color)
                        draw.text((left, top), ctype, fill=color, font=font)
                    except Exception as e:
                        print(f"Draw error for element '{ctype}' at depth {depth}: {str(e)}")

                for child in node.get('children', []):
                    _traverse(child)

            _traverse(ui_tree)
            
            overlay_path = Path(png_path).with_stem(Path(png_path).stem + "_overlay")
            img.save(overlay_path)
            print(f"Overlay saved: {overlay_path}")
            
        except Exception as e:
            print(f"Error creating overlay: {e}")

    def run(self):
        """Execute the auto-clicking process, capturing initial state before the loop."""
        if not self.app_config:
            print("App config not set")
            return

        BASE_DIR = Path(__file__).resolve().parent.parent
        DATA_ROOT = BASE_DIR / "data" / self.app_config["app_name"]
        DATA_ROOT.mkdir(parents=True, exist_ok=True)
        self.data_dir = DATA_ROOT

        print("Capturing initial state...")
        if not self.open_app():
            print("Failed to open application")
            return
        
        time.sleep(self.app_config.get("wait_time", 3))   ###
        
        ss_info_initial = None
        ui_tree_initial = None
        
        for attempt in range(3):
            print(f"Attempt {attempt + 1} to capture initial state...")
            ss_info_initial = self.capture_screenshot()
            ui_tree_initial = self.fetch_ui_tree()
            
            if ss_info_initial and ui_tree_initial:
                print("Successfully captured initial state")
                break
            else:
                print(f"Failed attempt {attempt + 1}, waiting before retry...")
                time.sleep(5)
        
        if ss_info_initial and ui_tree_initial:
            self.save_data(ui_tree_initial, ss_info_initial, "initial", 0)
            clickable_elements = self.get_clickable_elements(ui_tree_initial)
            print(f"Found {len(clickable_elements)} clickable elements")
        else:
            print("Failed to capture initial state after multiple attempts")
            self.close_app()
            return      
        
        self.close_app()
        time.sleep(5)

        for i in range(1, 16):
            print(f"Starting click {i}...")
            
            if not self.open_app():
                print(f"Failed to open app for click {i}")
                continue
                
            time.sleep(self.app_config.get("wait_time", 3))
            
            if not clickable_elements:
                print(f"No clickable elements found for click {i}")
                self.close_app()
                continue
                
            # element_to_click = random.choice(clickable_elements)
            # print(f"Clicking element: {element_to_click.get('control_type', 'Unknown')}")
            
            # if self.click_element(element_to_click):
            #     time.sleep(5)
            #     ss_info_after = self.capture_screenshot()
            #     ui_tree_after = self.fetch_ui_tree()
                
            #     if ss_info_after and ui_tree_after:
            #         self.save_data(ui_tree_after, ss_info_after, "after", i)
            #         print(f"Successfully captured state after click {i}")
            #     else:
            #         print(f"Failed to capture state after click {i}")
            # else:
            #     print(f"Click action failed for click {i}")
            
            ###
            time.sleep(5)  ##
            ss_info_after = self.capture_screenshot()
            ui_tree_after = self.fetch_ui_tree()
                
            if ss_info_after and ui_tree_after:
                self.save_data(ui_tree_after, ss_info_after, "after", i)
                print(f"Successfully captured state after click {i}")
            else:
                print(f"Failed to capture state after click {i}")
            ###

            self.close_app()
            time.sleep(5)
        
        print("Auto-clicking process completed")

if __name__ == "__main__":
    # # win32
    # app_infos = {
    #     "app_name": "explorer",
    #     "exe_path": r"C:\Windows\explorer.exe",
    #     "wait_time": 5
    # }
    # app_infos = {
    #     "app_name": "taskmgr",
    #     "exe_path": r"C:\Windows\System32\Taskmgr.exe",
    #     "wait_time": 5
    # }
    # app_infos = {
    #     "app_name": "systemsettings",
    #     "exe_path": r"C:\Windows\ImmersiveControlPanel\SystemSettings.exe",
    #     "wait_time": 5
    # }
    # app_infos = {
    #     "app_name": "control",
    #     "exe_path": r"C:\Windows\System32\control.exe",
    #     "wait_time": 5
    # }
    # app_infos = {
    #     "app_name": "notepad",
    #     "exe_path": r"C:\Windows\System32\notepad.exe",
    #     "wait_time": 5
    # }
    # app_infos = {
    #     "app_name": "mspaint",
    #     "exe_path": r"C:\Program Files\WindowsApps\Microsoft.Paint_11.2506.71.0_x64__8wekyb3d8bbwe\PaintApp\mspaint.exe",
    #     "wait_time": 5
    # }
    # app_infos = {
    #     "app_name": "calc",
    #     "exe_path": r"C:\Windows\System32\calc.exe",
    #     "wait_time": 5
    # }
    # app_infos = {
    #     "app_name": "snippingtool",
    #     "exe_path": r"C:\Program Files\WindowsApps\Microsoft.ScreenSketch_11.2505.21.0_x64__8wekyb3d8bbwe\SnippingTool\SnippingTool.exe",
    #     "wait_time": 5
    # }
    # app_infos = {
    #     "app_name": "wmplayer",
    #     "exe_path": r"C:\Program Files (x86)\Windows Media Player\wmplayer.exe",
    #     "wait_time": 5
    # }
    # app_infos = {
    #     "app_name": "outlook",
    #     "exe_path": r"C:\Program Files\WindowsApps\Microsoft.OutlookForWindows_1.2025.617.100_x64__8wekyb3d8bbwe\olk.exe",
    #     "wait_time": 5
    # }
    # app_infos = {
    #     "app_name": "remotedesktop",
    #     "exe_path": r"C:\Windows\System32\mstsc.exe",
    #     "wait_time": 5
    # }
    # app_infos = {
    #     "app_name": "chrome",
    #     "exe_path": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    #     "wait_time": 5
    # }
    # app_infos = {
    #     "app_name": "word",
    #     "exe_path": r"C:\Program Files\Microsoft Office\Office16\WINWORD.EXE",
    #     "wait_time": 5
    # }
    # app_infos = {
    #     "app_name": "excel",
    #     "exe_path": r"C:\Program Files\Microsoft Office\Office16\EXCEL.EXE",
    #     "wait_time": 5
    # }
    # app_infos = {
    #     "app_name": "ppt",
    #     "exe_path": r"C:\Program Files\Microsoft Office\Office16\POWERPNT.EXE",
    #     "wait_time": 5
    # } 
    # # electron
    # app_infos = {
    #     "app_name": "code",
    #     "exe_path": r"D:\Program Files\Microsoft VS Code\Code.exe",
    #     "wait_time": 5
    # }
    # app_infos = {
    #     "app_name": "iqiyi",
    #     "exe_path": r"D:\Program Files\爱奇艺\IQIYI Video\QyClient.exe",
    #     "wait_time": 5
    # }
    # app_infos = {
    #     "app_name": "wechat",
    #     "exe_path": r"C:\Program Files\WeChat\WeChat.exe",
    #     "wait_time": 5
    # }
    # app_infos = {
    #     "app_name": "tencentdocs",
    #     "exe_path": r,
    #     "wait_time": 5
    # }
    # app_infos = {
    #     "app_name": "wechatwork",
    #     "exe_path": r"C:\Program Files\Tencent\WeCom\WeCom.exe",
    #     "wait_time": 5
    # }
    # app_infos = {
    #     "app_name": "dingtalk",
    #     "exe_path": r"D:\app\DingDing\DingtalkLauncher.exe",
    #     "wait_time": 5
    # }
    # app_infos = {
    #     "app_name": "feishu",
    #     "exe_path": r"D:\app\Feishu\Feishu.exe",
    #     "wait_time": 5
    # }
    # app_infos = {
    #     "app_name": "wemeet",
    #     "exe_path": r"D:\Program Files (AC)\腾讯会议\WeMeet\wemeetapp.exe",
    #     "wait_time": 5
    # }    
    # app_infos = {
    #     "app_name": "baidunetdisk",
    #     "exe_path": r"D:\app\BaiduNetdisk\BaiduNetdisk.exe",
    #     "wait_time": 5
    # }
    # app_infos = {
    #     "app_name": "aDrive",
    #     "exe_path": r"D:\app\aDrive\aDrive.exe",
    #     "wait_time": 5
    # }
    # app_infos = {
    #     "app_name": "skype",
    #     "exe_path": r"C:\Program Files (x86)\Microsoft\Skype\Skype.exe",
    #     "wait_time": 5
    # }
    # app_infos = {
    #     "app_name": "bilibili",
    #     "exe_path": r"D:\Program Files\bilibili\哔哩哔哩.exe",
    #     "wait_time": 5
    # }
    # app_infos = {
    #     "app_name": "iqiyi",
    #     "exe_path": r"D:\Program Files\爱奇艺\IQIYI Video\LStyle\13.1.5.9002\QyClient.exe",
    #     "wait_time": 5
    # }
    # app_infos = {
    #     "app_name": "qqlive",
    #     "exe_path": r"D:\app\QQLive\QQLive.exe",
    #     "wait_time": 5
    # }
    # app_infos = {
    #     "app_name": "youku",
    #     "exe_path": r"D:\app\youku\9.2.65.1001\YOUKU.exe",
    #     "wait_time": 5
    # }
    # # qt
    # app_infos = {
    #     "app_name": "qqmusic",
    #     "exe_path": r"D:\Program Files\QQMusic\QQMusic.exe",
    #     "wait_time": 5
    # }
    # app_infos = {
    #     "app_name": "potplayer",
    #     "exe_path": r"D:\app\PotPlayer\PotPlayerMini64.exe",
    #     "wait_time": 5
    # }
    # app_infos = {
    #     "app_name": "stormplayer",
    #     "exe_path": r"D:\app\bfyy\StormPlayer.exe",
    #     "wait_time": 5
    # }
    # app_infos = {
    #     "app_name": "vlc",
    #     "exe_path": r"D:\app\VLC\vlc.exe",
    #     "wait_time": 5
    # }

    # # java
    # app_infos = {
    #     "app_name": "xmind",
    #     "exe_path": r"C:\Users\lenovo\AppData\Local\Programs\Xmind\Xmind.exe",
    #     "wait_time": 5
    # }
    # # # win32
    # app_infos = {
    #     "app_name": "wps",
    #     "exe_path": r"D:\app\WPS Office\ksolaunch.exe",
    #     "wait_time": 5
    # }
    # app_infos = {
    #     "app_name": "acrobat",
    #     "exe_path": r"C:\Program Files\Adobe\Acrobat DC\Acrobat\Acrobat.exe",
    #     "wait_time": 5
    # }
    # electron
    # app_infos = {
    #     "app_name": "vscode",
    #     "exe_path": r"D:\Program Files (AC)\vscode\Microsoft VS Code\Code.exe",
    #     "wait_time": 5
    # }
    # app_infos = {
    #     "app_name": "sublime",
    #     "exe_path": r"D:\app\Sublime Text\sublime_text.exe",
    #     "wait_time": 5
    # }
    # app_infos = {
    #     "app_name": "evernote",
    #     "exe_path": r"C:\Users\lenovo\AppData\Local\Programs\Evernote\Evernote.exe",
    #     "wait_time": 5
    # }
    # app_infos = {
    #     "app_name": "onenote",
    #     "exe_path": r"C:\Program Files\Microsoft Office\Office16\ONENOTE.EXE",
    #     "wait_time": 5
    # }
    # # win32
    # app_infos = {
    #     "app_name": "qq",
    #     "exe_path": r"C:\Program Files\Tencent\QQ\Bin\QQ.exe",
    #     "wait_time": 5
    # }
    # # electron
    # app_infos = {
    #     "app_name": "netease_mail",
    #     "exe_path": r"C:\Program Files (x86)\Netease\MailMaster\MailMaster.exe",
    #     "wait_time": 5
    # }

    ##7.20 beginning
    # app_infos = {
    #     "app_name": "thunderbird",
    #     "exe_path": r"D:\app\thunderbird\thunderbird.exe",
    #     "wait_time": 5
    # }
    # app_infos = {
    #     "app_name": "mailmaster",
    #     "exe_path": r"D:\app\wangyi\MailMaster\Application\mailmaster.exe",
    #     "wait_time": 5
    # }
    # app_infos = {
    #     "app_name": "qq",
    #     "exe_path": r"D:\Program Files\QQ\QQ.exe",
    #     "wait_time": 5
    # }
    # app_infos = {
    #     "app_name": "wechat",
    #     "exe_path": r"D:\Program Files\微信\Weixin\Weixin.exe",
    #     "wait_time": 5
    # }
#####
    # # win32
    # app_infos = {
    #     "app_name": "formatfactory",
    #     "exe_path": r"C:\Program Files\FormatFactory\FormatFactory.exe",
    #     "wait_time": 5
    # }
    # app_infos = {
    #     "app_name": "itunes",
    #     "exe_path": r"C:\Program Files\iTunes\iTunes.exe",
    #     "wait_time": 5
    # }

    # qt
    # app_infos = {
    #     "app_name": "meituxiuxiu",
    #     "exe_path": r"D:\app\MeituApp\XiuXiu\XiuXiu.exe",
    #     "wait_time": 5
    # }

    # app_infos = {
    #     "app_name": "mgtv",
    #     "exe_path": r"D:\app\mgtv\MGTVPCC\芒果TV.exe",
    #     "wait_time": 5
    # }

    # # electron
    # app_infos = {
    #     "app_name": "gimp",
    #     "exe_path": r"D:\app\GIMP 3\bin\gimp-3.exe",
    #     "wait_time": 5
    # }
    # app_infos = {
    #     "app_name": "audacity",
    #     "exe_path": r"D:\app\Audacity\Audacity.exe",
    #     "wait_time": 5
    # }
    # app_infos = {
    #     "app_name": "spotify",
    #     "exe_path": r"C:\Users\lenovo\AppData\Roaming\Spotify\Spotify.exe",
    #     "wait_time": 5
    # }
    # app_infos = {
    #     "app_name": "kugou",
    #     "exe_path": r"D:\app\KGMusic\KuGou.exe",
    #     "wait_time": 5
    # }
    # app_infos = {
    #     "app_name": "cloudmusic",
    #     "exe_path": r"D:\app\CloudMusic\cloudmusic.exe",
    #     "wait_time": 5
    # }
    # app_infos = {
    #     "app_name": "qqmusic",
    #     "exe_path": r"D:\Program Files\QQMusic\QQMusic.exe",
    #     "wait_time": 5
    # }
    # app_infos = {
    #     "app_name": "spotify",
    #     "exe_path": r"C:\Users\lenovo\AppData\Roaming\Spotify\Spotify.exe",
    #     "wait_time": 5
    # }

    app_infos = {
        "app_name": "winrar",
        "exe_path": r"C:\Program Files\WinRAR\WinRAR.exe",
        "wait_time": 5
    }

    # # 浏览器
    # app_infos = {
    #     "app_name": "chrome",
    #     "exe_path": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    #     "wait_time": 5
    # }
    # app_infos = {
    #     "app_name": "firefox",
    #     "exe_path": r"C:\Program Files\Mozilla Firefox\firefox.exe",
    #     "wait_time": 5
    # }
    # app_infos = {
    #     "app_name": "sogou_browser",
    #     "exe_path": r"C:\Program Files\SogouExplorer\SogouExplorer.exe",
    #     "wait_time": 5
    # }
    # # win32
    # app_infos = {
    #     "app_name": "git",
    #     "exe_path": r"C:\Program Files\Git\git-bash.exe",
    #     "wait_time": 5
    # }
    # app_infos = {
    #     "app_name": "github_desktop",
    #     "exe_path": r"C:\Users\<user>\AppData\Local\GitHubDesktop\GitHubDesktop.exe",
    #     "wait_time": 5
    # }
    # app_infos = {
    #     "app_name": "docker",
    #     "exe_path": r"C:\Program Files\Docker\Docker\Docker Desktop.exe",
    #     "wait_time": 5
    # }
    # app_infos = {
    #     "app_name": "postman",
    #     "exe_path": r"C:\Users\<user>\AppData\Local\Postman\Postman.exe",
    #     "wait_time": 5
    # }
    # app_infos = {
    #     "app_name": "fiddler",
    #     "exe_path": r"C:\Program Files (x86)\Fiddler2\Fiddler.exe",
    #     "wait_time": 5
    # }
    # app_infos = {
    #     "app_name": "xshell",
    #     "exe_path": r"C:\Program Files\NetSarang\Xshell 7\Xshell.exe",
    #     "wait_time": 5
    # }
    # app_infos = {
    #     "app_name": "vmware",
    #     "exe_path": r"D:\Program Files (AC)\VMware\vmware.exe",
    #     "wait_time": 5
    # }
    # app_infos = {
    #     "app_name": "virtualbox",
    #     "exe_path": r"C:\Program Files\Oracle\VirtualBox\VirtualBox.exe",
    #     "wait_time": 5
    # }
    app_infos = {
        "app_name": "clash",
        "exe_path": r"D:\Program Files (AC)\Clash for Windows\Clash for Windows.exe",
        "wait_time": 5
    }
    # app_infos = {
    #     "app_name": "sunlogin",
    #     "exe_path": r"C:\Program Files (x86)\Oray\SunloginClient\SunloginClient.exe",
    #     "wait_time": 5
    # }
    # app_infos = {
    #     "app_name": "teamviewer",
    #     "exe_path": r"C:\Program Files\TeamViewer\TeamViewer.exe",
    #     "wait_time": 5
    # }
    # app_infos = {
    #     "app_name": "anydesk",
    #     "exe_path": r"C:\Program Files (x86)\AnyDesk\AnyDesk.exe",
    #     "wait_time": 5
    # }
    # app_infos = {
    #     "app_name": "everything",
    #     "exe_path": r"C:\Program Files\Everything\Everything.exe",
    #     "wait_time": 5
    # }
    # app_infos = {
    #     "app_name": "listary",
    #     "exe_path": r"C:\Program Files\Listary\Listary.exe",
    #     "wait_time": 5
    # }
    # app_infos = {
    #     "app_name": "pdf_converter",
    #     "exe_path": r"C:\Program Files (x86)\Apowersoft\PDF Converter Studio\ApowerPDF.exe",
    #     "wait_time": 5
    # }

    auto_clicker = AutoClicker(app_config=app_infos)
    auto_clicker.run()