# Script Templates

这里存放 Global50 的差异化脚本模板。模板只负责表达结构，不负责事实和数字。

## 目录

- `broad_based/`：宽基指数
- `dividend/`：红利指数
- `sector/`：行业指数
- `overseas/`：海外指数
- `strategy/`：策略指数
- `technology/`：科技成长指数
- `low_volatility/`：低波动指数

每个目录都有一个 `episodes.json`，固定包含 5 条 episode：

1. `01_index_intro`
2. `02_holdings_breakdown`
3. `03_portfolio_role`
4. `04_return_drawdown_risk`
5. `05_valuation_view`

## 使用原则

- 同类型指数可以共用框架，但必须根据数据变化调整讲述角度。
- 模板里的 `{index_name}`、`{market}`、`{provider}`、`{role_summary}` 等占位符只能由结构化 profile 或 data_used 数据填充。
- 模板不能绕过 `data_validation.py` 和 `compliance_check.py`。
- 如果关键数据没有补齐，该指数必须停留在 `needs_data` 或 `needs_review`。
- 模板生成的是脚本草稿，不是最终成片文稿。

## 校验

```powershell
python -m src.script_templates
```

校验内容包括：

- 7 类模板是否齐全。
- 每类是否有 5 条 episode。
- episode 顺序是否一致。
- 是否缺少主题、风险点、所需数据、画面建议和脚本文稿。
- 是否命中禁用表达。
