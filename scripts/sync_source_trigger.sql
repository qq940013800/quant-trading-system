-- ============================================
-- QuantDinger 策略源代码自动同步触发器
-- 基于第一性原理和全球最佳实践
-- ============================================

-- 注意：执行前请备份数据库！

-- 1. 创建触发器函数
CREATE OR REPLACE FUNCTION sync_source_version_to_config()
RETURNS TRIGGER AS $$
DECLARE
    v_source_id INT;
BEGIN
    -- 如果设置了 source_version_id，自动同步到 trading_config
    IF NEW.source_version_id IS NOT NULL AND NEW.source_version_id > 0 THEN
        -- 从 source_versions 表反查 source_id
        SELECT source_id INTO v_source_id 
        FROM qd_script_source_versions 
        WHERE id = NEW.source_version_id;
        
        IF v_source_id IS NOT NULL THEN
            -- 确保 trading_config 是 JSONB
            IF NEW.trading_config IS NULL OR NEW.trading_config = '{}'::jsonb THEN
                NEW.trading_config = '{}'::jsonb;
            END IF;
            
            -- 同步 script_source_id
            NEW.trading_config = jsonb_set(
                NEW.trading_config,
                '{script_source_id}',
                to_jsonb(v_source_id)
            );
            
            -- 同步 script_source_version_id
            NEW.trading_config = jsonb_set(
                NEW.trading_config,
                '{script_source_version_id}',
                to_jsonb(NEW.source_version_id)
            );
        END IF;
    END IF;
    
    -- 反向同步：如果 trading_config 有字段，但 source_version_id 没有，也同步过去
    IF (NEW.source_version_id IS NULL OR NEW.source_version_id = 0) 
       AND NEW.trading_config ? 'script_source_version_id' THEN
        NEW.source_version_id = (NEW.trading_config->>'script_source_version_id')::INT;
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 2. 删除旧触发器（如果存在）
DROP TRIGGER IF EXISTS trigger_sync_source_version ON qd_strategies_trading;

-- 3. 创建触发器
CREATE TRIGGER trigger_sync_source_version
BEFORE INSERT OR UPDATE OF source_version_id, trading_config
ON qd_strategies_trading
FOR EACH ROW
EXECUTE FUNCTION sync_source_version_to_config();

-- 4. 验证触发器
-- 测试：更新一个策略的 source_version_id，看看 trading_config 是否自动同步
UPDATE qd_strategies_trading 
SET source_version_id = 15 
WHERE id = 1;

-- 查看结果
SELECT id, strategy_name, source_version_id, trading_config FROM qd_strategies_trading WHERE id = 1;

-- 预期结果：trading_config 应该自动包含 script_source_id=8 和 script_source_version_id=15
