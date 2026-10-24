# TradingView 与 Pine Script 开发实践

> TradingView 是散户和小团队最常用的图表与策略原型平台，Pine Script 是其内置脚本语言。

## 目录

1. [TradingView 平台定位](#tradingview-平台定位)
2. [Pine Script 语言基础](#pine-script-语言基础)
3. [Pine Script 最佳实践](#pine-script-最佳实践)
4. [常见策略模板](#常见策略模板)
5. [Pine Script 与 Python 工作流](#pine-script-与-python-工作流)
6. [TradingView 的局限](#tradingview-的局限)

---

## TradingView 平台定位

### 第一性定位

**TradingView 不是实盘交易系统，是策略原型验证和图表分析平台。**

| 能力 | 适合 | 不适合 |
|------|------|--------|
| ✅ 图表分析、指标开发 | 快速可视化想法 | 大规模数据计算 |
| ✅ 策略原型验证 | 快速回测简单策略 | 严格的过拟合防御 |
| ✅ 预警信号推送 | 手动交易辅助 | 自动化实盘执行 |
| ✅ 社区分享 | 学习和参考 | 生产级系统 |

### 生态特点

- ** Pine Script**：内置脚本语言，专门为图表和指标设计
- ** 海量社区指标**：几十万用户分享的指标和策略
- ** 预警系统**：价格触发、指标触发，可以推送通知
- ** 经纪商对接**：部分经纪商支持 TradingView 直接下单（但功能有限）

---

## Pine Script 语言基础

### 语言特点

- **声明式**：不是命令式编程，是"定义指标怎么计算"
- ** 时序友好**：内置历史数据访问，不需要自己管理时间序列
- ** 内置函数丰富**：TA 库有几百个技术指标函数
- ** 迭代式**：Pine v5 是最新版本，功能越来越完善

### 基本结构

```pine
//@version=5
indicator("我的指标", overlay=true)

// 输入参数
length = input.int(14, title="周期")

// 计算
smaValue = ta.sma(close, length)

// 绘图
plot(smaValue, color=color.blue, title="SMA")
```

### 策略模板结构

```pine
//@version=5
strategy("我的策略", overlay=true, default_qty_type=strategy.percent_of_equity, default_qty_value=10)

// 输入
fastLength = input.int(10, title="快线周期")
slowLength = input.int(20, title="慢线周期")

// 计算
fastMA = ta.sma(close, fastLength)
slowMA = ta.sma(close, slowLength)

// 信号
goldenCross = ta.crossover(fastMA, slowMA)
deathCross = ta.crossunder(fastMA, slowMA)

// 交易
if goldenCross
    strategy.entry("Long", strategy.long)
if deathCross
    strategy.close("Long")
```

### 核心概念

| 概念 | 说明 |
|------|------|
| `ta.sma()` | 简单移动平均 |
| `ta.ema()` | 指数移动平均 |
| `ta.rsi()` | RSI 指标 |
| `ta.atr()` | 平均真实波动范围 |
| `ta.crossover()` | 上穿 |
| `ta.crossunder()` | 下穿 |
| `strategy.entry()` | 开仓 |
| `strategy.close()` | 平仓 |
| `strategy.position_size` | 当前持仓量 |

---

## Pine Script 最佳实践

### 1. 模块化思维

**不要把所有逻辑写在一行。** 分块组织：

```pine
//@version=5
strategy("我的策略", overlay=true)

// === 输入参数 ===
fastLen = input.int(10)
slowLen = input.int(20)

// === 指标计算 ===
calcFastMA(length) => ta.sma(close, length)
calcSlowMA(length) => ta.sma(close, length)

// === 信号生成 ===
getLongSignal() => ta.crossover(calcFastMA(fastLen), calcSlowMA(slowLen))
getShortSignal() => ta.crossunder(calcFastMA(fastLen), calcSlowMA(slowLen))

// === 执行 ===
if getLongSignal()
    strategy.entry("Long", strategy.long)
if getShortSignal()
    strategy.close("Long")
```

### 2. 避免过拟合（Pine 环境下）

Pine 回测很容易做出"完美曲线"，要警惕：

- **不要在图上调参数调到完美**：那是数据挖掘
- **样本外测试**：用前 70% 数据开发，后 30% 验证
- **参数越少越好**：3 个参数以内，超过 5 个就容易过拟合
- **不要相信 Sharpe**：Pine 的回测结果偏乐观，交易成本可能没算对

### 3. 风控要写进策略

Pine 策略一定要带止损和仓位管理：

```pine
// ATR 止损
stopLossDistance = ta.atr(14) * 2

// 跟踪止盈
trailingStop = ta.highest(close, 10) - ta.atr(14) * 2

// 在策略里设置
strategy.entry("Long", strategy.long)
strategy.exit("Exit", "Long", stop=close - stopLossDistance, trail_offset=trailingStop)
```

### 4. 使用 `barstate.islast` 优化性能

Pine 每次都重算全部历史数据。如果只在最后一根 K 线做计算：

```pine
if barstate.islast
    // 只在最后一根 bar 执行的重计算
```

### 5. 预警系统配合

Pine 的 alert 功能很强大：

- 价格触发：`alertcondition(condition, title="信号", message="做多")`
- 指标触发：当 RSI 超买超卖时推送
- 可以接 webhook 到自己的系统

---

## 常见策略模板

### 海龟交易法（Pine 版）

```pine
//@version=5
strategy("海龟交易法", overlay=true, default_qty_type=strategy.percent_of_equity, default_qty_value=10)

entryPeriod = input.int(20, title="入场周期")
exitPeriod = input.int(10, title="出场周期")
atrMult = input.float(2.0, title="ATR 止损倍数")

// 唐奇安通道
upper = ta.highest(high, entryPeriod)
lower = ta.lowest(low, entryPeriod)
exitUpper = ta.highest(high, exitPeriod)
exitLower = ta.lowest(low, exitPeriod)

// 信号
longSignal = ta.crossover(close, upper[1])
shortSignal = ta.crossunder(close, lower[1])

// 执行
if longSignal
    strategy.entry("Long", strategy.long)
if shortSignal
    strategy.close("Long")

// ATR 止损
stopLoss = close - ta.atr(14) * atrMult
strategy.exit("Stop", "Long", stop=stopLoss)
```

### 双均线交叉（Pine 版）

```pine
//@version=5
strategy("双均线策略", overlay=true)

fastLen = input.int(10)
slowLen = input.int(20)

fastMA = ta.ema(close, fastLen)
slowMA = ta.ema(close, slowLen)

plot(fastMA, color=color.green)
plot(slowMA, color=color.red)

if ta.crossover(fastMA, slowMA)
    strategy.entry("Long", strategy.long)
if ta.crossunder(fastMA, slowMA)
    strategy.close("Long")
```

### RSI 均值回归（Pine 版）

```pine
//@version=5
strategy("RSI 均值回归", overlay=false)

rsiLength = input.int(14)
oversold = input.int(30)
overbought = input.int(70)

rsiValue = ta.rsi(close, rsiLength)

plot(rsiValue, color=color.purple)
hline(oversold, color=color.green)
hline(overbought, color=color.red)

if ta.crossover(rsiValue, oversold)
    strategy.entry("Long", strategy.long)
if ta.crossunder(rsiValue, overbought)
    strategy.close("Long")
```

---

## Pine Script 与 Python 工作流

### 推荐工作流

```
想法 → Pine Script 原型验证 → Python 严格回测 → 实盘
         ↓                        ↓
    快速可视化              过拟合防御、交易成本
    简单回测                样本外验证、蒙特卡洛
```

### 为什么需要两步？

**Pine 的优势：**
- 开发速度快，几分钟就能写出一个指标
- 图表可视化好，直观看到信号位置
- 社区资源多，可以参考别人的代码

**Pine 的劣势：**
- 回测偏乐观，交易成本计算不准确
- 过拟合防御工具不足
- 无法做严格的统计检验（PBO、CPCV 等）
- 大数据量计算慢

**正确做法：**
1. 用 Pine 快速验证想法是否有道理
2. 有潜力的策略，再用 Python 严格回测
3. Python 验证通过，再考虑实盘

---

## TradingView 的局限

### 1. 不是实盘系统

TradingView 主要是图表和分析平台，不是交易执行系统。即使有经纪商对接，功能也很有限。

### 2. 回测偏乐观

Pine 的策略回测有几个问题：
- 假设你总能在收盘价成交（实际上有滑点）
- 交易成本可能算得不准
- 没有考虑流动性限制
- 没有做样本外验证的工具

### 3. 数据量限制

Pine 无法处理大规模历史数据（比如几十年的 tick 数据），适合中小规模的日线/小时线分析。

### 4. 过拟合容易

Pine 的可视化回测太容易调出"完美曲线"，新手很容易陷入数据挖掘。

### 5. 不适合机构级使用

- 无法自定义数据源
- 无法做复杂的组合管理
- 风控功能简单
- 没有审计追踪

---

## Pine Script 开发检查清单

每次写完策略，过一遍：

- [ ] 参数是不是太多了？（超过 5 个就要警惕过拟合）
- [ ] 有没有写止损和仓位管理？
- [ ] 回测结果是不是太完美了？（完美 = 可疑）
- [ ] 有没有做样本外验证？
- [ ] 交易成本是不是算进去了？
- [ ] 这个策略在震荡市和趋势市分别表现如何？
- [ ] 最大回撤是不是能承受？
- [ ] 要不要用 Python 再严格回测一遍？
