---
description: "发布前检查：依次调用 causal-guard、mql5-reviewer、backtest-runner，汇总是否可进入人工上线评审。"
agent: quant-program-architect
---
对当前改动执行发布前检查，只汇总结论，不做修改：

1. 用 `causal-guard` 审查涉及 `core/`、`scripts/`、特征、区域、退出的改动；如无相关改动，注明“不适用”。
2. 若改动涉及 `.mq5`/`.mqh`，用 `mql5-reviewer` 审查；否则注明“不适用”。
3. 用 `backtest-runner` 运行 `pytest -q` 及两个单测脚本；测试失败则停止，不继续后续步骤。
4. 汇总为一张表：检查项 / 结论（PASS、FAIL、UNKNOWN、不适用）/ 证据 / 需要人工处理的事项。

任何 `FAIL` 或 `UNKNOWN` 都视为不可上线，并列出最小修复或所需人工步骤。无法自动验证的项（实盘冒烟、经纪商差异）必须标注“未验证”。
