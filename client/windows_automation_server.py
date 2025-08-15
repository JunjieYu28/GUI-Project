import os
import time
import datetime
import argparse
import uiautomation as uiauto
from uiautomation import WindowControl
from pywinauto.application import Application
from PIL import ImageGrab
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
import psutil
import subprocess
import win32gui, win32con, win32process

app = FastAPI()

# 支持跨域请求（可选）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 默认共享目录路径
SHARED_DIR = r"D:\\screenshots"

# ---------- Pydantic 请求模型 ----------

class PathModel(BaseModel):
    path: str

class CoordModel(BaseModel):
    x: int
    y: int

class PIDModel(BaseModel):
    pid: int

class PIDListModel(BaseModel):
    pids: list[int]

class AppTask(BaseModel):
    name: str
    path: str
    pids: list[int]  # Updated to accept a list of PIDs

# ---------- 内部方法 ----------
def extract_ui(ctrl, app_name='App', page_tag='Main', depth=0):
    try:
        rect = ctrl.BoundingRectangle
        control_type = ctrl.ControlTypeName or ""
        name = ctrl.Name or ""
        return {
            "app_name": app_name,
            "page_tag": f"{page_tag}_{depth}",
            "name": name,
            "control_type": control_type,
            "automation_id": ctrl.AutomationId,
            "is_enabled": ctrl.IsEnabled,
            "is_offscreen": ctrl.IsOffscreen,
            "depth": depth,
            "rect": {
                "left": rect.left,
                "top": rect.top,
                "right": rect.right,
                "bottom": rect.bottom
            },
            "clickable": ctrl.GetClickablePoint(),
            "focusable": ctrl.IsKeyboardFocusable,
            "children": [
                extract_ui(child, app_name=app_name, page_tag=f"{page_tag}_{depth}", depth=depth + 1)
                for child in ctrl.GetChildren()
            ]
        }
    except Exception as e:
        print(f"Error extracting UI for control {ctrl.Name}: {e}")
        return None

def _wait_for_window(name_keywords: list[str], timeout=10):
    """轮询顶层窗口，直到出现包含关键字的窗口"""
    import time, uiautomation as auto
    t0 = time.time()
    while time.time() - t0 < timeout:
        for win in auto.GetRootControl().GetChildren():
            try:
                title = (win.Name or "").lower()
                if any(k in title for k in name_keywords):
                    return win
            except Exception:
                pass
        time.sleep(0.3)
    return None

def terminate_process_tree(pid: int) -> bool:
    """psutil fallback to kill a process tree"""
    try:
        parent = psutil.Process(pid)
        for child in parent.children(recursive=True):
            child.kill()
        parent.kill()
        return True
    except Exception:
        return False
    
def post_wm_close(pid: int):
    """枚举所有顶层窗口，把 WM_CLOSE 发给属于 pid 的那个"""
    def _enum(hwnd, _):
        _, wpid = win32process.GetWindowThreadProcessId(hwnd)
        if wpid == pid and win32gui.IsWindowVisible(hwnd):
            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
    win32gui.EnumWindows(_enum, None)

def get_all_related_pids(pid_list):
    """获取所有相关进程ID，包括子进程"""
    all_pids = set()
    for pid in pid_list:
        try:
            proc = psutil.Process(pid)
            all_pids.add(pid)
            # 添加所有子进程
            for child in proc.children(recursive=True):
                all_pids.add(child.pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return all_pids

def find_window_by_pids(pids, app_name=""):
    """根据进程ID列表查找窗口"""
    root = uiauto.GetRootControl()
    
    print(f"Looking for windows with PIDs: {pids}")
    
    # 获取所有相关进程ID（包括子进程）
    all_pids = get_all_related_pids(pids)
    print(f"All related PIDs: {all_pids}")
    
    # 1. 首先尝试前台窗口
    try:
        foreground_win = uiauto.GetForegroundControl()
        if foreground_win and foreground_win.ProcessId in all_pids:
            print(f"Found foreground window: {foreground_win.Name} (PID: {foreground_win.ProcessId})")
            return foreground_win
    except Exception as e:
        print(f"Error getting foreground window: {e}")
    
    # 2. 遍历所有顶层窗口，查找匹配的PID
    windows_found = []
    for win in root.GetChildren():
        try:
            if win.ProcessId in all_pids:
                windows_found.append(win)
                print(f"Found window: '{win.Name}' (PID: {win.ProcessId})")
        except Exception as e:
            print(f"Error checking window: {e}")
            continue
    
    # 3. 如果找到了窗口，优先选择可见的窗口
    if windows_found:
        for win in windows_found:
            try:
                if win.IsWindowPatternAvailable() and not win.IsOffscreen:
                    print(f"Selected visible window: {win.Name}")
                    return win
            except Exception:
                continue
        
        # 如果没有可见窗口，返回第一个找到的
        print(f"No visible windows found, using first available: {windows_found[0].Name}")
        return windows_found[0]
    
    # 4. 如果按PID找不到，尝试按应用名称关键字查找
    if app_name:
        KEYWORD_MAP = {
            # Windows 自带应用
            'explorer': ['文件资源管理器', 'explorer', '此电脑','windows 资源管理器'],
            'taskmgr': ['任务管理器', 'task manager'],
            'control': ['控制面板', 'control panel'],
            'systemsettings': ['设置', 'windows settings','systemsettings'],
            'notepad': ['记事本', 'notepad', 'untitled'],
            'mspaint': ['画图', 'paint'],
            'calculator': ['计算器', 'calculator'],
            'outlook': ['邮件', 'mail', 'outlook mail','outlook','microsoft outlook'],
            'chrome': ['google chrome', 'google chrome浏览器','chrome浏览器','chrome'],
            'wmplayer': ['windows media player', 'wmplayer'],
            'snippingtool': ['截图工具', 'snipping tool'],
            'remotedesktop': ['远程桌面', 'remote desktop'],

            # 办公与生产力
            'word': ['word', 'word文档', 'microsoft word','微软word'],
            'excel': ['excel', 'excel文档', 'microsoft excel','微软excel'],
            'ppt': ['ppt', 'powerpoint', 'microsoft powerpoint','微软powerpoint'],
            'wps': ['wps', '金山办公','ksolaunch','wps office','wps办公'],
            'acrobat': ['acrobat reader', 'adobe reader', 'pdf阅读器'],
            'foxitpdf': ['foxit pdf', '福昕', 'foxit editor'],
            'notepad++': ['notepad++', '代码编辑器'],
            'vscode': ['visual studio code', 'code', 'vscode'],
            'sublime': ['sublime text', 'sublime'],
            'evernote': ['evernote', '印象笔记'],
            'onenote': ['onenote', '微软笔记'],
            'slack': ['slack', '团队沟通'],
            'zoom': ['zoom', '视频会议'],
            'teams': ['microsoft teams', 'teams'],
            'dingtalk': ['钉钉', 'dingtalk','dingtalklauncher'],
            'feishu': ['飞书', 'feishu'],
            'wemeet': ['腾讯会议', 'tencent meeting', 'wemeet'],
            'tencentdocs': ['腾讯文档', 'docs.qq.com'],
            'baidunetdisk': ['百度网盘', 'baidunetdisk','百度云'],
            'adrive': ['aDrive', '阿里云盘'],
            # 网络与通信
            'wechat': ['微信', 'wechat'],
            'qq': ['qq', '腾讯qq'],
            'weibo': ['微博', 'weibo'],
            'mailmaster': ['网易邮箱大师', 'mailmaster'],
            'thunderbird': ['thunderbird', '雷鸟'],
            # 多媒体与设计
            'vlc': ['vlc', 'vlc player'],
            'potplayer': ['potplayer'],
            'stormplayer': ['暴风影音', '暴风影音5', 'stormplayer'],
            'iqiyi': ['爱奇艺', 'iqiyi','qyclient'],
            'qqlive': ['腾讯视频', 'tencent video','qqlive','qq视频'],
            'youku': ['优酷', 'youku'],
            'bilibili': ['哔哩哔哩', 'bilibili', 'b站'],
            'mgtv': ['芒果TV', 'mgtv'],
            'photoshop': ['photoshop', 'ps'],
            'premiere': ['premiere', 'pr'],
            'lightroom': ['lightroom', 'lr'],
            'gimp': ['gimp', '开源图像编辑','gimp3'],
            'meituxiuxiu': ['美图秀秀', 'meitu','xiuxiu'],
            'formatfactory': ['格式工厂', 'format factory'],
            'audacity': ['audacity', '音频编辑'],
            'kugou': ['酷狗音乐', 'kugou'],
            'kwmusic': ['酷我音乐', 'kwmusic'],
            'cloudmusic': ['网易云音乐', 'netease music','cloudmusic'],
            'qqmusic': ['qq音乐', 'qqmusic'],
            'spotify': ['spotify'],
            'itunes': ['itunes'],
            '千千静听': ['千千静听'],

            # 安全与系统工具
            '360safe': ['360安全卫士', '360safe'],
            'qqmanager': ['腾讯电脑管家', 'qq电脑管家'],
            'huorong': ['火绒', '火绒安全'],
            'ludashi': ['鲁大师', 'ludashi'],
            'ccleaner': ['ccleaner', '系统清理'],
            '7zip': ['7-zip', '压缩工具'],
            'winrar': ['winrar'],
            'bandizip': ['bandizip'],
            'thunder': ['迅雷', 'thunder'],
            'idm': ['idm', 'internet download manager'],
            'qbittorrent': ['qbittorrent', 'bt下载'],
            'chrome': ['谷歌浏览器', 'chrome', 'google chrome'],
            'firefox': ['火狐浏览器', 'firefox', 'mozilla firefox'],
            'sogou_browser': ['搜狗浏览器', 'sogou'],

            # 开发与工具类
            'git': ['git', 'git bash'],
            'github_desktop': ['github desktop', 'github'],
            'docker': ['docker', 'docker desktop'],
            'postman': ['postman', 'api测试'],
            'fiddler': ['fiddler', '抓包工具'],
            'xshell': ['xshell', 'ssh工具'],
            'vmware': ['vmware', '虚拟机'],
            'virtualbox': ['virtualbox', '虚拟机'],
            'putty': ['putty'],
            'sunlogin': ['向日葵', 'sunlogin'],
            'teamviewer': ['teamviewer'],
            'anydesk': ['anydesk'],
            'everything': ['everything', '文件搜索'],
            'listary': ['listary', '快速启动'],
            'pdf_converter': ['pdf转换器', '迅捷pdf'],
            
            # java类
            'xmind': ['xmind'],
            'clash': ['clash']
        }
        keywords = KEYWORD_MAP.get(app_name.lower(), [app_name.lower()])
        print(f"Searching by keywords: {keywords}")
        
        for win in root.GetChildren():
            try:
                title = (win.Name or "").lower()
                if any(keyword.lower() in title for keyword in keywords):
                    print(f"Found window by keyword: {win.Name}")
                    return win
            except Exception:
                continue
    
    print("No matching window found")
    return None

# ---------- 接口定义 ----------

@app.post("/open_app")
def open_app(data: PathModel):
    exe_path = os.path.abspath(data.path)
    exe_name = os.path.basename(exe_path).lower()
    print(f"Opening app: {exe_path}")

    # 1. 如果已在运行，就直接返回主进程 PID 与窗口
    for proc in psutil.process_iter(['pid', 'exe', 'name']):
        try:
            if proc.info['exe'] and os.path.samefile(proc.info['exe'], exe_path):
                main = proc
                child_pids = [c.pid for c in main.children(recursive=True)]
                all_pids = [main.pid] + child_pids
                window = find_window_by_pids(all_pids, os.path.splitext(exe_name)[0])
                real_pid = window.ProcessId if window else main.pid
                title = window.Name if window else "Unknown"
                print(f"App already running - UI PID: {real_pid}, Window: {title}")
                return {
                    "status": "already running",
                    "path": exe_path,
                    "pid": real_pid,
                    "window_title": title
                }
        except Exception:
            continue

    # 2. 启动应用
    try:
        parent = subprocess.Popen([exe_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=False)
        print(f"Started stub process PID: {parent.pid}")
        time.sleep(2)

        # 收集 parent + 子进程 PIDs
        try:
            proc = psutil.Process(parent.pid)
            child_pids = [c.pid for c in proc.children(recursive=True)]
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            child_pids = []
        stub_pids = [parent.pid] + child_pids

        # 查找真正的 UI 窗口和进程
        window = find_window_by_pids(stub_pids, os.path.splitext(exe_name)[0])
        if window:
            real_pid = window.ProcessId
            title = window.Name
            print(f"App UI PID: {real_pid}, Window: {title}")
        else:
            # 回退到 stub PID
            real_pid = parent.pid
            title = "Unknown"
            print("Warning: 未找到 UI 窗口，使用 stub PID 进行后续操作")

        return {
            "status": "launched",
            "path": exe_path,
            "pid": real_pid,
            "window_title": title
        }

    except Exception as e:
        print(f"Error launching app: {e}")
        return JSONResponse(status_code=500, content={"error": f"Failed to launch app: {e}", "status": "error"})

@app.post("/screenshot")
def screenshot(request: Request):
    try:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"screenshot_{timestamp}.png"
        save_path = os.path.join(SHARED_DIR, filename)

        image = ImageGrab.grab()
        image.save(save_path)

        host = request.client.host + ":" + str(request.url.port or 5000)
        url = f"http://{host}/screenshot/{filename}"

        return {
            "status": "ok",
            "filename": filename,
            "path": save_path,
            "url": url
        }
    except Exception as e:
        print(f"Screenshot error: {e}")
        return JSONResponse(status_code=500, content={"error": str(e), "status": "error"})

@app.get("/screenshot/{filename}")
def serve_screenshot(filename: str):
    file_path = os.path.join(SHARED_DIR, filename)
    if os.path.exists(file_path):
        return FileResponse(file_path, media_type="image/png")
    else:
        return JSONResponse(status_code=404, content={"error": "file not found"})
    
@app.post("/get_ui_tree")
def get_ui_tree(data: AppTask):
    try:
        print(f"Getting UI tree for app: {data.name}, PIDs: {data.pids}")
        
        # 查找窗口
        window = find_window_by_pids(data.pids, data.name)
        
        if not window:
            error_msg = f'No window found for app {data.name} with PIDs {data.pids}'
            print(error_msg)
            return JSONResponse(
                status_code=404,
                content={"error": error_msg, "status": "error"}
            )
        
        # 提取UI树
        ui_tree = extract_ui(window, data.name)
        
        if not ui_tree:
            error_msg = f'Failed to extract UI tree for window {window.Name}'
            print(error_msg)
            return JSONResponse(
                status_code=500,
                content={"error": error_msg, "status": "error"}
            )
        
        print(f"Successfully extracted UI tree for window: {window.Name}")
        return {"status": "ok", "ui_tree": ui_tree}
        
    except Exception as e:
        error_msg = f"Error getting UI tree: {str(e)}"
        print(error_msg)
        return JSONResponse(
            status_code=500,
            content={"error": error_msg, "status": "error"}
        )

import os

@app.post("/close_app")
def close_app(data: PIDModel):
    pid = data.pid
    print(f"Closing app with PID: {pid}")

    # ——0) 跳过自己——
    if pid == os.getpid():
        return {"status": "skipped", "pid": pid, "message": "Refusing to close server process"}

    # ——1) 尝试 WindowControl.Close()（UWP 窗口有效）——
    try:
        win = WindowControl(ProcessId=pid)
        if win.Exists(0, 0) and hasattr(win, "Close"):
            print("Attempting WindowControl.Close()")
            win.Close()
            time.sleep(1)
    except Exception as e:
        print("WindowControl.Close() failed:", e)

    # ——2) 发送 WM_CLOSE——
    try:
        print("Posting WM_CLOSE to PID", pid)
        post_wm_close(pid)
        time.sleep(1)
    except Exception as e:
        print("post_wm_close failed:", e)

    # ——3) 最后强制杀进程树——
    try:
        print(f"taskkill /PID {pid} /T /F")
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        return {"status": "ok", "pid": pid, "message": "Terminated via taskkill"}
    except subprocess.CalledProcessError as e:
        print("taskkill failed, fallback to psutil:", e)
        if terminate_process_tree(pid):
            return {"status": "ok", "pid": pid, "message": "Terminated via psutil fallback"}
        else:
            return {"status": "error", "pid": pid, "message": "Both taskkill and psutil failed"}

@app.post("/close_apps")
def close_apps(data: PIDListModel):
    results = []
    for pid in data.pids:
        if pid == os.getpid():
            results.append({"pid": pid, "status": "skipped", "message": "Refusing to close server process"})
            continue

        # 同上：1) Close() 2) WM_CLOSE 3) taskkill/psutil
        try:
            win = WindowControl(ProcessId=pid)
            if win.Exists(0, 0) and hasattr(win, "Close"):
                win.Close(); time.sleep(1)
        except: pass

        try:
            post_wm_close(pid); time.sleep(1)
        except: pass

        try:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            results.append({"pid": pid, "status": "ok", "message": "Terminated via taskkill"})
        except subprocess.CalledProcessError:
            success = terminate_process_tree(pid)
            results.append({
                "pid": pid,
                "status": "ok" if success else "error",
                "message": "Terminated via psutil fallback" if success else "Both methods failed"
            })

    return {"results": results}

@app.post("/get_processes_by_exe")
def get_processes_by_exe(data: PathModel):
    """获取运行指定可执行文件的所有进程"""
    exe_path = os.path.abspath(data.path)
    processes = []
    
    try:
        for proc in psutil.process_iter(['pid', 'exe', 'name', 'create_time']):
            try:
                if proc.info['exe'] and os.path.samefile(proc.info['exe'], exe_path):
                    processes.append({
                        "pid": proc.info['pid'],
                        "name": proc.info['name'],
                        "exe": proc.info['exe'],
                        "create_time": proc.info['create_time']
                    })
            except (psutil.NoSuchProcess, psutil.AccessDenied, FileNotFoundError):
                continue
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e), "status": "error"})
    
    return {"processes": processes, "count": len(processes)}

@app.post("/get_ui")
def get_ui(data: PIDModel):
    try:
        root = uiauto.GetRootControl()
        top_windows = root.GetChildren()

        # 找到与传入 pid 匹配的窗口
        target_window = None
        for win in top_windows:
            if win.ProcessId == data.pid:
                target_window = win
                break

        if not target_window:
            return JSONResponse(status_code=404, content={"error": f"No window found with pid {data.pid}"})

        info_list = []
        for ctrl in target_window.GetChildren():
            rect = ctrl.BoundingRectangle
            info_list.append({
                "name": ctrl.Name,
                "control_type": ctrl.ControlTypeName,
                "rect": {
                    "left": rect.left,
                    "top": rect.top,
                    "right": rect.right,
                    "bottom": rect.bottom
                }
            })
        return {
            "app_name": target_window.Name,
            "pid": data.pid,
            "control_list": info_list
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/click")
def click(data: CoordModel):
    try:
        uiauto.Click(data.x, data.y)
        return {"status": "clicked", "x": data.x, "y": data.y}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

# ---------- 启动入口（用于命令行启动） ----------

if __name__ == "__main__":
    import uvicorn
    import sys
    parser = argparse.ArgumentParser()
    parser.add_argument("--shared-dir", default="shared", help="Shared directory for screenshots")
    args = parser.parse_args()
    SHARED_DIR = args.shared_dir
    uvicorn.run(app, host="0.0.0.0", port=5000)