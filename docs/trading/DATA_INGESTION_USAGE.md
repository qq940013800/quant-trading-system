# 数据管线使用说明（core/data + scripts/ingest_xauusd.py）

> 对应冻结设计：AI_ML_SYSTEM_DESIGN.md §3、DATA_INGESTION.md。本文只讲怎么用，不重复规格。

## 1. 一条命令完成导入

```powershell
# 从 D:\Trader 目录运行
.venv\Scripts\python.exe scripts\ingest_xauusd.py `
  --data data\raw\mt5\XAUUSD_M5.csv `
  --tz EET `
  --out  data\clean\XAUUSD_M5.csv `
  --splits data\splits\split_dates.yaml
```

退出码：0=成功；1=校验失败/数据损坏（如时间戳非单调）；2=参数错误。

## 2. 参数速查

| 参数 | 说明 |
|---|---|
| `--data` | MT5 历史中心导出的 CSV（列：DATE TIME OPEN HIGH LOW CLOSE TICKVOL VOL SPREAD） |
| `--out` | 归一化输出 CSV（列式列名见下；parquet 需 pyarrow，当前基线环境未装） |
| `--tz EET` | 经纪商 profile：EET（冬季 UTC+2 / 夏季 UTC+3，跟随美国 DST）；GMT0=无 DST 恒定 0 |
| `--offset-table broker.json` | 经纪商校准过的 DST 切换表（优先级高于 `--tz`） |
| `--tz-offset-hours 2.0` | 无 DST 券商的恒定偏移（兜底；禁止写死在代码里） |
| `--splits` | CLEAN/KNOWN 区间配置；HELD_OUT 区间内的 bar 直接丢弃，永不返回 |
| `--bar-minutes / --outlier-window / --outlier-mult` | 网格步长与异常值判定参数（调用方传入，非模块内字面量） |

输出 CSV 列：`ts_utc, ts_server, server_offset_hours, open, high, low, close, tick_volume, spread_points`。

## 3. OffsetTable JSON 格式（--offset-table）

```json
{
  "profile": "EET-MY-BROKER",
  "winter_offset_hours": 2.0,
  "summer_offset_hours": 3.0,
  "transitions": {
    "2024": ["2024-03-10", "2024-11-03"],
    "2025": ["2025-03-09", "2025-11-02"]
  }
}
```

Python 端这张表必须与 MQL5 EA 的 `InServerOffset` 配置指向同一份（硬规则 6）。

## 4. split_dates.yaml 格式（--splits）

```yaml
clean:    ["2023-01-01", "2024-01-01"]   # 估计 ATR/vol/Hurst、标定阈值
known:    ["2024-01-01", "2024-06-01"]   # 构建供需区结构
held_out: ["2025-01-01", "2025-06-01"]  # 静默集：区间内 bar 丢弃；
                                         # 文件中若出现 held_out_data_path 类键，直接 raise
```

区间为左闭右开。`split_dataset()` 返回 `{"CLEAN": [...], "KNOWN": [...], "HELD_OUT": []}`——`HELD_OUT` 恒为空列表。

## 5. Python API 速览

```python
from core.data import (load_bars, validate_bars, split_dataset,
                       make_synthetic_bars, OffsetTable, assert_as_of,
                       LookAheadError, ValidationError)

bars = load_bars("data/raw/mt5/XAUUSD_M5.csv", "XAUUSD", 2.0,
                 offset_table=OffsetTable.eet_default())
report = validate_bars(bars)          # gaps/isolated/outliers/dst_days
parts  = split_dataset(bars, "data/splits/split_dates.yaml")

# 因果守卫：任何 history 含 ts_utc > as_of 的 bar 即抛 LookAheadError
assert_as_of(history, as_of)
```

合成数据（pipeline 无泄漏自检）：`make_synthetic_bars(seed=42, n=1000, kind="martingale"|"trend_regime")`，同种子逐字节复现；在 martingale 上盈利 = 前视泄漏。

## 6. 校验行为速查

| 规则 | 处理 |
|---|---|
| ts_utc 非严格递增 | `ValidationError`（硬失败，不自动修） |
| OHLC 不一致 / close≤0 / spread<0 | 隔离进 `ValidationReport.isolated`（保留记录，不删 bar） |
| 缺 bar | 生成 `Gap` 清单（起止 UTC + 缺失根数），**绝不回填**；走 `core/gap_normalizer.py` |
| 单 bar 异动 > N×滚动 std | 标记 `Outlier`，回测可选过滤 |
| 重复服务器时间戳 | 保留首条，计数日志 |

## 7. 测试

```powershell
.venv\Scripts\python.exe -m pytest tests\test_data_loader.py tests\test_data_timezone.py tests\test_data_synthetic.py -q
```
