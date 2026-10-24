# ADR-001: 统一数据模型 - 以 source_version_id 为单一事实来源

## 状态
已采纳（2026-10-25）

## 背景
在实盘启动策略时遇到 `strategyV2.sourceRequired` 错误。排查发现：
- 策略表 `qd_strategies_trading` 有 `source_version_id` 字段
- `trading_config` JSON 里也有 `script_source_id` 和 `script_source_version_id`
- 两处需要手动同步，容易遗漏，导致启动失败

## 决策
选择 `source_version_id` 作为单一事实来源（Single Source of Truth）：

1. 策略表只存 `source_version_id` 外键
2. 用数据库触发器自动同步到 `trading_config`（为了查询性能）
3. API 层提供统一的加载接口，避免各处重复查询

## 理由
- **单一事实来源**：同一个信息只存一份，避免不一致
- **自动化**：用数据库触发器自动同步，不需要手动维护
- **向后兼容**：`trading_config` 里的字段保留，但是由触发器自动填充

## 后果
- ✅ 创建策略时只需要选择 source_version_id，不需要手动设置多个字段
- ✅ 不会再因为遗漏字段导致启动失败
- ✅ 数据一致性有保障
- ⚠️ 需要维护数据库触发器
- ⚠️ 旧的代码如果直接设置 trading_config 会被触发器覆盖（这是预期行为）
