## 说明

一共有两个文件夹：

- client：被控制也就是用来运行app的一台电脑，也就是我会给你在实验室找的一台（你也可以先自己玩玩自己的电脑熟悉一下代码）。
- server：主控，也就是用来连接client然后输入命令，等它执行返回结果的一端。


### client部署

`windows_automation_server.py`就是你需要去适配不同平台的主文件，比如在我给你的代码里你可以看到就实现了一部分。你可以先熟悉好这个文件内代码的作用，随后可以自己仿照着来兼容其他架构的windows软件。
`start_server.bat`就类似windows端的bash文件，他主要的作用是在我的虚拟机上设置自动启动python脚本。

### server
`controller.py`就是一个类还有一些工具方法。作用就是在类中可以通过内部方法来向client发起调用请求，client的脚本正是监听这些请求。这方面你可以问chatgpt关于fastapi的相关知识。

### app
先给你一些app list：
- 笔记本
- 日历
- 天气
- 计算器
- 内置的视频/音频播放器
- 腾讯会议
- 飞书
- vscode
- Microsoft To Do
- OneNote
- XMind
- WinSCP
- 爱奇艺


## 100个常见应用软件列表（非游戏类）

### Windows自带应用
1. 文件资源管理器 -
2. 任务管理器 -
3. 控制面板 +
4. 设置(Windows Settings) -
5. 记事本(Notepad) +
6. 画图(Paint) -
7. 计算器(Calculator) +
8. 日历(Calendar) -
9. outlook(Mail) +
10. 照片(Photos) -
11. 相机(Camera) -
12. 录音机(Voice Recorder) -
13. 微软商店(Microsoft Store) -
14. 天气(Weather) -
15. 地图(Maps) -
16. google chrome +
17. Windows Media Player +
18. 截图工具(Snipping Tool) -
19. 便笺(Sticky Notes) -
20. 远程桌面连接(Remote Desktop) +

### 办公与生产力工具
1.  Microsoft Office(Word/Excel/PowerPoint) ++++
2.  WPS Office +
3.  Adobe Acrobat Reader(PDF阅读器) +
4.  Foxit PDF Editor -
5.  Notepad++(代码编辑器) -
6.  Visual Studio Code 
7.  Sublime Text +
8.  Evernote(笔记工具) +
9.  OneNote +
10. 印象笔记 +
11. 腾讯文档 +
12. xmind +
13. 钉钉(办公协作) +
14. 飞书(Lark) +
15. Zoom(视频会议) -
16. Microsoft Teams -
17. 腾讯会议 +
18. Slack(团队沟通) -
19. 百度网盘 +
20. 阿里云盘 +
21. Google Drive -

### 网络与通信
41. 微信(PC版) +
42. QQ(PC版) -
43. 微博(桌面版) -
44. 网易邮箱大师 +
45. Thunderbird(邮件客户端) +

### 多媒体与设计
51. VLC Media Player(视频播放器) +
52. PotPlayer +
53. 暴风影音 +
54. 爱奇艺(客户端) +
55. 腾讯视频(客户端) +
56. 优酷(客户端) +
57. 哔哩哔哩(客户端) +
58. GIMP(开源图像编辑) +
59. mgtv +
60. 美图秀秀(PC版) +
61. Audacity(音频编辑) +
62. 酷狗音乐 +
63. 酷我音乐 +
64. 网易云音乐 +
65. QQ音乐
66. Spotify +

### 安全与系统工具
1.  WinRAR +
2.  VMware(虚拟机)
3.  clash