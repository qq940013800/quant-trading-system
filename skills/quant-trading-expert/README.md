# Quant Trading Expert - AI 技能知识库

> 基于第一性原理和全球顶级量化机构最佳实践构建

## 概述

这是一个为 AI Agent 设计的量化交易专家技能库，包含 31 份深度参考文档，覆盖从策略设计到实盘执行的完整链路。

## 设计原则

### 1. 第一性原理
不依赖"别人怎么做"，从最基本的事实和真理出发推导：
- 价格是什么？
- 风险是什么？
- 策略为什么有效？
- 策略什么时候会失效？

### 2. 顶级机构对标
参考 Renaissance Technologies、Two Sigma、Citadel、Jane Street 等全球顶级量化机构的实践。

### 3. 失败模式优先
先想清楚这个策略怎么会死，再想它怎么赚钱。

## 文档结构

### 基础理论层
| 文档 | 内容 |
|------|------|
| [first-principles.md](references/first-principles.md) | 量化交易第一性原理框架 |
| [mental-models.md](references/mental-models.md) | 思维模型工具箱 |
| [quant-strategy-landscape.md](references/quant-strategy-landscape.md) | 全球量化策略全景 |

### 策略设计层
| 文档 | 内容 |
|------|------|
| [trading-strategies.md](references/trading-strategies.md) | 交易系统与策略体系 |
| [technical-analysis-playbook.md](references/technical-analysis-playbook.md) | 技术分析实战手册 |
| [market-structure-analysis.md](references/market-structure-analysis.md) | 市场结构与价格行为 |
| [strategy-matching.md](references/strategy-matching.md) | 策略自动匹配模块 |

### ML/AI 层
| 文档 | 内容 |
|------|------|
| [ml-playbook.md](references/ml-playbook.md) | AI/ML 实战手册 |
| [overfitting-defense.md](references/overfitting-defense.md) | 过拟合防御方法论 |
| [model-explainability.md](references/model-explainability.md) | 模型可解释性 |
| [mlops.md](references/mlops.md) | 企业级 MLOps 与实验管理 |

### 风控执行层
| 文档 | 内容 |
|------|------|
| [risk-and-execution.md](references/risk-and-execution.md) | 风控与执行系统设计 |
| [position-sizing.md](references/position-sizing.md) | 资金仓位管理 |
| [portfolio-management.md](references/portfolio-management.md) | 组合管理与多策略优化 |
| [risk-models-and-stress-testing.md](references/risk-models-and-stress-testing.md) | 风险模型与压力测试 |

### 工程实践层
| 文档 | 内容 |
|------|------|
| [system-architecture.md](references/system-architecture.md) | 企业级系统架构 |
| [dev-practices.md](references/dev-practices.md) | 工程最佳实践 |
| [backtest-realism.md](references/backtest-realism.md) | 回测真实性与执行成本 |
| [debugging-and-optimization.md](references/debugging-and-optimization.md) | 系统调试与优化 |

### 基础设施层
| 文档 | 内容 |
|------|------|
| [database-architecture.md](references/database-architecture.md) | PostgreSQL 数据库架构 |
| [database-ops-playbook.md](references/database-ops-playbook.md) | PostgreSQL 运维实战 |
| [docker-infrastructure.md](references/docker-infrastructure.md) | Docker 容器化部署 |
| [docker-troubleshooting.md](references/docker-troubleshooting.md) | Docker 排障实战 |

## 使用场景

### 当你需要：
- 设计新策略 → 读 `first-principles.md` + `trading-strategies.md`
- 评估策略有效性 → 读 `overfitting-defense.md` + `backtest-realism.md`
- 优化仓位管理 → 读 `position-sizing.md` + `portfolio-management.md`
- 诊断系统问题 → 读 `debugging-and-optimization.md`
- 设计系统架构 → 读 `system-architecture.md` + `dev-practices.md`

## 核心原则速查

### 过拟合防御（最重要）
1. 样本外测试是唯一真理
2. 三重验证：PBO + CPCV + Deflated Sharpe Ratio
3. 决策规则必须冻结在实验前
4. trials 计数必须包含失败试验

### 因果与数据
5. 因果单向：只用 available_at <= bar.close 的数据
6. 集合分离：统计量估计集、策略构建集、测试集严格分离
7. 数据质量优先于模型复杂度

### 风控与仓位
8. 截断亏损，让利润奔跑
9. Kelly 仓位用分数 Kelly（1/4 ~ 1/2）
10. 分散化是分散风险因子，不是分散持仓数量

## 最佳实践参考

本技能库参考了以下顶级机构的实践：
- **Renaissance Technologies**：大奖章基金，年化收益 66%+
- **Two Sigma**：数据驱动的量化投资
- **Citadel**：多策略对冲基金
- **Millennium**：多管理人平台
- **Jane Street**：做市与统计套利
- **Jump Trading**：高频交易与做市

## 许可证

MIT License
