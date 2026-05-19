# Index Video Studio

一个本地网页端指数观察视频生成工具。它把“一个指数拆成 5 条视频”的内容框架固定下来，并支持用 1080x1920 信息卡片、男声配音、字幕和公开数据生成短视频。

## 功能

- 网页端填写指数资料，生成 5 条视频策划。
- 自动把图片按用途匹配到对应视频主题。
- 生成本地测试视频，适合先检查画面、字幕和节奏。
- 生成沪深300五条正式系列视频：
  - 跟踪什么
  - 行业分布和前十大权重
  - 在经典投资组合里的角色
  - 历史走势、收益、回撤和风险
  - 估值怎么看
- 使用公开数据源，生成结果包含 `manifest.json` 方便追溯。
- 固定风险提示：`仅作指数观察，不构成投资建议；本视频由 AI 辅助生成。`

## 项目结构

```text
.
├── index.html                    # 网页入口
├── assets/                       # 前端样式和交互
├── server.py                     # 本地网页服务和测试视频接口
├── render_csi300_series.py       # 沪深300五条正式视频生成器
├── render_global_index_batch.py  # 多指数示范视频生成器
├── render_zzhl_series.py         # 中证红利系列视频生成器
├── data/                         # 可提交的指数目录样例数据
├── requirements.txt              # Python 依赖
└── DEPLOYMENT.md                 # 部署和运行方法
```

生成的视频、音频、字幕、下载的数据源会输出到 `runs/`，该目录默认不提交到 GitHub。

## 本地运行

先安装 Python 依赖：

```powershell
cd D:\etf
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

启动网页：

```powershell
python -m uvicorn server:app --host 127.0.0.1 --port 8765
```

打开：

```text
http://127.0.0.1:8765/index.html
```

## 生成沪深300五条视频

确保电脑已安装 `ffmpeg`，然后运行：

```powershell
python render_csi300_series.py
```

生成结果会保存到：

```text
runs/csi300_series_时间戳/
```

每条视频目录里会包含：

- `final.mp4`
- `manifest.json`
- `scene_*.png`
- `subtitles_*.ass`
- `voice_*.mp3`

## 数据原则

- 不编造权重、估值、回撤和收益数字。
- 如果官方单张没有给出某个分位，可以用公开历史数据计算区间和分位，并在 `manifest.json` 中记录来源。
- 视频画面尽量说“目前”“发布以来”“历史最大回撤阶段”，具体日期保留在追溯文件里。
- 不使用“推荐买入”“可以上车”等投资建议表达。

## 部署

完整部署方法见 [DEPLOYMENT.md](DEPLOYMENT.md)。
