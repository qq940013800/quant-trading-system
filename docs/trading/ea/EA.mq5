//+------------------------------------------------------------------+
//|                                                                   |
//|  EA.mq5  ——  AI/ML 增强量化交易系统 · MQL5 执行层 EA 骨架          |
//|                                                                   |
//|  设计依据（冻结，不得偏离）：                                       |
//|    docs/trading/AI_ML_SYSTEM_DESIGN.md 第⑥章 MQL5 EA 骨架结构；   |
//|    信号对接方式：文件 JSONL（备选 ZeroMQ，骨架不实现）。            |
//|                                                                   |
//|  铁律对齐（AGENTS.md）：                                            |
//|    硬规则4  止损单调；atr0/entryDist/sl/lots 由 Python 冻结下发，  |
//|             EA 不重算（R 倍数用入场冻结值）                         |
//|    硬规则5  intra-bar：信号/退出决策只在已收盘 bar 对应信号上触发； |
//|             OnTick 内不做任何阻塞与决策                              |
//|    硬规则6  时区：MT5 服务器偏移须与 Python --tz 一致，禁止写死     |
//|    硬规则7  OrderSend/PositionModify/PositionClosePartial 检查      |
//|             retcode 并重试（封装在 trade_utils.mqh）                |
//|    硬规则8  点值/手数/阈值一律走 SymbolInfo* 与 input/config         |
//|    硬规则9  无静默吞错：每个失败分支都带上下文日志                  |
//|                                                                   |
//|  编码说明：本文件含中文注释，保存与编译编码须为 UTF-8。             |
//|  边界：本文件为骨架设计示例（docs/trading/ea/），不入 mt5/；        |
//|        实盘代码后续经人工确认后放入 mt5/ 受人工管控。               |
//|  未验证：MT5 编译与实盘执行未在本环境验证。                         |
//+------------------------------------------------------------------+
#property copyright "AI/ML enhanced quant system — execution layer skeleton"
#property link      "docs/trading/AI_ML_SYSTEM_DESIGN.md"
#property version   "0.1"
#property strict

#include "trade_utils.mqh"

//==================================================================
// 输入参数（风控常量只允许来自 config / 部署输入；禁止写死在代码里）
//==================================================================
input group "=== 信号对接（文件 JSONL） ==="
input string  InSignalDir         = "Signals";              // 信号文件目录（相对 MT5 Files/ 沙盒或公共目录，见 SIGNAL_PROTOCOL.md）
input string  InSignalPrefix      = "xauusd_signal_";       // experiments/signals/xauusd_signal_YYYYMMDD.jsonl
input string  InAckPrefix         = "ack_";                 // 回执 experiments/signals/ack_YYYYMMDD.jsonl
input int     InTimerPeriodSec    = 5;                      // OnTimer 拉取周期：不堵 OnTick 队列（设计 5s）
input string  InStateFile        = "ea_last_seq.txt";       // 已处理单调序号持久化（跨重启幂等）

input group "=== 时区（硬规则6：须与 Python 端 --tz 一致） ==="
input double  InServerOffsetHours = 2.0;                    // 服务器时间 - UTC（小时），EET=2；DST 切换日须人工核对
input bool    InDstAuto           = false;                  // 经纪商 DST 自动切换（人工核对后开启；禁止写死 UTC+2/+3）

input group "=== 交易执行规格 ==="
input string  InSymbol           = "XAUUSD";                // 交易品种
input int     InMagic            = 20261024;                // magic number（EA 标识；来自部署 config，须唯一）
input int     InSlippagePoints   = 30;                      // 允许滑点（点；来自 config，禁止硬编码到交易逻辑外）

input group "=== 新闻窗口冻结（设计第⑥章第5条） ==="
input string  InNewsCsv          = "news_events.csv";       // 事件 UTC 时间列表（每行一个时刻，UTC 语义）
input int     InNewsWindowMin     = 15;                     // 冻结窗口 ±分钟（设计默认 ±15min，可配）

input group "=== 日权益熔断（阈值来自 config/CLEAN 分布校准，禁止硬编码） ==="
input double  InDailyMaxDDPct     = 0.03;                   // 当日权益熔断线（参照 3% 档；实际值由分布校准后人工填入）

//==================================================================
// 全局运行态（不落 config；仅本进程内存 + 序号持久化文件）
//==================================================================
SymbolSpec      g_spec;                 // 合约规格（OnInit 经 SymbolInfo* 填充）
CircuitState    g_circuit;              // 熔断三态机
datetime        g_news_events[];        // 新闻事件 UTC 列表
long            g_last_seq = 0;        // 已处理信号单调序号（幂等游标）
bool            g_ready     = false;    // 初始化完成标志

//==================================================================
// 信号消息结构（对应 Python 侧 Signal/Decision 冻结下发字段）
//==================================================================
struct SignalMsg
  {
   long     seq;                // 单调递增序号（Decision.decision_id）
   string   symbol;             // 品种
   string   signal_id;          // 幂等键：f"{symbol}_{bar_ts_utc}_{expert}_{dir}"
   int      direction;          // +1 多 / -1 空
   double   atr0;               // 入场冻结 ATR（EA 只读，不重算 —— 硬规则4）
   double   entry_dist;         // 入场到止损距离（入场冻结）
   double   sl_price;           // 冻结止损价
   double   tp_price;           // 止盈价；<0 表示 null（不下止盈）
   double   lots;               // Python sizing 冻结手数
   long     ts_utc;             // 触发 bar 收盘 UTC 时刻
   string   rule_version;       // decision_rule_version（冻结规则版本）
   bool     valid;              // 解析是否成功
  };

//+------------------------------------------------------------------+
//| 信号行解析（JSONL → SignalMsg；非法行 valid=false 并带日志）       |
//+------------------------------------------------------------------+
SignalMsg ParseSignalLine(const string line)
  {
   SignalMsg s;
   ZeroMemory(s);
   s.tp_price = -1.0;
   s.valid = false;

   double v_seq  = JsonExtractNumber(line, "seq");
   double v_dir  = JsonExtractNumber(line, "direction");
   double v_sl   = JsonExtractNumber(line, "sl_price");
   double v_lots = JsonExtractNumber(line, "lots");

   if(MathIsNaN(v_seq)  || MathIsNaN(v_dir) ||
      MathIsNaN(v_sl)   || MathIsNaN(v_lots))
     {
      PrintFormat("[ParseSignal] 信号行字段缺失，跳过。line=\"%.200s\"", line);
      return(s);
     }

   s.seq         = (long)v_seq;
   s.symbol      = JsonExtractString(line, "symbol");
   s.signal_id   = JsonExtractString(line, "signal_id");
   s.direction   = (int)v_dir;
   s.atr0        = JsonExtractNumber(line, "atr0");
   s.entry_dist  = JsonExtractNumber(line, "entry_dist");
   s.sl_price    = v_sl;
   s.tp_price    = JsonExtractNumber(line, "tp_price");   // 允许 NaN → 按下止盈处理
   s.lots        = v_lots;
   s.ts_utc      = JsonExtractLong(line, "ts_utc");
   s.rule_version= JsonExtractString(line, "decision_rule_version");

   if(s.signal_id=="" || s.seq<=0 || (s.direction!=1 && s.direction!=-1))
     {
      PrintFormat("[ParseSignal] 信号行语义非法 seq=%I64u signal_id=\"%s\" dir=%d —— 跳过",
                  s.seq, s.signal_id, s.direction);
      return(s);
     }
   s.valid = true;
   return(s);
  }

//+------------------------------------------------------------------+
//| 回执写回：ack_YYYYMMDD.jsonl（与 SIGNAL_PROTOCOL.md 一致）         |
//+------------------------------------------------------------------+
void AppendAck(const string signal_id, const int retcode, const double fill_price,
               const string status)
  {
   MqlDateTime t;
   TimeToStruct(TimeGMT(), t);
   string fname = InSignalDir + "/" + InAckPrefix +
                  StringFormat("%04d%02d%02d", t.year, t.mon, t.day) + ".jsonl";

   int h = FileOpen(fname, FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_SHARE_READ, 0, CP_UTF8);
   if(h==INVALID_HANDLE)
     {
      // 回执写失败 = 可审计性破口：必须显式告警，禁止静默（硬规则/不变量2）
      PrintFormat("[AppendAck] 错误：回执文件 %s 打开失败 err=%d signal_id=%s retcode=%d —— 需人工对账！",
                  fname, GetLastError(), signal_id, retcode);
      return;
     }
   FileSeek(h, 0, SEEK_END);
   string rec = StringFormat(
      "{\"signal_id\":\"%s\",\"retcode\":%d,\"retcode_name\":\"%s\",\"fill_price\":%g,"
      "\"fill_time_server\":%I64u,\"status\":\"%s\"}\n",
      signal_id, retcode, RetcodeToString(retcode), fill_price, (long)TimeCurrent(), status);
   FileWriteString(h, rec);
   FileClose(h);
  }

//+------------------------------------------------------------------+
//| 已处理序号持久化（幂等游标；重启后防重复下单）                      |
//+------------------------------------------------------------------+
void LoadLastSeq()
  {
   int h = FileOpen(InStateFile, FILE_READ|FILE_TXT|FILE_ANSI);
   if(h==INVALID_HANDLE) { g_last_seq = 0; return; }
   string s = FileReadString(h, 64);
   FileClose(h);
   g_last_seq = (long)StringToInteger(s);
   PrintFormat("[State] 已处理序号游标 g_last_seq=%I64u", g_last_seq);
  }

void SaveLastSeq()
  {
   int h = FileOpen(InStateFile, FILE_WRITE|FILE_TXT|FILE_ANSI);
   if(h==INVALID_HANDLE)
     {
      PrintFormat("[State] 错误：游标文件 %s 写失败 err=%d —— 重启后可能重复下单，需人工检查",
                  InStateFile, GetLastError());
      return;
     }
   FileWriteString(h, (string)g_last_seq);
   FileClose(h);
  }

//+------------------------------------------------------------------+
//| 执行单条已接受信号：建市价单 + 冻结 SL/TP；EA 不重算任何风控量     |
//+------------------------------------------------------------------+
void ExecuteSignal(const SignalMsg s)
  {
   // —— 品种核对 ——
   if(s.symbol != InSymbol && s.symbol != "")
     {
      PrintFormat("[Exec] 品种不符 signal=%s got=%s expect=%s —— 拒绝并回执",
                  s.signal_id, s.symbol, InSymbol);
      AppendAck(s.signal_id, 0, 0.0, "REJECTED_SYMBOL");
      return;
     }

   // —— 新闻窗口冻结（设计第⑥章第5条）——
   if(IsInNewsWindow(TimeGMT(), g_news_events, InNewsWindowMin))
     {
      PrintFormat("[Exec] 新闻窗口内（±%d min）拒绝新开仓 signal=%s", InNewsWindowMin, s.signal_id);
      AppendAck(s.signal_id, 0, 0.0, "REJECTED_NEWS_WINDOW");
      return;
     }

   // —— 熔断态：禁止新开仓 ——
   if(g_circuit.state != CIRCUIT_NORMAL)
     {
      PrintFormat("[Exec] 熔断态=%d 拒绝新开仓 signal=%s", (int)g_circuit.state, s.signal_id);
      AppendAck(s.signal_id, 0, 0.0, "REJECTED_CIRCUIT_BREAKER");
      return;
     }

   // —— 手数规范化（只取整/夹逼，不重算风险 —— 硬规则4/8）——
   double lots = NormalizeLots(s.lots, g_spec);
   if(lots <= 0.0)
     {
      AppendAck(s.signal_id, 0, 0.0, "REJECTED_LOTS");
      return;
     }

   bool   is_long = (s.direction==1);
   double price   = is_long ? SymbolInfoDouble(InSymbol, SYMBOL_ASK)
                             : SymbolInfoDouble(InSymbol, SYMBOL_BID);
   double sl      = NormalizeDouble(s.sl_price, g_spec.digits);
   double tp      = (s.tp_price >= 0.0) ? NormalizeDouble(s.tp_price, g_spec.digits) : 0.0;

   // —— 经纪商最小止损距离校验（stops_level 动态读取；经纪商差异未验证）——
   double min_dist = g_spec.stops_level * g_spec.point;
   if(MathAbs(price - sl) < min_dist)
     {
      PrintFormat("[Exec] 拒绝：SL 距市价 %g < stops_level 最小距离 %g（signal=%s）—— 回执 REJECTED_STOPS_LEVEL",
                  MathAbs(price-sl), min_dist, s.signal_id);
      AppendAck(s.signal_id, 0, price, "REJECTED_STOPS_LEVEL");
      return;
     }

   MqlTradeRequest req;
   ZeroMemory(req);
   req.action       = TRADE_ACTION_DEAL;
   req.symbol       = InSymbol;
   req.volume       = lots;
   req.type         = is_long ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   req.price        = price;
   req.sl           = sl;
   req.tp           = tp;
   req.deviation    = InSlippagePoints;
   req.magic        = InMagic;
   req.type_filling = (ENUM_ORDER_FILLING_TYPE)g_spec.filling_mode;
   req.comment      = StringSubstr(s.signal_id, 0, 31);   // MQL5 comment 长度限制

   MqlTradeResult res;
   ZeroMemory(res);
   bool ok = SafeOrderSend(req, res, 3);

   if(ok)
      AppendAck(s.signal_id, res.retcode, res.price,
                (res.retcode==TRADE_RETCODE_PLACED ? "PLACED" : "FILLED"));
   else
      AppendAck(s.signal_id, res.retcode, res.price, "ERROR");
  }

//+------------------------------------------------------------------+
//| OnTimer：拉取新增信号（设计：每 5s，不堵 OnTick 队列）             |
//+------------------------------------------------------------------+
void ScanNewSignals()
  {
   MqlDateTime t;
   TimeToStruct(TimeGMT(), t);
   string fname = InSignalDir + "/" + InSignalPrefix +
                  StringFormat("%04d%02d%02d", t.year, t.mon, t.day) + ".jsonl";

   int h = FileOpen(fname, FILE_READ|FILE_TXT|FILE_ANSI, 0, CP_UTF8);
   if(h==INVALID_HANDLE)
     {
      // 文件尚未生成是正常态（盘前）：仅 debug 级打印，不告警
      return;
     }

   long processed_now = g_last_seq;

   while(!FileIsEnding(h))
     {
      string line = FileReadString(h, 4096);
      line = StringTrimLeft(line);
      line = StringTrimRight(line);
      if(StringLen(line)==0) continue;

      SignalMsg s = ParseSignalLine(line);
      if(!s.valid) continue;

      // —— 单调序号 + 幂等：已处理序号直接跳过（防重复下单）——
      if(s.seq <= g_last_seq) continue;

      PrintFormat("[Signal] 新信号 seq=%I64u id=%s dir=%d sl=%g lots=%g rule=%s",
                  s.seq, s.signal_id, s.direction, s.sl_price, s.lots, s.rule_version);

      ExecuteSignal(s);
      processed_now = s.seq;   // 无论成功/拒绝都推进游标（拒绝已落 ACK，不可重复投递）
     }
   FileClose(h);

   if(processed_now != g_last_seq)
     {
      g_last_seq = processed_now;
      SaveLastSeq();
     }
  }

//+------------------------------------------------------------------+
//| 事件处理函数                                                      |
//+------------------------------------------------------------------+
int OnInit()
  {
   PrintFormat("=== EA 骨架 OnInit（v%s，骨架未编译验证）===", MQLInfoString(MQL_PROGRAM_VERSION));

   // 1. 合约规格（SymbolInfo*，禁硬编码 —— 硬规则8）
   ReadSymbolSpecs(InSymbol, g_spec);
   if(!g_spec.valid)
     {
      Print("[OnInit] 合约规格读取失败 —— 终止初始化（错误已在上方打印，上下文完整）");
      return(INIT_FAILED);
     }

   // 2. 时区一致性 sanity check（硬规则6：EA 偏移须与 Python --tz 一致）
   long measured_offset_h = (long)MathRound((TimeCurrent() - TimeGMT()) / 3600.0);
   PrintFormat("[OnInit] 配置服务器偏移=%.1fh；实测(TimeCurrent-TimeGMT)=%ldh —— DST 切换日人工核对",
               InServerOffsetHours, measured_offset_h);
   if(MathAbs((double)measured_offset_h - InServerOffsetHours) > 0.5)
      Print("[OnInit] 警告：实测服务器偏移与 input 配置不一致（可能 DST 日）——信号时间对齐可能错位，需人工确认");

   // 3. 新闻日历
   LoadNewsEvents(InNewsCsv, g_news_events);

   // 4. 熔断态初始化
   g_circuit.state = CIRCUIT_NORMAL;
   g_circuit.day_start_server = 0;
   g_circuit.day_start_equity = AccountInfoDouble(ACCOUNT_BALANCE);

   // 5. 幂等游标
   LoadLastSeq();

   // 6. 定时器：信号拉取走 OnTimer，OnTick 保持轻量（G01 事件队列语义）
   EventSetTimer(InTimerPeriodSec);

   g_ready = true;
   Print("[OnInit] 完成。信号拉取周期=", InTimerPeriodSec, "s；等待 ", InSignalPrefix, "*.jsonl");
   return(INIT_SUCCEEDED);
  }

void OnDeinit(const int reason)
  {
   EventKillTimer();
   SaveLastSeq();
   PrintFormat("=== EA 骨架 OnDeinit reason=%d，游标 g_last_seq=%I64u 已保存 ===", reason, g_last_seq);
  }

void OnTick()
  {
   // 设计：OnTick 内不做任何阻塞工作（MQL5 事件队列对积压 NewTick 直接丢弃 —— G01）。
   // 本 EA 不在 OnTick 决策；信号拉取与风控检查一律走 OnTimer。
   // 硬规则5：信号对应已收盘 bar（ts_utc = bar.close），EA 收到信号才行动，不在 intra-bar 下单。
  }

void OnTimer()
  {
   if(!g_ready) return;

   // 1. 熔断三态机（新服务器日自动复位；触发后禁止新开仓）
   CircuitOnTimerUpdate(g_circuit, InDailyMaxDDPct);

   // 2. 拉取新增信号（单调序号 + signal_id 幂等）
   ScanNewSignals();

   // 3. 止损单调管理钩子（骨架位）：
   //    实盘版在此遍历本 EA 持仓，按 Python 侧下发的移动止损信号调用
   //    MonotonicModifySL()；本骨架不内置追踪逻辑（方向骨架在 Python 研究层）。
  }

void OnTradeTransaction(const MqlTradeTransaction trans,
                        const MqlTradeRequest        request,
                        const MqlTradeResult         result)
  {
   // 异步确认通道（硬规则7 对账用）：DEAL_ADD 到达 = 订单真实成交。
   // 骨架：记录上下文；实盘版据此补全 ACK 的 fill_price/deal 对账字段。
   if(trans.type==TRADE_TRANSACTION_DEAL_ADD)
     {
      PrintFormat("[OnTradeTransaction] DEAL_ADD deal=%I64u order=%I64u retcode=%s(%d) "
                  "—— 异步成交确认（对账用）",
                  trans.deal, trans.order, RetcodeToString(result.retcode), result.retcode);
     }
  }
//+------------------------------------------------------------------+
