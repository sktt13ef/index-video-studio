# Global50 视觉主题样例

第四阶段新增了全球指数视觉主题系统。它只生成用于人工确认的静态样例图，不生成配音和视频。

```powershell
python render_visual_theme_samples.py
```

输出目录：

```text
runs/visual_theme_samples_时间戳/
```

目录中包含：

- 8 张 `cover_*.png` 封面样例
- 8 张 `card_*.png` 正文卡样例
- 每张图片对应的 `.json` 视觉元数据
- `visual_samples_report.html`
- `visual_quality_report.html`
- `sample_manifest.json`

视觉引擎文件：

- `config/style_themes.yaml`
- `src/visual_engine/theme_loader.py`
- `src/visual_engine/card_layout.py`
- `src/visual_engine/text_fit.py`
- `src/visual_engine/visual_quality_check.py`

硬性规则：

- 所有样例为 1080x1920。
- 所有大面积背景使用浅色，不使用深色顶栏或深色整块底板。
- 封面只放指数名称、一句话定位和系列名。
- 正文卡会预留字幕区，正文和字幕不能重叠。
- 每张正文卡最多 3-5 行核心文字。
- 字体必须足够大，手机端可读。
- 如果文字过长，自动换行、缩小或要求人工复核。
- 画面正文、数字和图表必须由代码确定性生成，不交给 AI 图片模型生成。

## 第五阶段 dry_run 审核流程

正式批量生成前先运行 dry_run：

```powershell
python render_global50_batch.py --dry-run
```

可选筛选：

```powershell
python render_global50_batch.py --index csi300
python render_global50_batch.py --index csi300 --episode 1
python render_global50_batch.py --render-sample 5
python render_global50_batch.py --render-ready
```

当前阶段 `--render-sample` 和 `--render-ready` 是保护式入口：会生成审核材料和 `render_guard.json`，但不会绕过人工确认直接生成 `final.mp4`。

输出目录：

```text
runs/global50_dry_run_时间戳/
```

主要文件：

- `global50_plan.csv`
- `batch_review.html`
- `batch_manifest.json`
- `{index_id}/profile.json`
- `{index_id}/index_manifest.json`
- `{index_id}/episode_*/script.md`
- `{index_id}/episode_*/storyboard.json`
- `{index_id}/episode_*/cover.png`
- `{index_id}/episode_*/card_preview_01.png`
- `{index_id}/episode_*/data_used.json`
- `{index_id}/episode_*/manifest.json`
- `{index_id}/episode_*/quality_report.html`

## 数据补齐到 ready

先从可验证的数据源做起，不硬凑 50 个指数。当前已提供沪深300的数据补齐入口：

```powershell
python enrich_global50_ready_data.py --index csi300
```

它会更新：

- `data/global50/profiles/csi300.json`
- `data/global50/global50_plan.csv`
- `data/global50/source_cache/csi300/`

沪深300补齐的数据包括：

- 官方指数页面、官方单张、官方编制方案
- 行业权重 TOP5
- 前十大权重股
- 历史年度收益
- 历史最大回撤
- PE/PB 当前值、历史区间和分位
- 股息率当前值和近期区间

运行后该指数会变成 `data_status=ready`，但 `review_status` 保持 `pending`。这是故意的：数据准备好不等于人工审核已经批准，正式出片仍然需要显式批准。
