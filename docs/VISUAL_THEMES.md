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
