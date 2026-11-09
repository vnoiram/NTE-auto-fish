<div align="center">

# NTE 自动钓鱼

[English](../README.md) | [简体中文](README_zh.md) | [日本語](README_ja.md)

**面向实时游戏控制的可视化、可调校自动钓鱼助手。**

基于 Python、OpenCV、MSS、PyDirectInput 和 DearPyGui 构建。

---

[![GitHub License](https://img.shields.io/github/license/Chizukuo/NTE-auto-fish)](https://github.com/Chizukuo/NTE-auto-fish/blob/main/LICENSE)
[![GitHub Release](https://img.shields.io/github/v/release/Chizukuo/NTE-auto-fish)](https://github.com/Chizukuo/NTE-auto-fish/releases)
[![Build Status](https://github.com/Chizukuo/NTE-auto-fish/actions/workflows/build.yml/badge.svg)](https://github.com/Chizukuo/NTE-auto-fish/actions)
[![GitHub Stars](https://img.shields.io/github/stars/Chizukuo/NTE-auto-fish)](https://github.com/Chizukuo/NTE-auto-fish/stargazers)

</div>

## 关于此分支

本仓库是 [Chizukuo/NTE-auto-fish](https://github.com/Chizukuo/NTE-auto-fish) 的 fork。以下新增功能由 fork 作者实现，日常使用中此 fork 更为出色：

- **自动选择游戏所在的显示器**：启动时自动选中显示游戏窗口的显示器（可在设置中关闭）；暂停期间更换显示器后，开始时会重新校准。
- **在仪表盘上设置自动停止**：指定钓获数和/或时间（分、秒）并点击“设置”，从点击的那一刻开始计数。`0` 表示不限制；按时间停止时会先钓完正在进行的这一条，并在下一次抛竿前停止。
- **开始延迟**：点击开始后，在首次抛竿前随机等待 1.4-2.6 秒，便于切换到游戏窗口。
- **大幅改进的区域调整**：区域检查的进度日志、紧挨检查按钮的重新截图、一键屏幕编辑器、按区域及全部重置、显式保存，咬钩区域和抛竿判定区域也支持拖动与宽高调整。
- **更稳的追踪**：光标到达条的最边缘时仍能继续追踪，默认的条区域也略微加宽。
- **新增拟人化操作**：原版没有拟人化行为。此 fork 新增了随机的按键按下/松开节奏、反应延迟、微小修正操作和时序波动，并调整了默认参数。
- **更好的缺饵/抛竿失败检测**：不再依赖对话框文字或等待时间，而是检查抛竿后动作栏图标是否仍然可见。它不依赖游戏语言，也不依赖时间，因此更稳定。
- **日间/傍晚/夜间配置（实验性）**：为不同时段提供检测颜色配置，并可自动识别背景来切换配置，从而提高检测率。
- **更快的区域检查 OCR。**
- **固定的构建**：默认图标为角色插画，构建名称固定（除非指定，否则不会带随机构建 ID）。

**不向上游提交 PR 的原因：** 此 fork 把随机名称选项改为固定名称，并把图标换成了另一个角色。这属于“宗教性”分歧（工程师口中的“宗教”，即喜好问题而非对错问题），因此不打算让上游合并。

**维护方针：** 此 fork 是一次性的，不会定期更新，也不会跟进上游的改动。

## 项目亮点

- **实时控制台**：在 GUI 中查看状态、钓获数、会话时长、FPS、PID 输出、ROI 数据和视觉追踪健康度。
- **更安全的控制流程**：界面启动后默认暂停；停止命令优先处理；暂停、停止、校准和退出时会释放已按住的按键。
- **运行时调参**：PID、HSV 阈值、时序、输入按键、全局热键、校准和调试选项都可以在设置页调整。（[详细设置指南](SETTINGS_GUIDE_zh.md)）
- **分辨率自适应**：基于比例的 ROI 校准配合分辨率比例缩放，自动适配 1080p、2K、4K 及自定义分辨率。
- **高效截图与输入**：使用 `mss` 捕获屏幕区域，使用 `PyDirectInput` 发送更适合游戏环境的输入事件。
- **便携构建**：GitHub Actions 生成 GUI 单文件 EXE 和 CLI 源码包。

## 项目结构

| 路径 | 说明 |
| :--- | :--- |
| `start_gui.py` | 推荐的 GUI 启动入口。 |
| `main.py` | 无界面入口和核心运行循环。 |
| `config.py` | PID、HSV、按键、时序和校准配置。 |
| `gui/` | DearPyGui 控制中心、面板和线程安全桥接。 |
| `modules/` | 截图、输入、视觉识别和钓鱼逻辑模块。 |
| `templates/` | 用于自动 ROI 校准的比例数据。 |
| `tools/ratio_annotator.py` | 从截图标注比例 ROI 的辅助工具。 |

## 快速开始

### 方式一：使用预构建程序（GUI）

1. 从 [Releases](https://github.com/Chizukuo/NTE-auto-fish/releases) 下载最新的 `NTE-Auto-Fish-v*.*.*-Windows-x64.exe`。
2. 以管理员身份运行，确保模拟输入可以进入游戏。

### 方式二：CLI 包

1. 从 [Releases](https://github.com/Chizukuo/NTE-auto-fish/releases) 下载 `NTE-Auto-Fish-v*.*.*-CLI.zip` 并解压。
2. 先执行 `python -m pip install -r requirements.txt` 安装依赖。
3. 更多用法请在终端运行 `python main.py --help`。可用命令：`start`、`calibrate`、`config show/set`、`reset`。

### 方式三：从源码运行

```bash
git clone https://github.com/Chizukuo/NTE-auto-fish.git
cd NTE-auto-fish
pip install -r requirements.txt
```

启动 GUI：

```bash
python start_gui.py
```

启动无界面模式：

```bash
python main.py
```

## 注意事项

- Windows 下建议在管理员终端中运行。
- 无边框窗口或窗口化全屏通常具有更稳定的截图效果。
- 全局热键可以在 GUI 中修改，编辑后会重新注册。
- 调试日志会把额外追踪数据写入 `fishing_data.csv`；品牌构建会在文件名中加入构建标识。

## 已知问题

- **黄昏/日出光照干扰**：游戏内日出和日落时段的暖黄色环境光会严重干扰基于 HSV 的光标检测，导致追踪失败、钓鱼成功率大幅下降。这是当前颜色检测方案的固有局限。如遇此情况，可尝试在设置中调整光标 HSV 阈值以适配偏移后的光照条件。
