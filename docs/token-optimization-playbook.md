# Token 节约 Playbook

> 第一性原理：token = 上下文窗口的计价单位，每轮推理全量过一遍。上下文越长 → 越贵、越慢、注意力越稀释。
> 目标：在保障质量前提下，把每轮系统注入从 ~91K 降到 ~25K（降幅 70%）。

---

## 三大浪费源（实测）

| 来源 | 每轮 token | 性质 |
|---|---|---|
| retained_skills 硬塞历史全文 | 30K | 平台行为，skill 未按需加载 |
| skill-selections 重复注入 | 25K | 同一 skill 出现两次全文 |
| installed-skills/plugins 静态列表 | 13K | 40+ skill 每轮全量列出 |

---

## Agent 行为规则（必须遵守，不废话）

1. **回复精炼**：不重复上下文里已有的信息；结论先行，不写铺垫。
2. **不重复 Read**：已读过的文件不重读；需要细节时按 file_path 定点 Grep 而非全量 Read。
3. **工具参数精简**：不传冗余描述；prompt 只写必要部分。
4. **大文件用 Grep 定位**：超过 500 行的文件不整读，用 Grep 找关键行号后再定点 Read。
5. **不主动触发不相关 skill**：一个任务只触发直接相关的 1-2 个 skill；其余需要时再加载。
6. **可视化从简**：能用表格说清的不用图；必须画图时用静态 HTML/SVG，不用 ECharts。
7. **错误信息只报一次**：同一错误不重复描述；修复后只报结果，不回溯过程。
8. **代码块最小化**：只贴关键 diff 或核心片段，不贴整文件。
9. **验证用最小命令**：一条命令能验证的不跑两条；能在容器内验证的不拷贝到本地。
10. **会话长了主动建议压缩**：当 trajectory 超过 5MB 时，建议用户开启新会话或主动 summary。

---

## 用户配置优化（会话级，见效最快）

1. **关闭不相关 skill selections**：每个会话只保留当前任务相关的 skill，其余关掉。
   - 量化开发会话：保留 `quant-trading-expert` + `doubao-coding-develop-backend-features` + `doubao-coding-develop-unit-tests`
   - 前端会话：加 `doubao-coding-develop-frontend-features` + `doubao-ui-design`
   - 其余（lark-wiki/lark-drive/chrome-devtools/notion/github/android-native/app-builder/browser-use-automation）默认关闭

2. **retained_skills 只保留本轮相关**：历史读过的 skill 不自动保留全文，需要时再 Read。

3. **定期开新会话**：每完成一个主线任务就开新会话，不要在一个会话里跨多个不相关任务。

---

## 基线测量

- 当前会话 baseline：每轮 ~91K token 系统注入，trajectory 10.8MB
- 优化目标：每轮 ~25K token，降幅 70%
- 测量方法：数 retained_skills 块官方 token 数 + skill-selections 块目测

---

## 版本

v1.0 · 2026-11-07 · 首次实测沉淀
