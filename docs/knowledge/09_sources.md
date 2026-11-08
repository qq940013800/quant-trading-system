# 09 来源与延伸阅读（主索引）

> 本文件是 L2 知识库的统一出处索引。各章自己的「证据与来源」保留**论证上下文**，
> 本文件只做去重后的**主清单**，便于审计与复核。
>
> 收录规则：只收可公开获取、可复核的材料；二手报道只用于"据报道"口径；
> 无法追溯的数字不入库（见 `README.md` §1）。

---

## 1. 学术论文（方法与统计基础）

| 主题 | 文献 |
|---|---|
| Purged CV / embargo / meta-labeling / CPCV / PBO / DSR | López de Prado, *Advances in Financial Machine Learning*, Wiley, 2018（第 7、11、12 章） |
| Deflated Sharpe Ratio | Bailey, D. & López de Prado, M., "The Deflated Sharpe Ratio: Correcting for Selection Bias, Backtest Overfitting and Non-Normality", *Journal of Portfolio Management*, 2014 |
| PBO / CSCV | Bailey, D., Borwein, J., López de Prado, M. & Zhu, Q., "The Probability of Backtest Overfitting", *Journal of Computational Finance*, 2017 |
| 最小回测长度（MinTRL） | Bailey, Borwein, López de Prado & Zhu, "Pseudo-Mathematics and Financial Charlatanism", *Notices of the AMS*, 2014 |
| 数据窥探 / 多重检验 | White, H., "A Reality Check for Data Snooping", *Econometrica*, 2000；Hansen, P.R., "A Test for Superior Predictive Ability", *JBES*, 2005；Romano & Wolf, *Econometrica*, 2005 |
| 因子显著性门槛 | Harvey, Liu & Zhu, "…and the Cross-Section of Expected Returns", *Review of Financial Studies*, 2016（t > 3.0） |
| 时间序列动量 | Moskowitz, Ooi & Pedersen, "Time Series Momentum", *Journal of Financial Economics*, 2012 |
| 学术发表后的因子衰减 | McLean & Pontiff, "Does Academic Research Destroy Stock Return Predictability?", *Journal of Finance*, 2016 |
| 2007 量化地震 | Khandani & Lo, "What Happened to the Quants in August 2007?", 2007 |
| 闪崩机制 | SEC & CFTC, *Findings Regarding the Market Events of May 6, 2010*, 2010 |
| 订单流与价格冲击 | Cont, Kukanov & Stoikov, "The Price Impact of Order Book Events", *Journal of Financial Econometrics*, 2014 |
| 做市报价/库存 | Avellaneda & Stoikov, "High-frequency Trading in a Limit Order Book", *Quantitative Finance*, 2008 |
| 凯利公式 | Kelly, J.L., "A New Interpretation of Information Rate", *Bell System Technical Journal*, 1956 |
| 遍历性 | Peters, O., "The Ergodicity Problem in Economics", *Nature Physics*, 2019 |
| 波动率拖累 / 几何增长 | Vince, R., *The Mathematics of Money Management*, Wiley, 1992 |

---

## 2. 书籍（人物、机构、失败史）

| 主题 | 文献 |
|---|---|
| 交易员心理与规则 | Lefèvre, *Reminiscences of a Stock Operator*, 1923；Livermore, *How to Trade in Stocks*, 1940 |
| 海龟实验 | Faith, *Way of the Turtle*, 2007；Covel, *The Complete TurtleTrader*, 2007 |
| 市场奇才访谈 | Schwager, *Market Wizards* 系列（1989– ） |
| 反身性 | Soros, *The Alchemy of Finance*, 1987；*Soros on Soros*, 1995 |
| 冠军方法 | Minervini, *Trade Like a Stock Market Wizard*, 2013；*Think & Trade Like a Champion*, 2016 |
| 自营交易员 | Schwartz, *Pit Bull*, 1998 |
| 机构史 | Zuckerman, *The Man Who Solved the Market*, 2019（Renaissance） |
| 风险与不确定性 | Taleb, *Fooled by Randomness* (2001), *The Black Swan* (2007), *Antifragile* (2012) |
| 决策与思维模型 | Munger, *Poor Charlie's Almanack*；Kahneman, *Thinking, Fast and Slow*, 2011 |
| 原则与配置 | Dalio, *Principles*, 2017 |

---

## 3. 监管与官方文件（失败案例的事实底座）

| 事件 | 文件 |
|---|---|
| LTCM 1998 | President's Working Group on Financial Markets, *Hedge Funds, Leverage, and the Lessons of Long-Term Capital Management*, 1999 |
| 2010 闪崩 | SEC & CFTC, *Findings Regarding the Market Events of May 6, 2010* |
| Knight Capital 2012 | SEC, *In the Matter of Knight Capital Americas LLC*（15c3-5 处罚令，含时间线） |
| Barings 1995 | Board of Banking Supervision Inquiry into the Circumstances of the Collapse of Barings, 1995 |
| MF Global 2011 | 受托人报告与国会听证记录 |
| 2020 负油价 | CME Group 关于负价格支持的公开公告（2020-04） |
| Archegos 2021 | SEC 起诉书与相关判决 |
| FTX 2022 | 美国司法部起诉书与相关判决 |
| 中国程序化交易 | 中国证监会《证券市场程序化交易管理规定（试行）》（2024）及交易所实施细则 |
| 中国股指期货限制 | 中金所 2015-09 日内开仓限制公告 |

---

## 4. 机构公开资料（用于 01 篇）

- Renaissance Technologies / Medallion：公开报道与 Zuckerman (2019)；
- Two Sigma、D.E. Shaw、Millennium、Citadel / Citadel Securities、AQR、Man Group/AHL、Bridgewater：公司官网、公开访谈、致投资者信与监管披露；
- Jane Street、Jump Trading、Optiver、IMC、SIG、XTX Markets、Hudson River Trading：公司官网、公开技术博客/演讲、交易所做市商披露；
- WorldQuant：BRAIN 平台公开资料；
- 幻方量化（High-Flyer）、九坤、灵均、明汯：公司官网、公开报道与公开技术资料（AI 集群等）。

> 机构内部流程无法公开核实的部分，一律标注【行业共识】或【推断】，不伪装成事实。

---

## 5. 开源代码库与工具文档（用于 05 篇）

- 数据处理：pandas、polars、numpy、numba 官方文档；
- 机器学习：scikit-learn、LightGBM、XGBoost、CatBoost、PyTorch 官方文档；
- 优化/实验：Optuna、Ray、MLflow 官方文档；
- 量化框架：Microsoft qlib、nautilus_trader、vn.py、QuantConnect LEAN、zipline-reloaded、vectorbt、backtrader、freqtrade、hummingbot、FinRL；
- 组合与统计：PyPortfolioOpt、riskfolio-lib、skfolio、cvxpy、statsmodels、arch；
- 执行与协议：QuickFIX、Aeron、ONNX Runtime。

> **许可证与维护状态必须在使用前复核官方 LICENSE 与仓库活跃度**；本表不构成法律意见，也不承诺版本号。

---

## 6. 本仓库内部证据链

| 主题 | 文件 |
|---|---|
| 三条不变量与 11 条硬规则 | `AGENTS.md` |
| 死法清单 | `docs/ANTI_FRAGILE.md` |
| 已验证胜法 | `docs/SUCCESS_PLAYBOOK.md` |
| 事故档案 | `docs/ERROR_LOG.md` |
| 目标体系 | `docs/GOALS.md` |
| 冻结接口 | `docs/trading/AI_ML_SYSTEM_DESIGN.md` |
| 实现规范 | `docs/trading/IMPLEMENTATION_SPEC.md` |
| L1 深度参考 | `skills/quant-trading-expert/references/`（34 篇） |
| 过拟合防御代码 | `core/backtest/overfitting.py`（PBO 已改 CSCV，2026-11） |
| 验证体系 | `tests/test_backtest/test_overfitting.py`（14 passed） |

---

## 7. 引用纪律

1. 论文写作者、年份、期刊；书写作者和书名、年份；官方文件写发布机构与年份；
2. 媒体报道只用于"据报道"，且不与审计数据混用；
3. 任何数字若无法回溯到上述来源，删除数字、保留机制描述；
4. 新增来源先进本文件，再在章节引用编号，避免同一出处多处漂移。

*版本：v1.0 ｜ 2026-11-02*
