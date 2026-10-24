---
description: "MQL5 层规范：决策时机、交易调用、状态与配置、与 Python 对齐。Use when editing EA .mq5 or .mqh files under mt5/."
applyTo: "mt5/**/*.mq5,mt5/**/*.mqh"
---
# MQL5 层规范

## 决策时机
- 所有信号/退出决策必须在 IsNewBar 守卫内，仅对已收盘 bar 执行一次
- 禁止在 tick 级做形态判定与区域重算

## 交易调用
- 每个交易函数检查返回值；失败记录 GetLastError 并重试（上限 3 次，指数退避）
- PositionClosePartial 失败必须有回退分支（净额账户不支持时降级并写 journal）
- 手数/点值/最小步长一律来自 SymbolInfoDouble，禁止字面量

## 状态与配置
- 阈值来自 include 的 config 头文件或外部 csv，禁止散落在逻辑中
- 全局状态变更必须写 journal（含 ts、旧值、新值、触发原因）
- 服务器时区在 OnInit 打印并写入文件，供 Python 端核对

## 与 Python 对齐
- ExitEngine / Filter / GapGuard 的语义必须与 core 侧镜像实现一致
- 任何一侧逻辑变更，必须同步改另一侧并更新跨语言一致性测试
