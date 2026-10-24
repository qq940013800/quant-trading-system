# QuantDinger 策略源代码加载器优化补丁

> 基于第一性原理和全球最佳实践
> 不修改核心代码，通过外部层实现优化

## 一、优化目标

1. ✅ 改进错误信息，明确指出缺少哪个字段
2. ✅ 统一数据模型，以 source_version_id 为单一事实来源
3. ✅ 自动同步冗余字段
4. ✅ 向后兼容，不破坏现有功能

## 二、错误信息改进

### 原错误（模糊）
```
strategyV2.sourceRequired
```

### 新错误（清晰）
```
[strategyV2.sourceRequired] 策略缺少源代码关联信息，无法启动

缺少的字段：
  - qd_strategies_trading.source_version_id (推荐)
  - trading_config.script_source_id
  - trading_config.script_source_version_id

修复建议：
  1. 推荐方式：使用正确的创建接口，自动关联源代码
  2. 临时方式：手动设置上述字段，确保 source_id 和 version_id 对应
```

## 三、统一数据模型

### 数据模型原则

```
单一事实来源：
qd_strategies_trading.source_version_id
    ↓ 自动反查
qd_script_source_versions.source_id
    ↓ 自动同步（向后兼容）
trading_config.script_source_id
trading_config.script_source_version_id
```

### 优先级顺序

1. **第一优先级**：`source_version_id` 字段（新方式，推荐）
2. **第二优先级**：`trading_config` 里的冗余字段（旧方式，兼容）
3. **都没有**：抛出明确错误

## 四、实现方案

### 方案A：数据库层自动同步（推荐）

创建数据库触发器，自动从 source_version_id 同步到 trading_config：

```sql
-- 触发器函数
CREATE OR REPLACE FUNCTION sync_source_version_to_config()
RETURNS TRIGGER AS $$
BEGIN
    -- 如果设置了 source_version_id，自动同步到 trading_config
    IF NEW.source_version_id IS NOT NULL AND NEW.source_version_id > 0 THEN
        -- 从 source_versions 表反查 source_id
        DECLARE v_source_id INT;
        SELECT source_id INTO v_source_id 
        FROM qd_script_source_versions 
        WHERE id = NEW.source_version_id;
        
        IF v_source_id IS NOT NULL THEN
            -- 确保 trading_config 是 JSONB
            IF NEW.trading_config IS NULL THEN
                NEW.trading_config = '{}'::jsonb;
            END IF;
            
            -- 同步字段
            NEW.trading_config = jsonb_set(
                NEW.trading_config,
                '{script_source_id}',
                to_jsonb(v_source_id)
            );
            NEW.trading_config = jsonb_set(
                NEW.trading_config,
                '{script_source_version_id}',
                to_jsonb(NEW.source_version_id)
            );
        END IF;
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 创建触发器
CREATE TRIGGER trigger_sync_source_version
BEFORE INSERT OR UPDATE OF source_version_id
ON qd_strategies_trading
FOR EACH ROW
EXECUTE FUNCTION sync_source_version_to_config();
```

### 方案B：应用层中间件

创建一个策略加载中间件，在调用 trading_executor 之前自动处理：

```python
class StrategySourceMiddleware:
    """
    策略源代码加载中间件
    在执行前自动处理 source 关联问题
    """
    
    def process_strategy(self, strategy: dict) -> dict:
        """处理策略数据，确保 source 关联正确"""
        
        # 1. 检查是否有 source_version_id
        source_version_id = int(strategy.get("source_version_id") or 0)
        
        if source_version_id > 0:
            # 2. 反查 source_id
            source = self._get_source_version(source_version_id)
            if source:
                source_id = int(source.get("source_id") or 0)
                
                # 3. 自动同步到 trading_config
                trading_config = strategy.get("trading_config") or {}
                trading_config["script_source_id"] = source_id
                trading_config["script_source_version_id"] = source_version_id
                strategy["trading_config"] = trading_config
                
                return strategy
        
        # 4. 检查 trading_config 里的字段
        trading_config = strategy.get("trading_config") or {}
        source_id = int(trading_config.get("script_source_id") or 0)
        config_version_id = int(trading_config.get("script_source_version_id") or 0)
        
        if source_id > 0 and config_version_id > 0:
            # 5. 反向同步到 source_version_id 字段
            strategy["source_version_id"] = config_version_id
            return strategy
        
        # 6. 都没有，抛出明确错误
        raise StrategySourceError(
            "策略缺少源代码关联信息，无法启动",
            missing_fields=[
                "qd_strategies_trading.source_version_id",
                "trading_config.script_source_id",
                "trading_config.script_source_version_id"
            ],
            fix_hint="创建策略时请通过正确的接口自动关联源代码"
        )
    
    def _get_source_version(self, version_id: int) -> dict:
        """从数据库获取 source_version"""
        # 实现省略...
        pass


class StrategySourceError(Exception):
    """策略源代码关联错误"""
    def __init__(self, message: str, missing_fields: list = None, fix_hint: str = None):
        self.message = message
        self.missing_fields = missing_fields or []
        self.fix_hint = fix_hint
        super().__init__(self.format_error())
    
    def format_error(self) -> str:
        lines = [f"[strategyV2.sourceRequired] {self.message}"]
        if self.missing_fields:
            lines.append("\n缺少的字段：")
            for f in self.missing_fields:
                lines.append(f"  - {f}")
        if self.fix_hint:
            lines.append(f"\n修复建议：{self.fix_hint}")
        return "\n".join(lines)
```

## 五、创建流程优化

### 原流程（繁琐）
```
1. 创建 source
2. 创建 version
3. 创建 strategy（手动设置 source_version_id）
4. 手动设置 trading_config.script_source_id
5. 手动设置 trading_config.script_source_version_id
```

### 新流程（一键）
```
1. 调用 create_strategy_with_source(source_id=8, name="我的策略", ...)
2. 自动完成：
   - 验证 source 存在
   - 获取最新 version
   - 创建 strategy 记录
   - 自动设置 source_version_id
   - 自动同步 trading_config
```

## 六、实施步骤

### Phase 1: 错误信息改进（已完成）
- ✅ 设计新的错误格式
- ✅ 明确指出缺少的字段
- ✅ 提供修复建议

### Phase 2: 数据库触发器（推荐）
- [ ] 创建同步触发器函数
- [ ] 创建触发器
- [ ] 测试自动同步功能

### Phase 3: 统一创建接口
- [ ] 创建 create_strategy_with_source() 函数
- [ ] 前端集成
- [ ] 测试一键创建流程

### Phase 4: 数据迁移
- [ ] 迁移现有数据
- [ ] 验证一致性
- [ ] 长期：移除冗余字段

## 七、测试验证

### 测试用例

1. **正常创建策略**
   - 输入：source_id=8
   - 预期：自动创建 version，自动设置所有字段

2. **手动创建策略**
   - 输入：直接插入数据库，只设置 source_version_id
   - 预期：自动同步 trading_config

3. **缺少字段**
   - 输入：没有任何 source 关联
   - 预期：抛出清晰的错误信息

## 八、总结

### 核心改进

| 改进项 | 之前 | 之后 |
|--------|------|------|
| 数据一致性 | 需要手动同步3个字段 | 自动同步，单一事实来源 |
| 错误信息 | 模糊的错误代码 | 清晰的字段名+修复建议 |
| 创建流程 | 5步手动操作 | 1步自动完成 |
| 向后兼容 | 不兼容 | 自动同步，优雅降级 |

### 预期收益

1. **减少 bug**：不再因为字段不同步导致的错误
2. **提升开发效率**：创建策略更简单
3. **更好的用户体验**：错误信息清晰，修复路径明确
4. **更好的可维护性**：统一数据模型，易于理解
