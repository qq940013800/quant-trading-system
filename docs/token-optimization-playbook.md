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

4. **保持系统提示与模型稳定，命中 prompt cache**：
   - 原理：系统提示 / 工具清单 / 已加载 skill 前缀稳定时，服务端可命中 prompt cache，复用已计算的前缀，显著降本降延迟（OpenCode、Hermes 等同源原理）；前缀一旦变化（切模型、改 system prompt、增删工具/skill 选择），缓存失效需整段重算。
   - 长会话内**不要频繁切换模型**，也不要反复增删 skill/MCP 选择；确需切换或裁剪工具集时，集中在会话开始前完成，而不是中途反复横跳。
   - 缓存命中是成本优化手段，不替代上面的上下文压缩规则；二者叠加。

### 4.1 命中率与降本幅度：测量边界（未验证）

- **现状标注（未验证）**：本仓库运行在代理环境，底层模型 provider 的缓存命中计数与节省 token 不向本地暴露；§4 目前只是原理性原则，**命中率、降本幅度均未在本项目实测**，不引用任何具体百分比或缓存命中 token 数。
- **本地可观测的代理指标（不等于命中率）**：会话内模型变更次数、system prompt / 工具与 skill 选择集变更次数、前缀保持稳定的连续轮次。这些只反映"前缀是否稳定"，可作为 cache 友好度的粗代理；前缀越稳定，命中概率越高，但不能反推命中数。
- **真实命中率的取数位置**：需在 provider 观测面板或账单明细读取 `cached_tokens` / 缓存命中前缀长度与 `prompt_tokens` 对比；接入对应 provider 后再回填实测值。在此之前，任何"降本 X%"都属待验证假设。
- **失效信号（可本地自查）**：中途切模型、改 system prompt、增删工具/skill/MCP 选择集、更换会话身份，都会使既有前缀缓存失效；这些动作集中在会话开始前完成，可减少重算。

---

## 基线测量

- 当前会话 baseline：每轮 ~91K token 系统注入，trajectory 10.8MB
- 优化目标：每轮 ~25K token，降幅 70%
- 测量方法：数 retained_skills 块官方 token 数 + skill-selections 块目测

---

## 版本

v1.0 · 2026-11-07 · 首次实测沉淀
