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

## 数据校验和追溯

第二阶段新增了生产前校验模块：

- `src/source_registry.py`：统一数据源结构和来源校验。
- `src/data_used_builder.py`：生成每集 `data_used.json`，记录视频里展示的数字。
- `src/data_validation.py`：检查指数基础信息、来源、日期、权重、估值、回撤、历史收益等关键数据。
- `src/compliance_check.py`：检查成品脚本和画面文字是否命中禁用表达。

沪深300正式生成器已经接入这些检查。每条 episode 渲染前会先生成 `data_used.json` 并执行数据校验和合规检查；检查失败会阻止生成，并把状态写入 `manifest.json`。

每条视频的 `manifest.json` 会记录：

- `index_id`
- `index_name`
- `index_code`
- `region`
- `index_type`
- `template_type`
- `style_theme`
- `data_date`
- `source_items`
- `script_version`
- `render_version`
- `compliance_check_result`
- `data_validation_result`
- `quality_check_result`

## 差异化脚本模板

第三阶段新增了 Global50 脚本模板系统：

- `templates/scripts/broad_based/`
- `templates/scripts/dividend/`
- `templates/scripts/sector/`
- `templates/scripts/overseas/`
- `templates/scripts/strategy/`
- `templates/scripts/technology/`
- `templates/scripts/low_volatility/`

每类模板固定包含 5 条 episode，覆盖认识、成分、组合角色、历史风险、估值五个主题。模板只负责表达结构，不负责事实和数字；最终脚本仍必须通过 `data_validation.py` 和 `compliance_check.py`。

校验模板：

```powershell
python -m src.script_templates
```

根据 profile 渲染脚本草稿时，系统会按 `index_type` / `template_type` 选择不同模板。例如海外宽基会走 `overseas`，科技成长会走 `technology`，红利策略会走 `dividend`。

## 生成 Global50 生产计划

第一阶段只生成 50 个指数的生产计划、资料 profile 和数据缺口报告，不生成视频：

```powershell
python build_global50_plan.py
```

输出文件：

- `data/global50/global50_plan.csv`
- `data/global50/profiles/{index_id}.json`
- `data/global50/sources/source_registry.json`
- `data/global50/global50_readiness_report.html`
- `runs/global50_dry_run_时间戳/`

`data_status = ready` 的指数才允许进入后续视频生成。当前计划会把只有目录级资料的指数标成 `needs_data`，把候选身份还需要人工确认的指数标成 `needs_review`。

## 部署

完整部署方法见 [DEPLOYMENT.md](DEPLOYMENT.md)。
