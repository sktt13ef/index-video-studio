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
- 封面只放指数名称、一句话定位和系列名。
- 正文卡会预留字幕区，正文和字幕不能重叠。
- 每张正文卡最多 3-5 行核心文字。
- 字体必须足够大，手机端可读。
- 如果文字过长，自动换行、缩小或要求人工复核。
- 画面正文、数字和图表必须由代码确定性生成，不交给 AI 图片模型生成。
