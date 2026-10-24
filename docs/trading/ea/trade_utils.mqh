//+------------------------------------------------------------------+
//|                                              trade_utils.mqh     |
//|  AI/ML 增强量化交易系统 — MQL5 执行层交易工具头文件（骨架）        |
//|                                                                  |
//|  设计依据（冻结，不得偏离）：                                     |
//|    docs/trading/AI_ML_SYSTEM_DESIGN.md 第⑥章「trade_utils.mqh    |
//|    必须实现的封装」1~6 条；研究分片 G01/G05 最佳实践。            |
//|                                                                  |
//|  铁律对齐（AGENTS.md）：                                          |
//|    硬规则4 止损单调 / atr0 入场冻结                                |
//|    硬规则7 OrderSend/PositionModify/PositionClosePartial 必须     |
//|            检查返回值（retcode）并重试                             |
//|    硬规则8 禁止硬编码点值/手数/阈值 —— 一律走 SymbolInfo* 与 config|
//|    硬规则9 禁止静默吞错 —— 所有失败路径必须带上下文日志            |
//|                                                                  |
//|  编码说明：本文件含中文注释，保存与编译编码须为 UTF-8。            |
//|  边界：本目录只放骨架设计与示例代码，不入 mt5/；                  |
//|        实盘代码后续经人工确认后放入 mt5/ 受人工管控。              |
//+------------------------------------------------------------------+
#property strict

#ifndef TRADE_UTILS_MQH
#define TRADE_UTILS_MQH

//==================================================================
// 0. 合约规格结构（由 ReadSymbolSpecs 经 SymbolInfo* 动态填充；
//    任何点值/手数/步长/合约规模禁止硬编码 —— 硬规则8）
//==================================================================
struct SymbolSpec
  {
   string             symbol;          // 交易品种（如 "XAUUSD"）
   int                digits;           // 价格小数位
   double             point;            // 1 个 point 的价格单位
   double             tick_value;      // SYMBOL_TRADE_TICK_VALUE（每手每 tick 的计价货币价值）
   double             tick_size;        // SYMBOL_TRADE_TICK_SIZE（最小价格变动）
   double             contract_size;    // SYMBOL_CONTRACT_SIZE（合约规模）
   double             lot_min;          // 最小手数
   double             lot_step;         // 手数步长
   double             lot_max;          // 最大手数
   long               stops_level;      // SYMBOL_TRADE_STOPS_LEVEL（止损最小距离，单位：point）
   long               filling_mode;     // SYMBOL_FILLING_MODE（成交模式，须用经纪商给定值）
   bool               valid;            // 规格是否成功读取（false 时一切交易动作必须拒绝）
  };

//+------------------------------------------------------------------+
//| 读取合约规格（硬规则8：全部走 SymbolInfo*，禁止硬编码）            |
//+------------------------------------------------------------------+
void ReadSymbolSpecs(const string symbol, SymbolSpec &spec)
  {
   spec.symbol       = symbol;
   spec.valid        = false;

   if(!SymbolSelect(symbol, true))
     {
      PrintFormat("[ReadSymbolSpecs] 错误：无法选择品种 %s（上下文：OnInit）——放弃初始化", symbol);
      return;
     }

   spec.digits       = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
   spec.point        = SymbolInfoDouble(symbol, SYMBOL_POINT);
   spec.tick_value   = SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_VALUE);
   spec.tick_size    = SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_SIZE);
   spec.contract_size= SymbolInfoDouble(symbol, SYMBOL_CONTRACT_SIZE);
   spec.lot_min      = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MIN);
   spec.lot_step     = SymbolInfoDouble(symbol, SYMBOL_VOLUME_STEP);
   spec.lot_max      = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MAX);
   spec.stops_level  = SymbolInfoInteger(symbol, SYMBOL_TRADE_STOPS_LEVEL);
   spec.filling_mode = SymbolInfoInteger(symbol, SYMBOL_FILLING_MODE);

   if(spec.point <= 0.0 || spec.lot_step <= 0.0)
     {
      PrintFormat("[ReadSymbolSpecs] 错误：%s 规格异常 point=%g lot_step=%g —— 经纪商差异未验证，拒绝继续",
                  symbol, spec.point, spec.lot_step);
      return;
     }

   spec.valid = true;
   PrintFormat("[ReadSymbolSpecs] %s digits=%d point=%g tick_value=%g tick_size=%g contract_size=%g "
               "lot_min=%g lot_step=%g lot_max=%g stops_level=%d filling_mode=%d",
               spec.symbol, spec.digits, spec.point, spec.tick_value, spec.tick_size,
               spec.contract_size, spec.lot_min, spec.lot_step, spec.lot_max,
               (int)spec.stops_level, (int)spec.filling_mode);
  }

//+------------------------------------------------------------------+
//| 手数规范化：按 lot_step 向下取整，夹在 [lot_min, lot_max]          |
//| 注意：风险预算/手数本身由 Python 侧 sizing 冻结下发；               |
//|       EA 只做取整与夹逼，绝不重算风险（硬规则4/8）。               |
//+------------------------------------------------------------------+
double NormalizeLots(const double lots, const SymbolSpec &spec)
  {
   if(!spec.valid)
     {
      PrintFormat("[NormalizeLots] 错误：规格未就绪（symbol=%s），拒绝下单 —— 上下文 lots=%g",
                  spec.symbol, lots);
      return(0.0);
     }
   double l = MathFloor(lots / spec.lot_step + 1e-8) * spec.lot_step;   // 向下对齐步长
   l = MathMax(l, spec.lot_min);
   l = MathMin(l, spec.lot_max);
   return(NormalizeDouble(l, 2));
  }

//==================================================================
// 1. retcode 映射（G01：OrderSend 的 bool 返回只表示"请求已送达"，
//    成交与否必须看 MqlTradeResult.retcode）
//==================================================================
string RetcodeToString(const int retcode)
  {
   switch(retcode)
     {
      case 0:        return("PREPARING");
      case 10004:    return("REQUOTE");
      case 10006:    return("REJECTED");
      case 10008:    return("PLACED");
      case 10009:    return("DONE");
      case 10010:    return("DONE_PARTIAL");
      case 10012:    return("TIMEOUT");
      case 10013:    return("INVALID_REQUEST");
      case 10014:    return("INVALID_VOLUME");
      case 10015:    return("INVALID_PRICE");
      case 10016:    return("INVALID_STOPS");
      case 10017:    return("TRADE_DISABLED");
      case 10018:    return("MARKET_CLOSED");
      case 10019:    return("NO_MONEY");
      case 10020:    return("PRICE_CHANGED");
      case 10021:    return("PRICE_OFF");
      case 10030:    return("INVALID_FILL");
      case 10035:    return("INVALID_ORDER");
      default:       return(StringFormat("UNKNOWN(%d)", retcode));
     }
  }

//+------------------------------------------------------------------+
//| 可重试 retcode 判定：REQUOTE(10004)/PRICE_CHANGED(10020)/         |
//| PRICE_OFF(10021)/TIMEOUT(10012) —— 按指数退避重试；               |
//| 其余（INVALID_*/NO_MONEY/REJECTED…）一律不重试，带上下文放弃。      |
//+------------------------------------------------------------------+
bool IsRetryableRetcode(const int retcode)
  {
   return(retcode==TRADE_RETCODE_REQUOTE       // 10004
       || retcode==TRADE_RETCODE_PRICE_CHANGED // 10020
       || retcode==TRADE_RETCODE_PRICE_OFF     // 10021
       || retcode==TRADE_RETCODE_TIMEOUT);     // 10012
  }

//+------------------------------------------------------------------+
//| SafeOrderSend —— 订单发送封装（硬规则7：必须读 res.retcode 并重试）|
//|                                                                  |
//| 成功 = DONE(10009) / PLACED(10008) / DONE_PARTIAL(10010)；       |
//| 可重试 = IsRetryableRetcode()，指数退避 200ms 起步翻倍；          |
//| 其余 retcode：记录完整上下文日志后放弃（硬规则9：禁止静默吞错）。  |
//|                                                                  |
//| 注意：Sleep() 会阻塞 OnTimer 事件；最坏阻塞 ≈ 200+400+800ms，     |
//|       远小于 InTimerPeriodSec(默认5s)，骨架可接受；                |
//|       实盘若改为高频，应改状态机异步重试（见 README_EA.md 限制）。 |
//+------------------------------------------------------------------+
bool SafeOrderSend(const MqlTradeRequest &req, MqlTradeResult &res, const int retries=3)
  {
   uint backoff_ms = 200;

   for(int attempt=1; attempt<=retries; attempt++)
     {
      bool sent = OrderSend(req, res);   // bool 仅表示请求送达终端，不代表成交

      if(!sent)
        {
         PrintFormat("[SafeOrderSend] OrderSend 调用失败 err=%d attempt=%d/%d symbol=%s action=%u "
                     "volume=%g price=%g sl=%g tp=%g —— 退避 %u ms 后重试",
                     GetLastError(), attempt, retries, req.symbol, req.action,
                     req.volume, req.price, req.sl, req.tp, backoff_ms);
         Sleep(backoff_ms);
         backoff_ms *= 2;
         continue;
        }

      // —— 请求已送达：成交与否只看 retcode ——
      if(res.retcode==TRADE_RETCODE_DONE        // 10009 市价单成交
      || res.retcode==TRADE_RETCODE_PLACED      // 10008 挂单已接受
      || res.retcode==TRADE_RETCODE_DONE_PARTIAL)// 10010 部分成交
        {
         if(attempt>1)
            PrintFormat("[SafeOrderSend] 第 %d 次尝试成功 retcode=%s(%d) order=%u deal=%u",
                        attempt, RetcodeToString(res.retcode), res.retcode, res.order, res.deal);
         return(true);
        }

      if(IsRetryableRetcode(res.retcode))
        {
         PrintFormat("[SafeOrderSend] 可重试 retcode=%s(%d) attempt=%d/%d symbol=%s volume=%g "
                     "price=%g —— 退避 %u ms 后重试",
                     RetcodeToString(res.retcode), res.retcode, attempt, retries,
                     req.symbol, req.volume, req.price, backoff_ms);
         Sleep(backoff_ms);
         backoff_ms *= 2;
         continue;
        }

      // 不可重试：带上下文记录后放弃（硬规则9）
      PrintFormat("[SafeOrderSend] 不可重试错误，放弃。retcode=%s(%d) symbol=%s action=%u "
                  "volume=%g price=%g sl=%g tp=%g order=%d comment=\"%s\"",
                  RetcodeToString(res.retcode), res.retcode, req.symbol, req.action,
                  req.volume, req.price, req.sl, req.tp, res.order, res.comment);
      return(false);
     }

   PrintFormat("[SafeOrderSend] 重试 %d 次后仍失败（末次 retcode=%s(%d)），放弃并落日志。"
               "需人工/OnTradeTransaction 对账，禁止静默继续。",
               retries, RetcodeToString(res.retcode), res.retcode);
   return(false);
  }

//==================================================================
// 2. MonotonicModifySL —— 止损单调校验（硬规则4：止损只允许向盈利方向移动）
//    多头：new_sl >= 当前 sl；空头：new_sl <= 当前 sl。
//    放宽请求直接拒绝并告警，绝不调用经纪商接口。
//    实现方式：构造 TRADE_ACTION_SL_MODIFY 请求，复用 SafeOrderSend 的
//    retcode 检查与重试通道（硬规则7）。
//==================================================================
bool MonotonicModifySL(const ulong ticket, const double new_sl, const int magic,
                       const SymbolSpec &spec, MqlTradeResult &res)
  {
   if(!PositionSelectByTicket(ticket))
     {
      PrintFormat("[MonotonicModifySL] 错误：持仓 ticket=%I64u 不存在（上下文：止损移动）——放弃", ticket);
      return(false);
     }

   long   pos_type = PositionGetInteger(POSITION_TYPE);
   double cur_sl   = PositionGetDouble(POSITION_SL);
   string pos_sym  = PositionGetString(POSITION_SYMBOL);
   bool   is_long  = (pos_type==POSITION_TYPE_BUY);

   // —— 单调校验：放宽即拒绝（硬规则4）——
   if(is_long && new_sl < cur_sl - spec.point*1e-9)
     {
      PrintFormat("[MonotonicModifySL] 告警：多头止损放宽被拒 ticket=%I64u cur_sl=%g new_sl=%g "
                  "（多头只允许上移）——拒绝调用经纪商接口", ticket, cur_sl, new_sl);
      return(false);
     }
   if(!is_long && new_sl > cur_sl + spec.point*1e-9)
     {
      PrintFormat("[MonotonicModifySL] 告警：空头止损放宽被拒 ticket=%I64u cur_sl=%g new_sl=%g "
                  "（空头只允许下移）——拒绝调用经纪商接口", ticket, cur_sl, new_sl);
      return(false);
     }

   double cur_tp = PositionGetDouble(POSITION_TP);

   MqlTradeRequest req;
   ZeroMemory(req);
   req.action       = TRADE_ACTION_SL_MODIFY;
   req.position     = ticket;
   req.symbol       = pos_sym;
   req.sl           = new_sl;
   req.tp           = cur_tp;
   req.magic        = magic;

   return(SafeOrderSend(req, res));
  }

//==================================================================
// 3. SafeClosePartial —— 部分平仓封装（PositionClosePartial 等价物）
//    用 DEAL 反向动作 + SafeOrderSend 通道（硬规则7 同样适用）。
//    部分平仓后剩余仓位沿用原止损（G05 最佳实践）。
//==================================================================
bool SafeClosePartial(const ulong ticket, const double partial_lots_norm, const int magic,
                      const int slippage_points, const SymbolSpec &spec, MqlTradeResult &res)
  {
   if(!spec.valid)
     {
      PrintFormat("[SafeClosePartial] 错误：规格未就绪，拒绝 ticket=%I64u", ticket);
      return(false);
     }
   if(!PositionSelectByTicket(ticket))
     {
      PrintFormat("[SafeClosePartial] 错误：持仓 ticket=%I64u 不存在 —— 放弃", ticket);
      return(false);
     }

   long   pos_type = PositionGetInteger(POSITION_TYPE);
   double cur_vol  = PositionGetDouble(POSITION_VOLUME);
   string pos_sym  = PositionGetString(POSITION_SYMBOL);

   if(partial_lots_norm <= 0.0 || partial_lots_norm > cur_vol + 1e-9)
     {
      PrintFormat("[SafeClosePartial] 错误：部分平仓量非法 ticket=%I64u partial=%g cur=%g —— 放弃",
                  ticket, partial_lots_norm, cur_vol);
      return(false);
     }

   double price = (pos_type==POSITION_TYPE_BUY)
                  ? SymbolInfoDouble(pos_sym, SYMBOL_BID)
                  : SymbolInfoDouble(pos_sym, SYMBOL_ASK);

   MqlTradeRequest req;
   ZeroMemory(req);
   req.action       = TRADE_ACTION_DEAL;
   req.position     = ticket;
   req.symbol       = pos_sym;
   req.volume       = partial_lots_norm;
   req.price        = price;
   req.type         = (pos_type==POSITION_TYPE_BUY) ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;
   req.deviation    = slippage_points;
   req.magic        = magic;
   req.type_filling = (ENUM_ORDER_FILLING_TYPE)spec.filling_mode;

   return(SafeOrderSend(req, res));
  }

//==================================================================
// 4. 新闻窗口冻结（设计第⑥章第5条）：事件 UTC 时刻列表，
//    ±window_minutes 窗口内拒绝新开仓。窗口宽度 input 化，禁止硬编码。
//==================================================================
bool LoadNewsEvents(const string csv_path, datetime &events[])
  {
   ArrayFree(events);
   int h = FileOpen(csv_path, FILE_READ|FILE_TXT|FILE_ANSI, 0, CP_UTF8);
   if(h==INVALID_HANDLE)
     {
      // 无新闻日历文件是常见部署形态：告警但不致命（窗口视为空）
      PrintFormat("[LoadNewsEvents] 警告：新闻日历 %s 打开失败 err=%d —— 视为无冻结事件，需人工确认部署",
                  csv_path, GetLastError());
      return(false);
     }
   int count = 0;
   while(!FileIsEnding(h))
     {
      string line = FileReadString(h, 1024);
      line = StringTrimLeft(line);
      line = StringTrimRight(line);
      if(StringLen(line)==0 || StringGetCharacter(line,0)=='#') continue;
      datetime ev = (datetime)StringToTime(line);   // 接受 "YYYY.MM.DD HH:MI:SS"（UTC 语义）
      if(ev>0)
        {
         ArrayResize(events, count+1);
         events[count] = ev;
         count++;
        }
     }
   FileClose(h);
   PrintFormat("[LoadNewsEvents] 载入新闻事件 %d 条（UTC 语义）", count);
   return(true);
  }

bool IsInNewsWindow(const datetime now_utc, const datetime &events[], const int window_minutes)
  {
   int n = ArraySize(events);
   if(n==0 || window_minutes<=0) return(false);
   long half = (long)window_minutes * 60;
   for(int i=0; i<n; i++)
     {
      long diff = (long)now_utc - (long)events[i];
      if(diff<0) diff = -diff;
      if(diff <= half) return(true);
     }
   return(false);
  }

//==================================================================
// 5. 日权益熔断三态机（设计第⑥章第6条；G05：熔断由 EA 自律实现，
//    测试器不内置账户级风控）。
//    阈值 InDailyMaxDrawdownPct 只允许来自 config（参照 3% 档，
//    实际由 CLEAN 分布校准后人工填入 —— 硬规则/不变量3）。
//==================================================================
enum ENUM_EA_CIRCUIT
  {
   CIRCUIT_NORMAL   = 0,   // 正常：允许新开仓
   CIRCUIT_BREAKER  = 1,   // 熔断：禁止新开仓，只允许平仓/止损管理
   CIRCUIT_COOLDOWN = 2    // 冷却：需人工重启或次日 00:00 服务器时间重置
  };

struct CircuitState
  {
   ENUM_EA_CIRCUIT state;
   datetime   day_start_server;   // 当日 00:00 服务器时间边界
   double     day_start_equity;   // 当日开盘权益（熔断基准）
  };

//+------------------------------------------------------------------+
//| 每个 OnTimer 调用一次：新的服务器日 → 复位；熔断线触发 → BREAKER  |
//+------------------------------------------------------------------+
void CircuitOnTimerUpdate(CircuitState &cs, const double daily_max_dd_pct)
  {
   double   equity = AccountInfoDouble(ACCOUNT_EQUITY);
   datetime now    = TimeCurrent();          // 服务器时间
   MqlDateTime t;
   TimeToStruct(now, t);
   MqlDateTime d0_struct = t;
   d0_struct.hour=0; d0_struct.min=0; d0_struct.sec=0;
   datetime day0 = StructToTime(d0_struct);

   // —— 新服务器日：熔断状态复位（设计：次日 00:00 服务器时间自动重置）——
   if(day0 > cs.day_start_server)
     {
      if(cs.state!=CIRCUIT_NORMAL)
         PrintFormat("[Circuit] 服务器新的一日，熔断复位 breaker->normal。昨收权益=%g", equity);
      cs.state             = CIRCUIT_NORMAL;
      cs.day_start_server  = day0;
      cs.day_start_equity  = AccountInfoDouble(ACCOUNT_BALANCE);   // 日基准用余额（可配）
      PrintFormat("[Circuit] 新交易日基准：day_start_equity=%g", cs.day_start_equity);
     }

   if(cs.day_start_equity<=0.0) return;

   double dd = (cs.day_start_equity - equity) / cs.day_start_equity;
   if(cs.state==CIRCUIT_NORMAL && dd >= daily_max_dd_pct)
     {
      cs.state = CIRCUIT_BREAKER;
      PrintFormat("[Circuit] 告警：当日权益回撤 %g%% ≥ 阈值 %g%% —— 进入熔断：禁止新开仓，"
                  "只允许平仓。恢复须人工重启或次日 00:00 服务器时间。",
                  dd*100.0, daily_max_dd_pct*100.0);
     }
  }

//==================================================================
// 6. JSONL 最小解析器（骨架实现，非完整 JSON 校验器）
//    信号行格式见 SIGNAL_PROTOCOL.md；字段缺失/非法一律视为无效行，
//    带上下文日志跳过（硬规则9：禁止静默吞错）。
//==================================================================
string JsonExtractString(const string line, const string key)
  {
   string pat = "\"" + key + "\"";
   int k = StringFind(line, pat);
   if(k<0) return("");
   int colon = StringFind(line, ":", k);
   if(colon<0) return("");
   int q1 = StringFind(line, "\"", colon+1);
   if(q1<0) return("");
   int q2 = StringFind(line, "\"", q1+1);
   if(q2<0) return("");
   return(StringSubstr(line, q1+1, q2-q1-1));
  }

double JsonExtractNumber(const string line, const string key)
  {
   string pat = "\"" + key + "\"";
   int k = StringFind(line, pat);
   if(k<0) return(0.0/0.0);   // NaN：表示字段缺失，由调用方判定
   int colon = StringFind(line, ":", k);
   if(colon<0) return(0.0/0.0);
   int i = colon+1;
   int len = StringLen(line);
   string buf = "";
   while(i<len)
     {
      ushort c = StringGetCharacter(line, i);
      if((c>='0' && c<='9') || c=='.' || c=='-' || c=='e' || c=='E')
        { buf += ShortToString(c); i++; }
      else break;
     }
   if(StringLen(buf)==0) return(0.0/0.0);
   return(StringToDouble(buf));
  }

long JsonExtractLong(const string line, const string key)
  {
   double v = JsonExtractNumber(line, key);
   return((long)v);
  }

#endif // TRADE_UTILS_MQH
//+------------------------------------------------------------------+
