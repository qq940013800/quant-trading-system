# 另类数据入模路径设计（盘点 → 清洗 → 特征化 → IC/衰减检验 → 入模/淘汰）

> 状态：**待评审草稿**，不含生产代码。
> 范围：现有 `data_providers` / `data_sources` 适配器盘点，另类数据从接入到入模/淘汰的门槛、流水线与审计；标注已接入决策链（confirmed）/ 推断为展示分析消费（inferred）/ 未知（unknown）。
> 边界：阈值由 CLEAN 分布校准，不照搬机构数值，不编绩效数字；不改交易/风控/资金逻辑。

## 1. 目标

1. **适配器盘点台账**：逐一登记数据适配器类别、上游、更新频率、当前消费方与状态（行情行情 / 展示聚合 / 研究候选 / 未知）。
2. **标准化入模流水线**：接入 → 清洗与质量校验 → PIT 特征化（因果）→ IC/ICIR/t 统计/衰减检验 → 入模候选或淘汰，每步留审计。
3. **门槛与去重**：候选因子须通过显著性、衰减半衰期、覆盖度/缺失率、与现有因子相关性去重等门槛；门槛阈值来自 CLEAN 分布，不预设固定数值。
4. **入链边界清晰**：明确哪些另类数据已进入策略决策链、哪些仅服务展示/分析；未追踪清楚前不得标记为已入链。

## 2. 现状证据

> 标注口径同前：**confirmed** = 文件/import 可佐证；**inferred** = 路径推断待核对；**unknown** = 快照无法判定。

### 2.1 confirmed — 行情类数据源（`backend_api_python/app/data_sources/`）

| 文件 | 职责（按工厂路由） |
|---|---|
| `factory.py` | 市场类别别名归一；`get_kline`/`get_ticker`；按 market 创建数据源实例；未知类别告警透传。 |
| `base.py`、`errors.py` | 数据源基类与异常体系。 |
| `cache_manager.py`、`circuit_breaker.py`、`rate_limiter.py` | 缓存、熔断、限流基础设施。 |
| `crypto.py`、`forex.py`、`us_stock.py`、`cn_stock.py`、`hk_stock.py`、`asia_stock_kline.py`、`futures.py`、`moex.py`、`tencent.py` | 各市场 K 线/报价适配器。 |
| `cn_hk_fundamentals.py` | 沪深/港股基本面适配器（产出是否可回测特征见 2.3）。 |

### 2.2 confirmed — 全球市场聚合/展示类适配器（`backend_api_python/app/data_providers/`）

| 文件 | 数据类别 | 缓存口径（`__init__.py` CACHE_TTL） |
|---|---|---|
| `news.py` | 财经新闻；经济日历负载封装 | `market_news` 180s |
| `economic_calendar.py` | 经济日历事件 | `economic_calendar*` 3600s |
| `sentiment.py` | 市场情绪（Fear&Greed、VIX、DXY 类） | `market_sentiment` 21600s |
| `adanos_sentiment.py` | Adanos 市场情绪 | 走情绪缓存口径 |
| `macro_series.py` | 宏观序列 | — |
| `commodities.py` | 大宗商品行情 | `commodities` 120s |
| `indices.py` | 股票指数 | `stock_indices` 120s |
| `heatmap.py` | 板块/币种/外汇/商品热力图 | `crypto_heatmap` 300s、`market_heatmap` 120s |
| `opportunities.py` | 机会扫描（本地股票机会价） | `trading_opportunities` 3600s |
| `crypto.py`、`forex.py` | 行情辅助适配器 | — |
| `__init__.py` | 共享缓存层：TTL 表、single-flight 合并、stale-while-revalidate、失效清理。 | — |

### 2.3 confirmed — 消费方（基于 import 盘点）

| 消费方 | 引用的适配器 |
|---|---|
| `routes/global_market.py` | `adanos_sentiment`、`news`（新闻/日历）、`heatmap`；缓存层 `cached_or_compute/clear_cache/invalidate`。 |
| `routes/ai_chat.py` | `macro_series`、`news`（日历负载）。 |
| `services/global_market_data.py` | `commodities`、`indices`、`opportunities`、`sentiment`。 |
| `services/market_data_collector.py` | `sentiment`（约 1372 行附近，经缓存读写）。 |
| `services/factor_library.py` | `FactorCategory` 枚举含 `SENTIMENT`、`ALTERNATIVE`；`BaseFactor.validate` 要求 OHLCV 列；已列因子为动量/价值/质量/波动率/成交量/技术类。 |

### 2.4 confirmed — 研究层边界

- 对 `core/` 全量检索：**未见**导入 `sentiment/news/macro_series/economic_calendar` 等 provider。
- `core/backtest/costs.py` 的 `news_window` 是**配置传入**的时间戳列表，用于新闻窗口点差放大；不主动抓取 provider 新闻数据。

### 2.5 inferred（待沿调用链核对）

- `market_data_collector.py` 中 sentiment 字段是仅做缓存聚合/看板回填，还是进入了某种评分/信号路径，需继续追踪其下游调用才能定性。
- `factor_library.py` 的 `SENTIMENT/ALTERNATIVE` 类别是否已有对应因子实现，还是仅枚举占位，需逐类核对。

### 2.6 unknown / 缺口

- **决策链接入状态 unknown**：任一情绪/新闻/宏观/基本面字段是否进入策略信号或 L1–L5 决策链，当前快照未见接线；在逐路由/服务追踪完成前，一律标 unknown，不得写成已入链。
- **历史落库与 PIT 对齐缺失**：另类数据未见按 bar 对齐的 point-in-time 特征存储；新闻/日历/情绪的发布时间、修订时间与 `available_at` 口径未定义。
- **检验流水线缺失**：未见 IC/ICIR/t 统计、衰减曲线/半衰期、相关性去重的离线检验脚本与报告留存。
- `cn_hk_fundamentals.py` 基本面字段能否构成可回测因子（更新频率、修订处理、覆盖度）unknown。

## 3. 候选方案权衡

| 维度 | A. 先登记后入模（台账 + 离线检验，过门槛再接链） | B. 在现有展示适配器上直接派生因子接策略 | C. 独立另类数据管道（采集落库 → 清洗 → 特征表 → 检验 → 研究层） |
|---|---|---|---|
| 数据可控性 | 中：先摸清现状再接 | 低：展示缓存口径直接进信号风险高 | 高：独立采集与落库 |
| PIT 正确性 | 检验阶段统一补齐 | 易混入未对齐/未来信息 | 管道内强制 PIT 守卫 |
| 因果风险 | 低：离线侧过前视守卫 | 高：展示层时间戳口径未校验 | 低：守卫前置 |
| 落地成本 | 低 | 中（但返工风险高） | 高 |
| 审计可追溯 | 检验报告 + 账本留痕 | 弱：缓存链路难回溯 | 强：全链路血缘 |
| 与现有缓存层关系 | 复用只读，不改缓存语义 | 复用缓存结果作信号输入（不建议） | 旁路独立存储 |
| 入模速度 | 慢一步登记，再检验 | 看似快，隐患大 | 最慢，规模化后最优 |

## 4. 选型建议（供评审，分阶段）

### 阶段 1：台账与消费方追踪（不接决策链）

- 建立适配器台账：名称、类别、上游、更新频率、缓存 TTL、消费方、状态（confirmed 行情 / inferred 展示分析 / unknown 待追踪）。
- 沿调用链追踪 2.5 两处推断点，把展示/分析消费与信号消费区分清楚；追踪结论回写台账。
- 明确边界：在检验流水线就绪前，另类数据只服务展示/研究，不进入在线决策链。

### 阶段 2：离线清洗 + PIT 特征化 + 门槛检验

- 清洗与质量校验：覆盖度、缺失率、异常值、时间对齐、时区口径（与 Python 端 `--tz` 一致，禁硬编码）；上游修订（revision）须保留版本。
- PIT 特征化：另类字段按 `available_at <= bar.close` 对齐到已收盘 bar；新闻/日历事件不得使用发布时刻之后才可知的信息；特征定义挂接特征注册表（见 `design-feature-store.md`）。
- 门槛检验（只在 CLEAN 集估阈值）：IC、ICIR、t 统计、衰减曲线与半衰期、与现有技术因子的相关性去重；样本区间、覆盖度、缺失率随报告留存。
- 检验结果写入实验账本：入模候选或淘汰均留痕，失败/淘汰不删除（trials 诚实口径，见 `design-mlops-experiment.md`）。

### 阶段 3：过门槛因子进入候选策略 → AB/paper → 接链

- 候选因子经特征注册表登记后进入策略研究；再经 AB/paper 验证（规则事前冻结）才允许接入在线决策链。
- 未过门槛者标记淘汰并保留审计记录；已入链因子若后续衰减越限，按漂移对账流程处理（#108）。

### 不建议

- 把展示层缓存数据直接派生为信号输入。
- 用未来新闻/日历事件对齐当前 bar，或忽略数据修订。
- 照搬机构 IC/相关性阈值；门槛数值须由 CLEAN 分布校准。
- 未做相关性去重就批量把另类因子灌入模型。

## 5. 未验证假设

- 上游 API 的历史回溯长度：能否支撑 IC/衰减/半衰期检验，需逐适配器核实。
- 文本类数据的时间戳口径：发布时间、抓取时间、修订时间与延迟分布，决定 `available_at` 正确性。
- 基本面数据的更新频率与修订规则；频率过低的字段不适合做短周期因子。
- 另类因子与现有 OHLCV 因子的相关结构，需在阶段 2 样本上实测，不预设结论。

## 6. 上线前置条件与验收标准

### 前置条件

- 台账覆盖 `data_sources/` 与 `data_providers/` 全部适配器，状态标注无悬空 unknown（除确实无法追踪项并注明原因）。
- PIT 对齐与时区校验有单测；检验脚本配套前视守卫测试；门槛阈值有分布校准记录。

### 验收标准

1. **台账完整**：每个适配器的类别、频率、上游、消费方、状态清晰；展示分析与决策链消费可区分。
2. **检验报告齐备**：每个候选另类特征含样本区间、覆盖度、缺失率、IC/ICIR/t、衰减/半衰期、与现有因子相关性、结论（入模候选 / 淘汰）。
3. **集合与因果合规**：检验不触碰 HELD_OUT；统计量阈值来自 CLEAN 分布；特征对齐满足 `available_at <= bar.close`。
4. **留痕可追溯**：入模候选经特征注册表与实验账本登记；淘汰记录可回溯到检验输入与结论。
5. **入链可审计**：决策链引用某另类特征时，审计可还原来源适配器、数据版本与取值时间。

## 7. 对应 TODO / 阻塞编号

- P2-2：因子库扩展到 20+（另类弱信号因子的主要承接项；每个因子配套单测、前视守卫、CLEAN 集 IC 衰减检验）。
- P2-3：五层识别 ML 增强（另类特征作为输入候选，前提是阶段 2 检验通过）。
- P2-5：PostgreSQL 历史 K 线/另类数据入库（离线检验的数据前提）。
- P1-2：五层识别接入真实 K 线（PIT 对齐与时间口径的实测场景）。
- #108：周期对账（已入链另类因子的衰减/漂移监控挂载点）。
- RULES.md 3.1（前视防御）、3.2（集合分离）；`top-firm-gap-analysis.md` 差距 2：另类数据当前 0%，本设计为其入模路径。

## 8. 风险与未验证

- 当前"是否入决策链"多为 unknown，台账追踪完成前不得在界面/文档中宣称某另类数据已驱动信号。
- 上游数据可得性（历史长度、修订、限流/熔断行为）未验证，可能影响阶段 2 检验可行性。
- 情绪/新闻类文本若引入 NLP 加工，其模型版本与血缘需另走 MLOps 注册流程（见 `design-mlops-experiment.md`），本文档不展开。
- 本设计不含生产代码；落地改动须附单测并经评审。
