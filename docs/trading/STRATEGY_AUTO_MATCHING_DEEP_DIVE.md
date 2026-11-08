# 策略自动匹配模块——深度解读与落地路线图

> 文档性质：研究解读 + 落地路线图（中文，保留英文术语）
> 落盘日期：2026-11-02
> 服务对象：AI/ML 增强量化交易系统（Python 研究层 `core/scripts/ops` + MQL5 执行层 `mt5`），标的 XAUUSD M5。
> 输入依据（按序）：
> 1. 知识库分片 `shard_O_entries.md`（O01–O10 完整原文，含来源 URL 与未确认清单）；
> 2. `docs/trading/RESEARCH_MAPPING.md`（30 条研究→设计决策映射，下称"决策 #N"）；
> 3. `docs/trading/AI_ML_SYSTEM_DESIGN.md` 与 `IMPLEMENTATION_SPEC.md`（架构契约，第③章接口）；
> 4. 既有实现盘点：`D:\Trader\core\` 全量文件清单 + `core/features/regime.py`、`core/models/meta_label.py`、`core/models/cv.py`、`core/backtest/engine.py`、`core/registry/*` 关键签名（2026-11-02 只读浏览）；
> 5. `AGENTS.md`（三条不变量与 11 条硬规则）。
>
> 证据等级约定（沿用 RESEARCH_MAPPING 口径）：
> - **已证实** = 论文/官方文档一手来源；
> - **建议** = 从业者口径、单一来源、或研究结论向本项目（XAUUSD M5）的迁移推断（非已证实事实）；
> - **未确认/缺乏证据** = 公开渠道无证据，须在本项目数据上自行验证。

---

## 第 1 节 第一性原理：为什么需要"按市场状态 + K 线形态自动匹配策略/参数"

### 1.1 问题的根源：分布非平稳，单一策略隐含"分布平稳"假设

市场收益的**条件分布不是平稳的**：均值、方差、自相关结构随时间分段变化（regime = 趋势市 vs 震荡市、高波动 vs 低波动）。任何"单一策略 + 一套参数"的系统，都隐含假设分布平稳；而现实是**分段平稳**（O01，已证实：Hamilton 1989 体制转换模型证明宏观序列呈分段自回归结构）。["https://users.ssc.wisc.edu/~bhansen/718/Hamilton1989.pdf","https://www.imf.org/external/pubs/ft/wp/1999/wp99107.pdf"]

两条经验事实决定了"匹配"的方向：

1. **波动率聚类是金融中最稳健的经验事实之一**（大波动跟大波动、平静跟平静，GARCH(1,1) 即为此建模），因此"先按波动率分桶"几乎是所有 regime 系统的第一刀（O01，已证实）。["https://www.luxalgo.com/library/concept/garch-family-clustering/","https://arxiv.org/html/2606.09478"]
2. **K 线形态携带的信息极薄**：fxbacktest.app 在 28 个品种、698,580 根 bar（含黄金）、420,317 个形态信号上的对照测试显示，最强形态（hammer）仅比匹配随机入场高 6.5 个百分点，且未过 50% 盈亏平衡线；**扣除真实点差后，日线 24 个"形态+目标"组合只有 1 个过盈亏平衡，4 小时图 24 个全灭（0/24）**（O03，已证实大样本实证）。["https://fxbacktest.app/research/candlestick-pattern-win-rates/"] 因此形态绝不能独立开仓，只能机械化编码为 L3 层的**条件过滤特征**（决策 #17）。

结论（推断，依据 O01/O03）：需要自动匹配的不是"每根 bar 换一个策略"，而是"用已收盘 bar 的可观测统计量推断当前状态，据此调整策略权重与仓位"——识别本质是用 `available_at <= bar.close` 的数据去推断**潜在状态**。

### 1.2 合理目标定位（O09 结论）：成功定义 = 稳健降风险，不是自动调优 Sharpe

**不可实现的**（O09，已证论证）：精确预测下一根 bar 处于哪个 regime、并实时选出当时最优策略与最优参数。理由三重：regime 识别天然滞后（O02）、状态边界连续渐变（O02）、参数自适应必带过拟合（O07）。["https://federalreserve.gov/pubs/ifdp/2008/956/ifdp956.htm"]

**可实现的**（O09）：①regime 作为**过滤器**（高波/震荡时降频降仓）；②策略间**稳健加权混合**（非硬切换）；③阈值来自**分布**而非绩效；④风险叠加层控制总敞口。

因此本模块的**成功定义**（引用 O09 结论 + RESEARCH_MAPPING 补充说明）：

> 自适应地**降低 OOS 最大回撤、whipsaw 次数与成本占比**——不是"自动调出更高 Sharpe"。验收主指标为 OOS 回撤 / whipsaw 频率 / 成本占比，Sharpe 仅作次要参考。["https://federalreserve.gov/pubs/ifdp/2008/956/ifdp956.htm","https://www.man.com/maninstitute/lets-admit-it"]

机构立场与此一致：Man Group 公开材料标题即"Nobody Knows What's Coming Next"——靠多策略并行 + 风险叠加（momentum / intraday correlation / volatility overlay 最多把市场敞口降 50%）控制回撤，而非预测状态（O04，机构口径为一方说法）。["https://www.man.com/maninstitute/lets-admit-it"]

### 1.3 与 AGENTS.md 三条不变量的逐条关系

| 不变量 | 本模块的具体含义 | 研究依据 |
|---|---|---|
| **① 因果单向** | 任何 regime 统计量（ADX/Hurst/ATR 分位/未来的 BOCPD）只能用 `available_at <= bar.close` 的已收盘 bar；`as_of` 装饰器 + `LookAheadError` 是强制手段（设计文档 3.1/3.2）。**滞后不是 bug，而是因果性 + 平滑两个不可去除约束叠加的天然代价**（O02，已证实：ADX 双重平滑需数根确认 bar 才越过 25，被直接称为 "lag trap"）。["https://www.vrdnation.com/adx-measuring-trend-strength/"] | O01/O02；硬规则 1（前视守卫）、规则 5（intra-bar 不决策） |
| **② 决策可审计** | 每一笔选择依据必须落盘可还原：当时的状态分、置信度、w 权重向量、阈值来源集（CLEAN/KNOWN）、决策规则版本、最终手数（O08 建议的审计字段，已落实为 `Decision` schema + `threshold_dataset` + `decision_rule_version` 字段）。回测-实盘特征不一致是实盘亏损首因，特征快照即审计对象（决策 #21/#30，部分已证实）。 | O08；不变量 2 |
| **③ 阈值来自分布** | 所有阈值（ATR 分位 30/70、ADX 灰区、deadband 宽度、w 的 EMA 半衰期）来自 **CLEAN 集经验分布分位数**，而非绩效网格搜索；regime 偏离参数向全局默认收缩（shrinkage）。DSR 证明：同一数据上试 N 个变体，即使所有变体真实 Sharpe=0，期望的最大 Sharpe 也严格为正且随 N 增大（O07，已证实）。["https://saral.money/blog/backtest-overfitting-deflated-sharpe/","https://escholarship.org/content/qt4hn4t174/qt4hn4t174.pdf?v=lg"] | O07；决策 #9/#10；硬规则 2（集合分离）、规则 11（trials_N 原子递增） |

硬规则映射补充：L1 位置（供需区/OB/FVG，KNOWN 集构建）→ L2 状态（本模块 regime 分类器，CLEAN 集估统计量）→ L3 触发（专家策略 + meta-labeling），**禁止 L3 结果反哺 L1**（硬规则 3）；阈值/参数走 config 冻结，禁止硬编码点值/手数/阈值（硬规则 8）。

---

## 第 2 节 方法对比（带来源与证据分级）

### 2.1 Regime 识别方法对比

| 方法 | 原理 | 滞后性分析 | 对本项目（XAUUSD M5）适用性 | 证据等级 | 来源 |
|---|---|---|---|---|---|
| **HMM / Markov 体制转换** | 离散不可见状态 s_t + 马尔可夫转移链，EM/滤波估计；输出滤波概率而非硬标签 | 滤波本身是平滑，状态刚切换的前几根 bar 必然看不清 | M5 在线端计算量偏大；建议作**离线校准器**输出概率，在线端用轻量分位替代 | 已证实（方法学）；M5 实证部分已查证 | ["https://users.ssc.wisc.edu/~bhansen/718/Hamilton1989.pdf","https://www.imf.org/external/pubs/ft/wp/1999/wp99107.pdf","https://pdfs.semanticscholar.org/bc80/6ca12b65abf8b47d464baa80b76c6a20a5a1.pdf"] |
| **GMM / 聚类（K-means、时序聚类）** | 收益/波动/方向特征投影到特征空间分簇；时序聚类要求簇标签时间连续 | 全样本聚类天然前视；在线版本需滚动适配 | 不推荐在线用；"软聚类"捕捉波动率渐进漂移在 COVID 前后优于 HAR 为 2026 arXiv 新证据 | 部分已查证 | ["https://arxiv.org/html/2510.03236"] |
| **波动率 regime（ATR / realized vol / GARCH）** | 按已实现波动水平与持续性分高/低波；波动率聚类最稳健 | ATR 是短窗平滑，滞后相对最小 | **第一刀首选**：ATR 分位数（CLEAN 集估），可在线、因果可证 | 已证实 | ["https://www.luxalgo.com/library/concept/garch-family-clustering/","https://arxiv.org/html/2606.09478"] |
| **ADX 趋势强度** | Wilder(1978) 0–100 量纲测趋势强度（不测方向）；经验阈值 25 | 双重平滑，需数根 bar 才越阈值——"lag trap"（O02） | 第二刀首选（短窗）；**ADX=25 只是惯例不是定律**，Wilder 本人在 20–25 灰区工作；阈值必须用 CLEAN 分布分位 | 已证实（滞后/阈值惯例）；M5 直接实证未确认 | ["https://www.vrdnation.com/adx-measuring-trend-strength/","https://captain-trading.com/en/free-trading-course/adx","https://tradesmrt.com/en/strategies/adx-dmi-trend-strength/"] |
| **Hurst 指数 / 方差比检验** | H=0.5 随机游走；H>0.5 持续（趋势），H<0.5 反持续（均值回归）；H(t) 向 0.5 回归 | 窗口长、估计噪声大，滞后最严重 | **只用于 CLEAN 集做状态分布先验，不用于逐 bar 决策**（O01 建议） | 已证实（方法学）；迁移为建议 | ["https://arxiv.org/html/2602.00548","https://federalreserve.gov/pubs/ifdp/2008/956/ifdp956.htm","https://arxiv.org/html/2509.18837v1"] |
| **贝叶斯在线变点 BOCPD（Adams & MacKay 2007）** | 在线维护"距上次变点的 run-length"后验，输出结构突变概率 | 对"状态刚切换"的早期预警反而是最及时的信号 | 建议作**第二路交叉验证**：与 HMM/分位信号同时报警才动权重，降误报（O01/O02 建议） | 已证实（开创性方法）；金融直接应用部分已查证 | ["https://arxiv.org/html/2609.07989v1","https://bioconductor.statistik.tu-dortmund.de/cran/web/packages/RegimeChange/RegimeChange.pdf"] |
| **小波（wavelet）** | 多尺度分解收益率能量，分离趋势与噪声 | 概念性 | 本片仅检索到概念性提及，**缺乏 M5 可落地证据，不采用**（未确认） | 缺乏证据 | O01 未确认清单 |

**综合落地选择（推断，依据 O01/O02）**：L2 状态层 = 二维连续分数 x = ATR/realized-vol 分位（CLEAN 集估）、y = 短窗 ADX/Hurst 方向持续度；z = BOCPD run-length 概率（二期第二路信号）。**输出连续分数/隶属度而非硬标签**，为 2.3 的加权混合服务。

### 2.2 动态选择机制对比

| 机制 | 定位 | 证据等级 | 来源 |
|---|---|---|---|
| **Meta-labeling（López de Prado, AFML 2018）** | 把"做什么方向"（primary）与"要不要做、做多大"（secondary 二进制分类）解耦；二级模型输出开仓概率 p 与仓位乘数 k，本质是**风险叠加过滤器**，不替换信号发生器。**最可落地的在线选择形态**——本项目已有初级信号（L3 触发），只需喂一个二级分类器。注意：二级模型训练必须 purged/embargo，否则标签泄漏（O05）。 | 已证实（AFML 3.6，pp.50–53 官方目录）；某基线精度 17%→63% 为单一来源，**不可外推** | ["https://www.wiley.com/en-us/-p-9781119482086","https://paperswithbacktest.com/course/meta-labeling","https://docs.jesse.trade/docs/research/ml/meta-labeling"] |
| **Mixture-of-Experts（MoE）/ 资本分配网络** | 每个专家专精一种市场环境（趋势/反转/突破/敞口控制），router 按 regime 加权；学术与工业界共识方向。但零售资金/算力下**少而精**：2–3 个逻辑低相关专家即可，并行 10 个同源变体只会相关性虚高 + 成本翻倍（O04 风险）。 | 已证实（学术）；机构参数为一方说法 | ["https://arxiv.org/html/2509.05080","https://arxiv.org/html/2606.30997v1","https://www.man.com/maninstitute/lets-admit-it"] |
| **Contextual bandit（LinUCB/LinTS）** | 选择时可见上下文（当前 regime），线性收益假设下 regret Õ(√T)。适合"按当前 regime 上下文选策略"的理论框架。 | 已证实（算法）；金融直接应用部分已查证 | ["https://mwshumway.github.io/data/contextual_bandits.pdf"] |
| **EXP3 / 对抗赌博机** | 无分布假设下亚线性 regret。**直接搬到金融不可行**：每次探索付真实点差+滑点，M5 探索代价极高，且金融反馈自相关不满足独立假设。只借鉴其"权重慢更新 + 强制探索下限"思想，探索以"小权重"而非真金白银试错实现（O05 建议）。 | 已证实（算法）；金融 regret 实证**缺乏**（未确认） | ["https://courses.cs.washington.edu/courses/cse599m/21sp/resources/Exp3Notes.pdf","https://proceedings.neurips.cc/paper_files/paper/2019/file/ae2a2db40a12ec0131d48acc1218d2ef-Paper.pdf"] |

### 2.3 切换 vs 混合：whipsaw 成本、滞回缓冲区（deadband）原理

- **硬切换（switching）的代价是双重的**：每次错误翻转 = 一笔亏损 + 手续费 + 滑点；震荡市里 stop-and-reverse 类系统的"小亏"被放大成连续流血（O06，已证实机制）。["https://arrowalgo.com/whipsaw-trading/"]
- **阈值附近振荡被命名为 "threshold whipsaw"**：ADX 在 cutoff 窄带内振荡会反复开关过滤器，缓解方式是"要求 ADX 上升而非仅过阈值"或加缓冲带（O02/O06，已证实机制）。["https://www.getswoopr.com/technical-analysis/trend-indicators/adx-regime-filter-trend-strength-not-direction/"]
- **转换期（transition）是最大亏损来源**：真正亏钱的往往不是"错误状态"里的策略，而是状态切换前后两套策略都不适应的过渡区——此时波动率跳升、相关性结构剧变（O02）。

**滞回缓冲区（deadband / hysteresis）原理**：进入状态与退出状态用**不同阈值**（双向阈值），中间"灰区"不切换、维持原权重；再要求**连续 N 根已收盘 bar** 确认才让状态生效。本质是**用反应速度换稳定性**——多等 N 根 bar / 双向阈值，换取消弭阈值附近的高频翻转。

**O06 结论（引用）**：推荐"状态隶属概率 → 连续加权混合 + 双向 deadband + 连续 N bar 确认"，权重用 EMA 慢更新；灰区/确认未到时权重向"中性全局默认"收缩（如 w=(1/3,1/3,1/3)），而非在两个策略间跳变；总敞口由风控叠加层单独控制，权重混合只决定策略间分配。["https://fortraders.com/blog/momentum-vs-mean-reversion-strategies-for-challenges","https://www.bigmovealgo.com/post/market-regime-filter/"]

对应设计决策：**RESEARCH_MAPPING 决策 #8**——"regime 输出连续概率/分位分数与 w 权重向量，不用硬标签；deadband 加权混合而非硬切换"，证据等级"已证实（机制）/建议（最佳实践）"，与硬规则 2（regime 统计量只在 CLEAN 集估计）对齐。

---

## 第 3 节 系统设计现状：已实现 vs 未实现

> 盘点口径：2026-11-02 对 `D:\Trader\core\` 全量只读浏览。**先按既有 `core/` 现状为准**；本路线图阶段 1–3（策略库注册、regime 权重路由、策略匹配器接线）由并行实现分片落地（`core/registry/strategy_registry.py`、`core/registry/strategy_router.py`、`core/registry/strategy_matcher.py` 已存在），其与本设计的连续权重口径差异在下表"待接线"列标注。

### 3.1 已实现清单

| # | 能力 | 所在文件 | 现状要点 |
|---|---|---|---|
| 1 | **连续 regime 权重向量** | `core/features/regime.py` | `@as_of adx()`（Wilder 双重平滑）、`hurst_exponent()`（R/S 滚动窗）、`regime_weights(adx_val, hurst_val, atr_pct, *, adx_q_lo, adx_q_hi, mr_hurst_thresh)` → `{w_trend, w_mr, w_range}` 归一化连续向量；CLEAN 分布分位阈值由调用方传入，模块内无绩效字面量；全 NaN 时防御性返回均匀 (1/3,1/3,1/3) |
| 2 | **meta-labeling 二级分类器** | `core/models/meta_label.py` | `MetaLabeler(base_model, q_lo=0.30, q_hi=0.70)`；fit 时从训练段 p 的经验分布取 30/70 分位；predict 返回 `(p, k)`，`k = clip((p-q_lo)/(q_hi-q_lo), 0, 1)`——仓位系数来自分布分位，不用固定 0.5 |
| 3 | **Purged walk-forward** | `core/models/cv.py` | `purged_walk_forward(n, embargo_bars, n_splits, *, label_window_bars=None)`；expanding-window 时间序折；purge 剔除标签重叠 + embargo 剔除每折后污染段；`embargo_bars < label_window_bars` 时 raise `PurgedCVError` |
| 4 | **事件驱动回测引擎** | `core/backtest/engine.py` | `run_backtest(bars, strategy: Strategy Protocol(on_bar_close), cost_model, risk_cfg)`；bar-by-bar 只在已收盘 bar 决策；内置熔断三态（CircuitBreaker）、海龟分级降档（每 -10% ×0.8）、realized vol、新闻窗口、`meta_p_threshold`、审计 Decision 收集 |
| 5 | **Decision 审计落盘与回放** | `core/audit/record.py`、`core/audit/replay.py` | JSONL 单行追加；replay 可还原 feature_snapshot / model_version / final_signed_lots / reject_reason（IMPLEMENTATION_SPEC §4 第 6 条）；测试 `tests/test_audit_replay.py` |
| 6 | **策略版本生命周期注册** | `core/registry/strategy_registry.py` | `StrategyStatus` 状态机（draft→backtest→paper→live→retired）、`StrategyVersion.freeze_parameters()`、`PerformanceSnapshot`、`StrategyRegistry.register/get/get_live/compare_versions`；测试 `tests/test_strategy_registry.py` |
| 7 | **regime→策略权重路由（静态配置表）** | `core/registry/strategy_router.py` | `StrategyDescriptor(regime_profile=dict[regime→base_weight])`；`StrategyWeightRouter.route(regime)` → 归一化白名单权重；模块 docstring 显式声明"权重表是路由配置，**不是绩效网格搜索产物**"；SUPPORTED_REGIMES = (trend/range/volatile/quiet) |
| 8 | **策略匹配打分 + 防抖动切换阈值** | `core/registry/strategy_matcher.py` | `StrategyProfile(best/worst_regimes, expected_sharpe, max_drawdown, correlation_cluster)`、`MarketRegime`、`StrategyMatcher.rank/select/select_portfolio`、`switch_threshold=0.15`（新策略得分须高出阈值才切换） |
| 9 | **专家策略骨架** | `core/strategies/trend_breakout.py`、`core/strategies/mean_reversion.py`、`core/models/ml_trend_strategy.py` | 趋势突破 / 均值回归两个专家已具雏形；engine 内置 DemoBreakoutStrategy |
| 10 | **DSR / PBO / CPCV 过拟合防御** | `core/backtest/overfitting.py` | `deflated_sharpe_ratio(returns, trials)`、`probability_of_backtest_overfitting`、`combinatorial_purged_cv`、`overfitting_diagnostic`——O07 的 DSR 门禁已有工具 |
| 11 | **模型层其余件** | `core/models/` | `labels.py`（triple-barrier）、`baseline.py`（Logistic/Ridge）、`gbm.py`（LightGBM）、`drift.py`（PSI/KS） |
| 12 | **数据管线与集合分离** | `core/data/` | `bar.py`/`loader.py`/`validator.py`/`timezone.py`/`splits.py`（CLEAN/KNOWN 打标、静默集显式拒绝）/`synthetic.py`（martingale/trend_regime 合成数据，供决策 #27 泄漏自检） |
| 13 | **风控层** | `core/risk/` | `sizing.py`（vol-target 手数 + fractional Kelly 上限）、`stops.py`（止损单调，放宽必 raise）、`circuit.py`（日内权益熔断三态机） |
| 14 | **入口脚本** | `scripts/` | `run_walkforward.py`、`ingest_xauusd.py`、`run_backtest.py` |

### 3.2 未实现 / 待接线清单

| # | 缺口 | 说明 | 依据 |
|---|---|---|---|
| 1 | **BOCPD 在线变点分（z 信号）** | `features/regime.py` 只有 ADX/Hurst/ATR 分位，无 run-length 后验输出；O01 建议的"第二路交叉验证"信号缺位 | O01 |
| 2 | **带滞回的权重状态机** | `regime_weights()` 是瞬时分数→权重的静态映射；**无 EMA 慢更新、无双向 deadband（进入/退出不同阈值）、无"连续 N bar 确认"计数器、无 state_confidence 字段输出** | O06；决策 #8 |
| 3 | **连续 w 向量 ↔ registry 离散 regime 的桥接** | `features/regime.py` 输出连续 (w_trend, w_mr, w_range)；`strategy_router.py` 用离散键 (trend/range/volatile/quiet) 查表；离散 vol 桶如何从 atr_pct 派生、w 向量如何与路由权重合成，**尚未接线统一** | O04/O06；本路线图阶段 1–3 由并行实现分片落地 |
| 4 | **混合选择器接入回测主循环** | engine.py demo 中 `regime_weights={"trend":1.0,"mr":0.0,"range":0.0}` 为硬编码 demo 值；目标仓位合成式 `Σ w_i · expert_i_signal · k · m`（O10 架构图）尚未在 `run_backtest` 中实现 | O10；设计文档 3.1 Signal schema |
| 5 | **元层验证对比脚本** | "混合层 vs 单一策略基线"的对比报告（OOS ≥30 笔、按 regime 分组盈亏分解、whipsaw 次数统计、成本占比）无独立脚本；`run_walkforward.py` 是单一模型 WF，不是元层基线对比 | O08 |
| 6 | **参数稳定性分析（邻域平坦度）** | `overfitting.py` 有 DSR/PBO，但"在 CLEAN 集做 walk-forward 参数邻域平坦性扫描（小扰动不改结果才采用，尖峰即过拟合）"未实现 | O07 |
| 7 | **审计日志固定字段扩充** | `Decision` 已有 feature_snapshot / threshold_dataset / decision_rule_version；O08 建议的逐字段快照（atr_clean_quantile、bocpd_runprob(z)、state_confidence、w 向量分量、recent_spread、meta_p/k、risk_multiplier_m）尚未逐字段落盘 | O08 §4.4 |
| 8 | **HMM 离线校准器（可选）** | O01 建议 HMM 作离线校准输出概率、在线端用轻量分位；当前未实现，列为可选项而非必需 | O01（建议） |

---

## 第 4 节 完整落地路线图（5 阶段）

> 每阶段给出：目标 / 关键设计决策（引用研究来源）/ 验收标准（可检验）。全程遵守 AGENTS.md：阈值只从 CLEAN 分布派生（`scripts/calibrate_regime.py --mode distribution`）、decision_rule 实验前冻结、trials_N 只由实验脚本原子递增、每次改动附单测且黄金集断言不放宽（硬规则 10）。

### 阶段 1：策略库与统一接口

- **目标**：把 `core/registry/` 已有的注册/路由/匹配三件套与 `core/strategies/` 专家、`features/regime.py` 连续 w 向量统一为同一套接口——所有专家实现同一个 `Strategy Protocol.on_bar_close(history, bar) -> Optional[Signal]`，Signal 携带 `regime_weights` 连续向量（设计文档 3.1），未注册策略白名单之外不出现在任何路由结果里。
- **关键设计决策**：
  - 策略画像（best/worst regime、相关性聚类）是**静态配置**，不来自在线绩效追逐（`strategy_router.py` 已声明此原则）；权重按近期表现追逐会在 regime 切换时把权重搬到刚失效的策略上（O04 风险，建议）。["https://arxiv.org/html/2509.05080"]
  - 专家数量控制在 2–3 个逻辑低相关（趋势突破 / 均值回归 / 区间），不做 10 个同源变体（O04 最佳实践，建议）。
  - 离散 regime 标签与连续分数的桥接规则冻结在 config：atr_pct → {quiet, volatile} 桶边界 = CLEAN 分布 30/70 分位（决策 #9）。
- **验收标准**：
  1. 注册一个假策略，`run_backtest` 能跑通多专家 + 权重白名单过滤（未注册策略信号被拒且落 reject_reason="not_registered"）；
  2. `pytest -q` 全绿，含新增 `test_strategy_unified_interface.py`；
  3. registry 三件套的既有测试（`tests/test_strategy_registry.py`）不放宽。

### 阶段 2：regime 分类器（L2）

- **目标**：L2 输出完整的状态分向量 `s=(x, y, z)` 与状态置信度 `c`：x = ATR/realized-vol CLEAN 分位（已实现）、y = 短窗 ADX/Hurst（已实现）、**z = BOCPD run-length 变点概率（新增）**；c ∈ [0,1] 综合阈值缓冲带位置与 z 报警强度。
- **关键设计决策**：
  - BOCPD 在线维护 run-length 后验，只用已收盘收益更新（O01，已证实方法学）。["https://arxiv.org/html/2609.07989v1"]
  - BOCPD 与分位信号**交叉验证**：二者同时报警才动权重，单一信号只降权重置信度、不触发切换（O01/O02 建议，降误报）。
  - ADX/Hurst 阈值全部 CLEAN 分布分位；ADX=25 不作为定律硬编码（O02，已证实"惯例非定律"）。["https://captain-trading.com/en/free-trading-course/adx","https://tradesmrt.com/en/strategies/adx-dmi-trend-strength/"]
  - Hurst/方差比只用于 CLEAN 集先验估计，不逐 bar 决策（O01 建议：窗口长、噪声大）。
- **验收标准**：
  1. 新增 `test_regime_no_lookahead.py` 扩展：BOCPD 喂打乱时间索引合成数据必抛 `LookAheadError`（复用 `tests/fixtures/causal_guard/` c05_clean 夹具语义）；
  2. BOCPD 统计量只从 CLEAN 集估计的代码审查确认；
  3. 置信度 c 字段写入 Decision.feature_snapshot。

### 阶段 3：带滞回的混合选择（w 向量状态机）

- **目标**：在阶段 2 分数之上实现 O06 推荐的完整权重状态机：`w = softmax 相关(s)` 经 **EMA 慢更新**（半衰期 = 分布派生值）、**双向 deadband**（进入/退出不同阈值）、**连续 N bar 确认**（N 取分布派生值，不拍脑袋）；状态置信度 c 低时 w 向全局默认 (1/3,1/3,1/3) 收缩；目标仓位 = `Σ_i w_i · expert_i_signal · k · m` 接入 `run_backtest`。
- **关键设计决策**：
  - 连续加权混合而非硬切换：硬切换在 whipsaw 区反复挨打（O06，已证实机制）。["https://arrowalgo.com/whipsaw-trading/"]
  - deadband + 连续 N bar 确认："单 bar 翻转模式会把两个能用的策略变成一台 whipsaw 机器"（O06，从业者共识一方说法，与决策 #8 一致）。["https://fortraders.com/blog/momentum-vs-mean-reversion-strategies-for-challenges","https://www.bigmovealgo.com/post/market-regime-filter/"]
  - meta-labeling 作为"是否下注/下多大"的二级过滤层接入（已实现 `MetaLabeler`，接 L3 输入：s、L1 位置布尔、形态特征、近期点差），二级模型训练走 purged/embargo（O05/O08，已证实）。["https://www.wiley.com/en-us/-p-9781119482086","https://handwiki.org/wiki/Purged_cross-validation"]
  - 总敞口由风控叠加层单独控制（m 系数：高 ATR / BOCPD 报警 / 相关性异常时降仓），权重混合只决定策略间分配（O04/O06）。
- **验收标准**：
  1. 构造 ADX 在阈值附近窄带振荡的合成行情：单 bar 翻转策略 whipsaw 次数 > 混合状态机（量化断言：whipsaw 次数下降）；
  2. 状态置信度低（灰区）时 w 单调趋近 (1/3,1/3,1/3)，单测断言；
  3. 混合层与单一策略基线跑同一回测，输出对比报告骨架（阶段 5 完成）；
  4. 熔断三态、新闻窗口拒开仓在混合模式下仍生效（回归测试）。

### 阶段 4：参数稳定性分析

- **目标**：对阶段 1–3 全部阈值与权重参数，在 CLEAN 集上做 walk-forward 邻域平坦性分析；任何"按 regime 调参"的主张必须过 DSR 门禁（按试验次数 N 校正）。
- **关键设计决策**：
  - 参数自适应的唯一允许形态：**全局默认参数（冻结）+ regime 偏离项 = 全局 × (1−shrinkage) × 小系数**；shrinkage 随该 regime 累计样本数增大而减小（O07 建议，James-Stein 思想，小样本下几乎总是降低预期误差）。["https://academic.oup.com/jfec/article/24/2/nbag002/8512976"]
  - 参数邻域平坦才采用：小扰动不改变结果 = 稳健；尖峰 = 过拟合（O07 最佳实践）。
  - 复用 `core/backtest/overfitting.py::deflated_sharpe_ratio(trials=...)` 作为门禁；trials_N 只由 `run_gate_experiment.sh` 原子递增（硬规则 11）。
- **验收标准**：
  1. 输出参数敏感性报告：每个参数 ±20% 邻域内 OOS 绩效变化幅度表；尖峰参数被标记并退回 config 人工审核；
  2. 任何 variant 登记走 `run_gate_experiment.sh --registry registry.yaml --variant <v> --mode dryrun`，decision_rule 实验前冻结；
  3. DSR 计算被单测覆盖（已知合成序列上 DSR 随 trials_N 增大而下降的单调性断言）。

### 阶段 5：元层验证与审计

- **目标**：把"自动匹配模块"当独立系统做 walk-forward + purged/embargo 验证，产出"混合层 vs 单一策略基线"的完整对比报告；审计日志逐字段落盘。
- **关键设计决策**：
  - 元层指标 = **装上选择层后的整体绩效 vs 单一策略基线**的差值，而非"某状态下某策略很赚"（O08，已证实）；OOS 交易数 ≥30 才有统计意义（O08 引用）。["https://www.bigmovealgo.com/post/market-regime-filter/"]
  - 验收主指标（O09）：**OOS 最大回撤、whipsaw 次数、成本占比**显著低于单一策略基线；Sharpe 次要。["https://federalreserve.gov/pubs/ifdp/2008/956/ifdp956.htm"]
  - 报告四件套：①混合层 vs 基线 Sharpe/回撤差；②OOS 交易数 ≥30；③按 regime 分组盈亏分解；④每笔决策审计字段齐全（O08 最佳实践）。
  - 审计固定字段（O08 §4.4 建议，落地）：`bar_time | symbol | atr | atr_clean_quantile(x) | adx_or_hurst(y) | bocpd_runprob(z) | state_confidence(c) | w_trend | w_mr | w_range | in_position_zone(L1) | pattern_features | recent_spread | meta_p | meta_k | risk_multiplier_m | final_signed_position | decision_rule_version | threshold_dataset(CLEAN/KNOWN) | accepted_or_rejected + reason`。
  - 泄漏自检：martingale 合成数据跑整条 pipeline 若仍"盈利"说明 pipeline 有前视（决策 #27，已证实 AFML 方法）。
- **验收标准**：
  1. `scripts/` 新增元层对比脚本：输入基线策略 + 混合配置，输出对比 Markdown 报告到 `experiments/reports/`；
  2. `audit/replay.py` 用快照完整还原某笔决策的全部 4.4 字段（测试 `test_audit_replay.py` 扩展）；
  3. martingale 合成数据回测期望 PnL ≈ 零成本随机水平（泄漏自检单测）；
  4. 未验证项显式标注：MT5 实盘执行（retcode 重试/滑点/幂等）未验证；经纪商差异（点差/合约规格）未验证；GBM/meta-labeling 在 XAUUSD M5 的 OOS 相对线性基线增益未验证（IMPLEMENTATION_SPEC §6）。

---

## 第 5 节 明确不做与风险

### 5.1 明确反对：按 regime 做绩效网格搜索

这是本模块最危险的失败模式（O07/O10）。把 N（试验次数）乘以状态数 K，以为在"自适应"，实际是在历史上雕刻模式：

- DSR（Bailey & López de Prado 2014）已证实：零真实 Sharpe 的 N 次独立试验，期望最大 Sharpe 严格为正（O07，已证实）。["https://saral.money/blog/backtest-overfitting-deflated-sharpe/","https://www.foliolab.ai/docs/metrics/deflated-sharpe-ratio","https://escholarship.org/content/qt4hn4t174/qt4hn4t174.pdf?v=lg"]
- 回测过拟合被定性为"多重检验的特例"（O07）。["https://escholarship.org/content/qt9tq3327h/qt9tq3327h.pdf"]
- 对应 RESEARCH_MAPPING 决策 #9（阈值全部来自 CLEAN 集分布分位数，禁止按绩效网格搜索）与决策 #10（实验前冻结 decision_rule、trials_N 原子递增、上线前过 PSR/DSR/PBO 闸门）——**直接对应 AGENTS.md 不变量 3 与硬规则 11**。
- 任何"按状态挑参数"的主张，不过 DSR 校正一律不采纳。

其他明确不做（RESEARCH_MAPPING 补充说明 + O 片共识）：LLM 信号；单形态独立开仓（O03）；硬切换代替加权混合（O06）；EXP3 真金白银在线试错（O05）。

### 5.2 内生风险：regime 识别天然滞后

- 滞后 = 因果性（只能用已收盘 bar）+ 平滑（抑制噪声）两个不可去除约束的叠加（O02，已证实）。**不追求"最早识别"，追求"识别错时少亏"**——用 deadband + 混合权重让状态不确定时自动降仓，而非急换（O02 最佳实践）。
- 风险一：把滞后当噪声去"优化反应速度"（缩短窗口、取消平滑）→ 直接放大 threshold whipsaw（O02）。
- 风险二：转换期满仓追新状态 → 正好接在波动率跳升、点差扩大的时刻（O02；成本模型三档见决策 #18）。
- 风险三：混合权重更新过快 → 权重本身变成另一个 whipsaw 源（O06）。
- 风险四：把"regime 过滤降回撤"误当成"提高收益" → 预期错位（O09）。

### 5.3 证据缺口清单（未确认/缺乏证据，须在本项目数据上自行验证）

| 缺口 | 出处 |
|---|---|
| HMM/BOCPD/各 regime 方法在 **XAUUSD M5** 上的直接、可复现、walk-forward 对比实证——公开渠道未见 | O01/O02 未确认清单 |
| meta-labeling 把某基线精度 17%→63%：单一来源（mental-momentum），不可外推 | O05 |
| Man AHL 的具体 overlay 参数：机构营销口径，非同行评议 | O04 |
| FVG/order block/SMC 的大样本扣费后盈利证据：缺乏同行评议对照，现有为从业者口径 | O03 |
| 小波（wavelet）regime 在本项目的可落地性：仅概念性提及，不采用 | O01 |
| EXP3/对抗赌博机在真实金融交易中的直接 regret 实证：缺乏，仅作思想借鉴 | O05 |
| GBM 在 XAUUSD M5 的 OOS 相对线性基线增益 | RESEARCH_MAPPING 补充说明（N 未确认） |
| 元层"混合 vs 单一基线"在本项目上的实际差值（回撤/whipsaw/成本占比） | 待阶段 5 在本项目数据上产出 |

---

### 附：本文引用的研究条目编号清单

- **shard_O 分片**：O01（regime 方法全景）、O02（regime 陷阱）、O03（K 线形态）、O04（机构多策略平台/MoE）、O05（在线选择算法）、O06（切换 vs 混合/deadband）、O07（参数自适应/防过拟合/DSR）、O08（元层验证）、O09（第一性原理评估与可行边界）、O10（设计结论与实现清单）。
- **RESEARCH_MAPPING 决策**：#5（purged walk-forward）、#6（triple-barrier 标签）、#7（meta-labeling）、#8（连续权重 + deadband）、#9（阈值来自分布，禁绩效网格）、#10（DSR/PBO 门禁）、#16（供需区 KNOWN 集构建）、#17（形态只做 L3 加成特征）、#18（成本三档模型）、#21（审计日志）、#26（置信度→仓位映射）、#27（martingale 泄漏自检）、#30（Feature Store 一致性）。
