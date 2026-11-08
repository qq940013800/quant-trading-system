
        // 调试日志系统
        window.debugLogs = [];
        window.debugMaxLogs = 50;
        
        function debugLog(msg, type = 'info') {
            const time = new Date().toLocaleTimeString();
            window.debugLogs.push({ time, msg, type });
            if (window.debugLogs.length > window.debugMaxLogs) {
                window.debugLogs.shift();
            }
            renderDebugPanel();
        }
        
        function renderDebugPanel() {
            const panel = document.getElementById('debug-content');
            if (!panel) return;
            panel.innerHTML = window.debugLogs.map(log => 
                `<div class="debug-log debug-${log.type}">[${log.time}] ${log.msg}</div>`
            ).join('');
            panel.scrollTop = panel.scrollHeight;
        }
        
        // 捕获全局错误
        window.onerror = function(msg, url, line, col, error) {
            debugLog(`JS错误: ${msg} (行:${line})`, 'error');
            return false;
        };
        
        window.addEventListener('unhandledrejection', function(e) {
            debugLog(`Promise错误: ${e.reason}`, 'error');
        });
        
        // 页面加载完成
        document.addEventListener('DOMContentLoaded', function() {
            debugLog('页面DOM加载完成', 'success');
            
            // 创建调试面板
            const toggle = document.createElement('div');
            toggle.id = 'debug-toggle';
            toggle.innerHTML = '!';
            toggle.onclick = function() {
                const panel = document.getElementById('debug-panel');
                panel.classList.toggle('visible');
            };
            document.body.appendChild(toggle);
            
            const panel = document.createElement('div');
            panel.id = 'debug-panel';
            panel.innerHTML = `
                <div id="debug-header" onclick="document.getElementById('debug-panel').classList.toggle('visible')">
                    <span>🐛 调试日志</span>
                    <span onclick="this.parentElement.parentElement.classList.remove('visible')">×</span>
                </div>
                <div id="debug-content"></div>
            `;
            document.body.appendChild(panel);
            
            debugLog('调试面板已初始化', 'success');
        });
        
        // 捕获所有fetch请求
        const originalFetch = window.fetch;
        window.fetch = function(...args) {
            debugLog(`API请求: ${args[0]}`, 'info');
            return originalFetch.apply(this, args)
                .then(response => {
                    debugLog(`API响应: ${args[0]} -> ${response.status}`, response.ok ? 'success' : 'error');
                    return response;
                })
                .catch(err => {
                    debugLog(`API失败: ${args[0]} -> ${err.message}`, 'error');
                    throw err;
                });
        };
    


        // ========== API 服务层 ==========
        const API_BASE = '/api';

        const ApiService = {
            async request(path, options = {}) {
                const startTime = Date.now();
                try {
                    const token = localStorage.getItem('qd_token') || '';
                    const response = await fetch(`${API_BASE}${path}`, {
                        headers: { 
                            'Authorization': token ? `Bearer ${token}` : '',
                            'Content-Type': 'application/json',
                            ...options.headers
                        },
                        ...options
                    });
                    
                    if (response.status === 401) {
                        debugLog('未登录或Token过期', 'warn');
                        return { code: 401, msg: '未登录', data: null, _unauthorized: true };
                    }
                    
                    const data = await response.json();
                    const latency = Date.now() - startTime;
                    const latencyEl = document.getElementById('latency');
                    if (latencyEl) latencyEl.textContent = latency + 'ms';
                    return data;
                } catch (e) {
                    debugLog(`API 请求失败: ${path} - ${e.message}`, 'error');
                    return { code: 0, msg: e.message, data: null, _error: true };
                }
            },

            getCredentials() {
                return this.request('/credentials/list');
            },

            getDashboardSummary() {
                return this.request('/dashboard/summary');
            },

            // 修复：正确的策略列表路径
            getStrategies() {
                return this.request('/strategies');
            },

            // AI 复盘：生成策略复盘报告（只读归因，不触发交易）
            postReviewReport(payload) {
                return this.request('/strategies/review-report', {
                    method: 'POST',
                    body: JSON.stringify(payload)
                });
            },

            // AI 复盘：历史复盘记录列表
            getReviewHistory(strategyId, limit = 20) {
                return this.request(`/strategies/review-report/history?id=${encodeURIComponent(strategyId)}&limit=${limit}`);
            },

            // 日志中心：策略决策/运行日志（只读归因素材）
            getStrategyLogs(strategyId, limit = 200) {
                return this.request(`/strategies/logs?id=${encodeURIComponent(strategyId)}&limit=${limit}`);
            },

            // 日志中心：策略成交事件（交易日志，只读归因素材）
            getStrategyTrades(strategyId) {
                return this.request(`/strategies/trades?id=${encodeURIComponent(strategyId)}`);
            },

            getPositions() {
                return this.request('/portfolio/positions');
            },

            // 修复：正确的K线API路径（后端注册在/api/indicator前缀下）
            getKline(symbol, timeframe = '1H', limit = 300) {
                return this.request(`/indicator/kline?market=Crypto&symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}&limit=${limit}`);
            },

            // 修复：正确的回测API参数
            runBacktest(params) {
                return this.request('/backtest/run', {
                    method: 'POST',
                    body: JSON.stringify({
                        code: params.code || '# 简单趋势策略\nimport numpy as np\n\ndef initialize(context):\n    context.sma_short = 20\n    context.sma_long = 50\n\ndef handle_data(context, data):\n    pass',
                        startDate: params.startDate || '2024-01-01',
                        endDate: params.endDate || '2024-12-31',
                        initialCapital: parseFloat(params.initialCapital) || 10000,
                        leverageEnabled: false
                    })
                });
            },

            // 回测历史记录（只读，用于回测结果卡真实回显）
            getBacktestHistory(limit = 20) {
                return this.request(`/backtest/history?limit=${limit}`);
            },

            // 单条回测完整结果（只读，取权益/回撤曲线）
            getBacktestRun(runId) {
                return this.request(`/backtest/get?runId=${runId}`);
            }
        };

        // ========== Toast 提示 ==========
        function showToast(message, type = 'success') {
            const toast = document.createElement('div');
            toast.className = `toast ${type}`;
            toast.textContent = message;
            document.body.appendChild(toast);
            setTimeout(() => toast.remove(), 3000);
        }

        // ========== K线图初始化 ==========
        let mainChart = null;
        let candlestickSeries = null;
        let volumeSeries = null;
        let currentSymbol = 'BTC/USDT';
        let currentTimeframe = '1H';
        let isUsingMockData = false;

        function initMainChart() {
            const container = document.getElementById('main-chart');
            mainChart = LightweightCharts.createChart(container, {
                layout: {
                    background: { color: '#12161c' },
                    textColor: '#848e9c',
                },
                grid: {
                    vertLines: { color: '#1e2329' },
                    horzLines: { color: '#1e2329' },
                },
                crosshair: {
                    mode: LightweightCharts.CrosshairMode.Normal,
                },
                rightPriceScale: {
                    borderColor: '#2b3139',
                },
                timeScale: {
                    borderColor: '#2b3139',
                    timeVisible: true,
                },
                width: container.clientWidth,
                height: container.clientHeight,
            });

            candlestickSeries = mainChart.addCandlestickSeries({
                upColor: '#0ecb81',
                downColor: '#f6465d',
                borderDownColor: '#f6465d',
                borderUpColor: '#0ecb81',
                wickDownColor: '#f6465d',
                wickUpColor: '#0ecb81',
            });

            // 初始化成交量副图
            initVolumeChart();

            // 从真实API加载K线
            loadKlineData();
            
            // 启动WebSocket实时推送
            initRealtimeWebSocket();
        }

        function initVolumeChart() {
            if (!mainChart) return;
            volumeSeries = mainChart.addHistogramSeries({
                priceFormat: { type: 'volume' },
                priceScaleId: '',
            });
            volumeSeries.priceScale().applyOptions({
                scaleMargins: { top: 0.7, bottom: 0 },
            });
        }

        // 修复：真实API加载K线，失败才用模拟数据并明确标注
        // silent=true 用于 30s 轮询静默刷新（不闪 loading 遮罩）
        async function loadKlineData(silent = false) {
            if (!silent) showKlineLoading(true);
            
            try {
                const res = await ApiService.getKline(currentSymbol, currentTimeframe, 300);
                
                if (res.data && Array.isArray(res.data) && res.data.length > 0) {
                    isUsingMockData = false;
                    const klineData = res.data.map(k => ({
                        time: k.time || k.timestamp,
                        open: parseFloat(k.open),
                        high: parseFloat(k.high),
                        low: parseFloat(k.low),
                        close: parseFloat(k.close),
                    }));
                    
                    const volumeData = res.data.map(k => ({
                        time: k.time || k.timestamp,
                        value: parseFloat(k.volume || 0),
                        color: parseFloat(k.close) >= parseFloat(k.open) ? 'rgba(14, 203, 129, 0.5)' : 'rgba(246, 70, 93, 0.5)'
                    }));
                    
                    candlestickSeries.setData(klineData);
                    if (volumeSeries) volumeSeries.setData(volumeData);
                    showDataSourceBadge('live');
                } else {
                    // 真实登录态：接口空返回走真实空态，不用人造蜡烛顶替；仅未登录（非真实）才保留 mock 兜底
                    if (Auth.isLoggedIn()) {
                        _clearKlinePanel();
                    } else {
                        generateMockKlineData();
                        showDataSourceBadge('mock');
                    }
                }
            } catch (e) {
                debugLog(`K线API失败: ${e.message}`, 'warn');
                if (Auth.isLoggedIn()) {
                    _clearKlinePanel();
                } else {
                    generateMockKlineData();
                    showDataSourceBadge('mock');
                }
            } finally {
                showKlineLoading(false);
            }
        }

        function showKlineLoading(show) {
            const el = document.getElementById('kline-loading');
            if (el) el.style.display = show ? 'flex' : 'none';
        }

        // 真实登录态 K 线空态：清空蜡烛/成交量/价格，不留 42000 起的人造行情
        function _clearKlinePanel() {
            if (candlestickSeries) candlestickSeries.setData([]);
            if (volumeSeries) volumeSeries.setData([]);
            const priceEl = document.getElementById('chart-price');
            if (priceEl) { priceEl.textContent = '--'; delete priceEl.dataset.lastPrice; }
            const badgeEl = document.getElementById('data-source-badge');
            if (badgeEl) badgeEl.innerHTML = '<span style="color: var(--text-tertiary); font-size: 10px; font-weight: 600;">○ 暂无真实行情</span>';
        }

        function showDataSourceBadge(type) {
            const el = document.getElementById('data-source-badge');
            if (!el) return;
            el.innerHTML = type === 'live' 
                ? '<span style="color: #0ecb81; font-size: 10px; font-weight: 600;">● LIVE 实时数据</span>'
                : '<span style="color: #f0b90b; font-size: 10px; font-weight: 600;">○ 模拟数据</span>';
        }

        function generateMockKlineData() {
            const data = [];
            let price = 42000;
            const now = Math.floor(Date.now() / 1000);
            const intervalSeconds = 3600; // 1h
            
            for (let i = 200; i >= 0; i--) {
                const time = now - i * intervalSeconds;
                const open = price;
                const change = (Math.random() - 0.5) * 200;
                const close = open + change;
                const high = Math.max(open, close) + Math.random() * 50;
                const low = Math.min(open, close) - Math.random() * 50;
                
                data.push({ time, open, high, low, close });
                price = close;
            }

            candlestickSeries.setData(data);
            const priceEl = document.getElementById('chart-price');
            if (priceEl) priceEl.textContent = '$' + data[data.length - 1].close.toLocaleString();
        }

        // ========== WebSocket 实时推送 ==========
        // 基于第一性原理：公共行情数据无需认证，前端直连交易所公共WebSocket
        // 全球最佳实践：Binance/OKX前端都直接连接公共WS，不经过后端中转
        let priceSocket = null;
        let orderbookSocket = null;
        let wsReconnectTimer = null;
        let lastPrice = 0;

        function initRealtimeWebSocket() {
            debugLog('初始化WebSocket实时推送...', 'info');
            
            // 连接Binance公共行情WebSocket（免费、稳定、无需API key）
            connectPriceWebSocket();
            
            // 连接订单簿深度WebSocket
            connectOrderbookWebSocket();
        }

        function connectPriceWebSocket() {
            if (priceSocket) {
                priceSocket.close();
            }
            
            // Binance BTC/USDT 1分钟K线流
            const wsUrl = 'wss://stream.binance.com:9443/ws/btcusdt@miniTicker';
            
            try {
                priceSocket = new WebSocket(wsUrl);
                
                priceSocket.onopen = function() {
                    debugLog('WebSocket行情连接成功', 'success');
                    updateWsStatus('connected');
                };
                
                priceSocket.onmessage = function(event) {
                    try {
                        const data = JSON.parse(event.data);
                        handlePriceUpdate(data);
                    } catch (e) {
                        debugLog(`WebSocket消息解析失败: ${e.message}`, 'warn');
                    }
                };
                
                priceSocket.onerror = function(error) {
                    debugLog('WebSocket行情错误: ' + error, 'error');
                    updateWsStatus('error');
                };
                
                priceSocket.onclose = function() {
                    debugLog('WebSocket行情断开，5秒后重连...', 'warn');
                    updateWsStatus('disconnected');
                    // 自动重连
                    wsReconnectTimer = setTimeout(connectPriceWebSocket, 5000);
                };
            } catch (e) {
                debugLog('WebSocket初始化失败: ' + e.message, 'error');
                updateWsStatus('error');
            }
        }

        function handlePriceUpdate(data) {
            // Binance miniTicker 数据格式:
            // {c: 当前收盘价, o: 开盘价, h: 最高价, l: 最低价, v: 成交量}
            const price = parseFloat(data.c);
            if (!price || isNaN(price)) return;
            
            lastPrice = price;
            
            // 更新顶部价格显示
            const priceEl = document.getElementById('chart-price');
            if (priceEl) {
                const priceDiff = price - (priceEl.dataset.lastPrice || price);
                priceEl.textContent = '$' + price.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
                priceEl.dataset.lastPrice = price;
                
                // 涨跌颜色闪烁
                priceEl.style.color = priceDiff >= 0 ? '#0ecb81' : '#f6465d';
                setTimeout(() => { priceEl.style.color = ''; }, 300);
            }
            
            // 更新买卖面板价格
            const orderPriceInput = document.getElementById('order-price');
            if (orderPriceInput && !orderPriceInput.dataset.userEdited) {
                orderPriceInput.value = price.toFixed(2);
            }
            
            // 更新最后价格到日志
            if (Math.random() < 0.05) { // 每20条记录一条，避免刷屏
                debugLog('实时价格: $' + price.toFixed(2), 'info');
            }
        }

        function connectOrderbookWebSocket() {
            if (orderbookSocket) {
                orderbookSocket.close();
            }
            
            // Binance BTC/USDT 订单簿深度流（20档）
            const wsUrl = 'wss://stream.binance.com:9443/ws/btcusdt@depth20@100ms';
            
            try {
                orderbookSocket = new WebSocket(wsUrl);
                
                orderbookSocket.onopen = function() {
                    debugLog('WebSocket订单簿连接成功', 'success');
                };
                
                orderbookSocket.onmessage = function(event) {
                    try {
                        const data = JSON.parse(event.data);
                        handleOrderbookUpdate(data);
                    } catch (e) {
                        debugLog(`订单簿WebSocket解析失败: ${e.message}`, 'warn');
                    }
                };
                
                orderbookSocket.onerror = function(error) {
                    debugLog('订单簿WebSocket错误: ' + error, 'error');
                };
                
                orderbookSocket.onclose = function() {
                    debugLog('订单簿WebSocket断开，5秒后重连...', 'warn');
                    setTimeout(connectOrderbookWebSocket, 5000);
                };
            } catch (e) {
                debugLog('订单簿WebSocket初始化失败: ' + e.message, 'warn');
            }
        }

        function handleOrderbookUpdate(data) {
            // Binance partial book depth 流: bids=买单降序, asks=卖单升序
            const bids = data.bids || [];
            const asks = data.asks || [];

            const asksEl = document.getElementById('orderbook-asks');
            const bidsEl = document.getElementById('orderbook-bids');
            const spreadEl = document.getElementById('orderbook-spread');
            if (!asksEl || !bidsEl) return;

            // 真实登录态且推送为空/断流：走真实空态，不留静态演示档位
            if (Auth.isLoggedIn() && asks.length === 0 && bids.length === 0) {
                asksEl.textContent = '';
                bidsEl.textContent = '';
                if (spreadEl) spreadEl.textContent = '--';
                return;
            }

            const num = (x) => parseFloat(x) || 0;
            const allAmt = bids.map(b => num(b[1])).concat(asks.map(a => num(a[1])));
            const maxAmt = Math.max(1, ...allAmt);

            const row = (side, price, amount, cum, barPct) => {
                const barSide = side === 'ask' ? 'ask' : 'bid';
                return `<div class="orderbook-row ${barSide}">
                    <span class="orderbook-price ${barSide}">${num(price).toFixed(2)}</span>
                    <span class="orderbook-amount">${num(amount).toFixed(4)}</span>
                    <span class="orderbook-total">${cum.toFixed(2)}</span>
                    <div class="amount-bar" style="width:${barPct}%;"></div>
                </div>`;
            };

            // 卖盘：价格从高到低展示，累计总额沿档位累加
            const askRows = asks.slice().reverse();
            let cumAsk = 0;
            asksEl.innerHTML = askRows.map(([p, q]) => {
                cumAsk += num(p) * num(q);
                return row('ask', p, q, cumAsk, (num(q) / maxAmt * 100).toFixed(1));
            }).join('');

            // 买盘：价格从高到低展示
            let cumBid = 0;
            bidsEl.innerHTML = bids.map(([p, q]) => {
                cumBid += num(p) * num(q);
                return row('bid', p, q, cumBid, (num(q) / maxAmt * 100).toFixed(1));
            }).join('');

            if (spreadEl && asks.length > 0 && bids.length > 0) {
                const spread = num(asks[0][0]) - num(bids[0][0]);
                spreadEl.textContent = `价差: $${spread.toFixed(2)}`;
            }
        }

        function updateWsStatus(status) {
            const statusEl = document.getElementById('ws-status');
            if (!statusEl) return;
            
            const statusMap = {
                connected: { text: '● WS已连接', color: '#0ecb81' },
                disconnected: { text: '○ WS重连中', color: '#f0b90b' },
                error: { text: '✕ WS错误', color: '#f6465d' }
            };
            
            const s = statusMap[status] || statusMap.disconnected;
            statusEl.innerHTML = `<span style="color: ${s.color}; font-size: 11px; margin-left: 8px;">${s.text}</span>`;
        }

        // 页面卸载时关闭WebSocket
        window.addEventListener('beforeunload', function() {
            if (priceSocket) priceSocket.close();
            if (orderbookSocket) orderbookSocket.close();
            if (wsReconnectTimer) clearTimeout(wsReconnectTimer);
        });

        // ========== 权益曲线 ==========
        let equityChart = null;
        let drawdownChart = null;
        let equitySeries = null;
        let drawdownSeries = null;

        // 读取容器当前尺寸；容器隐藏/未就绪时回退兜底尺寸，避免图表落成默认 300×150
        function _chartSize(container, fallbackW, fallbackH) {
            return {
                width: (container && container.clientWidth) || fallbackW,
                height: (container && container.clientHeight) || fallbackH
            };
        }

        function initEquityChart(points) {
            const container = document.getElementById('equity-chart');
            if (!container) return;

            if (!equityChart) {
                const size = _chartSize(container, 919, 400);
                equityChart = LightweightCharts.createChart(container, {
                    layout: {
                        background: { color: '#12161c' },
                        textColor: '#848e9c',
                    },
                    grid: {
                        vertLines: { color: '#1e2329' },
                        horzLines: { color: '#1e2329' },
                    },
                    width: size.width,
                    height: size.height,
                });

                equitySeries = equityChart.addAreaSeries({
                    lineColor: '#f0b90b',
                    topColor: 'rgba(240, 185, 11, 0.3)',
                    bottomColor: 'rgba(240, 185, 11, 0.0)',
                    lineWidth: 2,
                });
            }

            equityChart.applyOptions(_chartSize(container, 919, 400));
            equitySeries.setData(Array.isArray(points) ? points : []);
        }

        // ========== 页面切换 ==========
        debugLog('页面切换模块初始化', 'info');
        document.querySelectorAll('.nav-item').forEach(item => {
            item.addEventListener('click', () => {
                const page = item.dataset.page;
                debugLog(`切换到页面: ${page}`, 'info');
                try {
                    document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
                    item.classList.add('active');
                    document.querySelectorAll('.page-view').forEach(v => v.classList.remove('active'));
                    const targetPage = document.getElementById(`page-${page}`);
                    if (!targetPage) {
                        debugLog(`页面不存在: page-${page}`, 'error');
                        return;
                    }
                    targetPage.classList.add('active');
                    debugLog(`页面切换成功: ${page}`, 'success');
                    
                    // 切换到回测页时加载最近历史回测结果（只读回显）
                    if (page === 'backtest') {
                        setTimeout(() => {
                            loadBacktestResults();
                        }, 100);
                    }
                    
                    // 切换到日志页时刷新决策/交易/系统日志
                    if (page === 'logs') {
                        setTimeout(() => {
                            if (window.refreshLogCenter) window.refreshLogCenter();
                            else if (window.renderLogList) window.renderLogList();
                        }, 100);
                    }
                    
                    // 切换到AI验证层时加载数据
                    if (page === 'validation') {
                        setTimeout(() => {
                            loadValidationData();
                        }, 100);
                    }
                    
                    // 切换到风险页时加载风险数据
                    if (page === 'risk') {
                        setTimeout(() => {
                            loadRiskData();
                        }, 100);
                    }
                    
                    // 切换到核心引擎页时加载引擎数据
                    if (page === 'engine') {
                        setTimeout(() => {
                            loadEngineData();
                        }, 100);
                    }

                    // 切换到 AI 复盘页时加载策略下拉与历史记录
                    if (page === 'review') {
                        setTimeout(() => {
                            initReviewModule();
                            loadReviewStrategies();
                            loadReviewHistory();
                        }, 100);
                    }
                } catch (err) {
                    debugLog(`页面切换失败: ${err.message}`, 'error');
                }
            });
        });
        debugLog(`找到 ${document.querySelectorAll('.nav-item').length} 个导航项`, 'success');

        // ========== AI验证层 子标签切换 ==========
        function switchValidationTab(group) {
            const page = document.getElementById('page-validation');
            if (!page) return;
            page.querySelectorAll('.vtab').forEach(t => {
                t.classList.toggle('active', t.dataset.vtab === group);
            });
            page.querySelectorAll('[data-vpanel]').forEach(p => {
                p.classList.toggle('vpanel-hidden', p.dataset.vpanel !== group);
            });
        }

        function initValidationTabs() {
            const page = document.getElementById('page-validation');
            if (!page) return;
            page.querySelectorAll('.vtab').forEach(t => {
                t.addEventListener('click', () => switchValidationTab(t.dataset.vtab));
            });
            const active = page.querySelector('.vtab.active');
            switchValidationTab(active ? active.dataset.vtab : 'monitor');
        }

        initValidationTabs();

        // ========== 时间周期切换 ==========
        document.querySelectorAll('.timeframe-tab').forEach(tab => {
            tab.addEventListener('click', () => {
                document.querySelectorAll('.timeframe-tab').forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
                currentTimeframe = tab.dataset.tf;
                loadKlineData(); // 重新从API加载数据
            });
        });

        // ========== 下单面板切换 ==========
        document.querySelectorAll('.order-tab').forEach(tab => {
            tab.addEventListener('click', () => {
                document.querySelectorAll('.order-tab').forEach(t => {
                    t.classList.remove('active', 'buy', 'sell');
                });
                const isBuy = tab.textContent === '买入';
                if (isBuy) {
                    tab.classList.add('active', 'buy');
                } else {
                    tab.classList.add('active', 'sell');
                }
                
                // 更新按钮文字和颜色
                const submitBtn = document.getElementById('submit-order-btn');
                if (submitBtn) {
                    submitBtn.textContent = isBuy ? '买入 BTC' : '卖出 BTC';
                    submitBtn.className = isBuy ? 'btn-primary btn-buy' : 'btn-primary btn-sell';
                }
            });
        });

        // ========== 策略编辑弹窗 ==========
        function openEditStrategy(strategyName) {
            document.getElementById('editStrategyName').textContent = strategyName;
            document.getElementById('editStrategyModal').classList.add('active');
        }

        function closeEditStrategy() {
            document.getElementById('editStrategyModal').classList.remove('active');
        }

        // ========== 策略详情弹窗 ==========
        let currentDetailStrategy = null;

        function openStrategyDetail(strategy) {
            currentDetailStrategy = strategy;
            
            // 填充基本信息
            document.getElementById('detail-strategy-name').textContent = strategy.name || '策略详情';
            document.getElementById('detail-strategy-id').textContent = strategy.id || '--';
            document.getElementById('detail-strategy-status').textContent = 
                (strategy.status === 'running' || strategy.status === 'active') ? '运行中' : '已停止';
            document.getElementById('detail-strategy-symbol').textContent = strategy.symbol || '--';
            document.getElementById('detail-strategy-created').textContent = strategy.created_at || '--';
            
            // 绩效指标：优先取策略携带字段，后端未返回时显示 --，不编演示数字
            document.getElementById('detail-total-return').textContent = '--';
            document.getElementById('detail-sharpe').textContent = strategy.sharpe == null ? '--' : Number(strategy.sharpe).toFixed(2);
            document.getElementById('detail-drawdown').textContent = strategy.max_drawdown == null ? '--' : Number(strategy.max_drawdown).toFixed(1) + '%';
            document.getElementById('detail-winrate').textContent = strategy.win_rate == null ? '--' : Number(strategy.win_rate).toFixed(0) + '%';
            document.getElementById('detail-trades').textContent = strategy.total_trades == null ? '--' : strategy.total_trades;
            document.getElementById('detail-profit-factor').textContent = '--';

            // 参数配置：取策略携带字段，后端未返回时显示 --，不编演示数字
            const tc = strategy.trading_config || {};
            const cap = strategy.initial_capital ?? null;
            document.getElementById('detail-capital').textContent =
                cap == null ? '--' : Number(cap).toFixed(2);
            const lev = strategy.leverage ?? tc.leverage ?? null;
            document.getElementById('detail-leverage').textContent =
                lev == null ? '--' : Number(lev) + 'x';
            const stopLoss = tc.equity_stop_loss_pct ?? null;
            document.getElementById('detail-stop-loss').textContent =
                stopLoss == null ? '--' : (Number(stopLoss) * 100).toFixed(1) + '%';
            // 累计亏损停止：后端未提供独立字段，留空态
            document.getElementById('detail-max-loss').textContent = '--';
            
            // 更新按钮文字
            const isRunning = strategy.status === 'running' || strategy.status === 'active';
            document.getElementById('detail-toggle-btn-text').textContent = isRunning ? '停止策略' : '启动策略';
            
            // 显示弹窗
            document.getElementById('strategyDetailModal').classList.add('active');
            
            debugLog('打开策略详情: ' + (strategy.name || '未知'), 'info');
        }

        function closeStrategyDetail() {
            document.getElementById('strategyDetailModal').classList.remove('active');
            currentDetailStrategy = null;
        }

        function toggleStrategyStatus() {
            if (!currentDetailStrategy) return;
            const isRunning = currentDetailStrategy.status === 'running' || currentDetailStrategy.status === 'active';
            const action = isRunning ? '停止' : '启动';
            
            if (confirm(`确定要${action}策略 "${currentDetailStrategy.name}" 吗？`)) {
                showToast(`策略已${action}（模拟）`, 'success');
                debugLog(`${action}策略: ${currentDetailStrategy.name}`, 'success');
                
                // 更新状态
                currentDetailStrategy.status = isRunning ? 'stopped' : 'running';
                document.getElementById('detail-strategy-status').textContent = isRunning ? '已停止' : '运行中';
                document.getElementById('detail-toggle-btn-text').textContent = isRunning ? '启动策略' : '停止策略';
                
                // 刷新策略列表
                setTimeout(() => {
                    if (typeof loadStrategies === 'function') loadStrategies();
                }, 500);
            }
        }

        // ========== 提交订单（对接真实API）==========
        // 基于第一性原理：危险操作需要明确反馈，成功/失败都要用户知道
        async function submitOrder() {
            try {
                // 1. 获取当前订单方向（买入/卖出）
                const activeTab = document.querySelector('.order-tab.active');
                const side = activeTab && activeTab.textContent.includes('卖出') ? 'sell' : 'buy';
                
                // 2. 获取交易对
                const symbolSelect = document.getElementById('order-symbol');
                const symbol = symbolSelect ? symbolSelect.value : 'BTC/USDT';
                
                // 3. 获取价格（限价单才用）
                const priceInput = document.getElementById('order-price');
                const price = priceInput ? parseFloat(priceInput.value) : 0;
                
                // 4. 获取数量/金额
                const amountInput = document.getElementById('order-amount');
                const amount = amountInput ? parseFloat(amountInput.value) : 100;
                
                // 5. 获取杠杆
                const leverageInput = document.getElementById('order-leverage');
                const leverage = leverageInput ? parseInt(leverageInput.value) : 1;
                
                // 6. 获取当前选中的凭证ID（从账户列表第一个）
                const firstAccount = document.querySelector('.credential-option');
                const credentialId = firstAccount ? parseInt(firstAccount.dataset.id || 1) : 1;
                
                debugLog(`提交订单: ${side} ${amount} USDT ${symbol}`, 'info');
                
                // 7. 调用真实API
                const orderData = {
                    credential_id: credentialId,
                    symbol: symbol,
                    side: side,
                    order_type: price > 0 ? 'limit' : 'market',
                    amount: amount,
                    price: price,
                    leverage: leverage,
                    market_type: leverage > 1 ? 'swap' : 'spot',
                    source: 'manual'
                };
                
                const result = await ApiService.request('/quick-trade/place-order', {
                    method: 'POST',
                    body: JSON.stringify(orderData)
                });
                
                if (result.code === 1 || result.code === 200) {
                    showToast(`订单提交成功！${side === 'buy' ? '买入' : '卖出'} ${amount} USDT ${symbol}`, 'success');
                    debugLog('下单成功: ' + JSON.stringify(result.data || result), 'success');
                    
                    // 刷新持仓和资产
                    setTimeout(() => {
                        if (typeof loadDashboardData === 'function') loadDashboardData();
                    }, 1000);
                } else {
                    showToast('下单失败: ' + (result.msg || result.message || '未知错误'), 'error');
                    debugLog('下单失败: ' + JSON.stringify(result), 'error');
                }
            } catch (e) {
                showToast('下单错误: ' + e.message, 'error');
                debugLog('下单异常: ' + e.message, 'error');
            }
        }

        // ========== 回测结果：历史记录真实回显（只读，不触发新回测） ==========
        function _btPct(value, { signed = false, digits = 2 } = {}) {
            if (value === null || value === undefined || Number.isNaN(Number(value))) return '--';
            const n = Number(value);
            const sign = signed ? (n >= 0 ? '+' : '-') : '';
            return sign + Math.abs(n).toFixed(digits) + '%';
        }

        function _btBlankResults() {
            const retEl = document.getElementById('bt-total-return');
            const sharpeEl = document.getElementById('bt-sharpe');
            const ddEl = document.getElementById('bt-drawdown');
            const winEl = document.getElementById('bt-winrate');
            if (retEl) retEl.textContent = '--';
            if (sharpeEl) sharpeEl.textContent = '--';
            if (ddEl) ddEl.textContent = '--';
            if (winEl) winEl.textContent = '--';
            if (equitySeries) equitySeries.setData([]);
            if (drawdownSeries) drawdownSeries.setData([]);
        }

        // 真实模式判定：已登录且回测历史接口返回真实记录；false 时保留演示样例作为兜底
        let backtestIsReal = false;

        // 后端暂无逐策略绩效快照与月度收益序列，真实模式对比表/热力图清空为 --，杜绝假绩效混淆
        function _clearComparisonTable() {
            const tbody = document.getElementById('comparison-table-body');
            if (!tbody) return;
            tbody.querySelectorAll('tr').forEach(tr => {
                tr.querySelectorAll('td').forEach(td => {
                    td.textContent = '--';
                    td.style.color = '';
                });
            });
        }

        function _clearMonthlyHeatmap() {
            const grid = document.getElementById('monthly-heatmap-grid');
            if (!grid) return;
            grid.querySelectorAll('.heatmap-cell').forEach(cell => {
                cell.textContent = '--';
                cell.classList.remove('positive', 'negative');
            });
        }

        // 真实模式判定：风险接口可达；false 时保留演示样例作为兜底
        let riskIsReal = false;

        // 后端暂无策略级风险预算/风险贡献数据，真实模式清空静态演示占比，杜绝假口径
        function _clearRiskBudget() {
            const list = document.getElementById('risk-budget-list');
            if (!list) return;
            list.innerHTML = '<div style="display:flex;justify-content:space-between;align-items:center;font-size:12px;color:var(--text-secondary);"><span>暂无策略级风险预算数据</span><span>--</span></div>';
        }

        // 后端暂无逐策略健康度绩效（名称/天数/收益/夏普/回撤/胜率），真实模式清空静态演示卡片
        function _clearHealthMonitorCards() {
            const list = document.getElementById('strategy-health-list');
            if (!list) return;
            list.innerHTML = '<div style="padding:16px;background:var(--bg-primary);border-radius:8px;color:var(--text-secondary);font-size:12px;">暂无策略级健康度绩效数据</div>';
        }

        // TCA 成本汇总：后端无订单返回 no_orders；真实模式清空静态演示成本
        function _clearTca() {
            ['tca-commission', 'tca-spread', 'tca-slippage', 'tca-impact', 'tca-timing', 'tca-total'].forEach(id => {
                const el = document.getElementById(id);
                if (el) el.textContent = '--';
            });
            const v = document.getElementById('tca-verdict');
            if (v) v.textContent = '--';
        }

        function renderTcaSummary(data) {
            if (!data || data.status === 'no_orders') { _clearTca(); return; }
            const b = data.cost_breakdown_pct || {};
            const map = [
                ['tca-commission', b.commission],
                ['tca-spread', b.spread],
                ['tca-slippage', b.slippage],
                ['tca-impact', b.market_impact],
                ['tca-timing', b.timing_risk],
            ];
            map.forEach(([id, v]) => {
                const el = document.getElementById(id);
                if (!el) return;
                el.textContent = (v == null || Number.isNaN(Number(v))) ? '--' : Number(v).toFixed(1) + '%';
            });
            const total = document.getElementById('tca-total');
            if (total) total.textContent = (data.avg_cost_bps == null || Number.isNaN(Number(data.avg_cost_bps))) ? '--' : Number(data.avg_cost_bps).toFixed(1) + ' bps';
            const verdict = document.getElementById('tca-verdict');
            if (verdict) verdict.textContent = data.verdict || '--';
        }

        // 后端暂无数据集质量汇总（仅 POST data-quality-check 需传入数据），真实模式清空静态演示评分
        function _clearDataQuality() {
            ['dq-completeness', 'dq-accuracy', 'dq-consistency', 'dq-timeliness', 'dq-uniqueness'].forEach(id => {
                const el = document.getElementById(id);
                if (el) el.textContent = '--';
            });
            ['dq-bar-completeness', 'dq-bar-accuracy', 'dq-bar-consistency', 'dq-bar-timeliness', 'dq-bar-uniqueness'].forEach(id => {
                const el = document.getElementById(id);
                if (el) el.style.width = '0%';
            });
            const score = document.getElementById('dq-overall-score');
            if (score) score.textContent = '--';
            const label = document.getElementById('dq-overall-label');
            if (label) label.textContent = '--';
        }

        // 后端暂无 L1 状态/分布占比/策略推荐与逐组件探针数据，真实模式清空静态演示
        function _clearRegimeAndHa() {
            const blank = (id, msg) => {
                const el = document.getElementById(id);
                if (el) el.innerHTML = `<div style="color: var(--text-secondary); font-size: 12px;">${msg}</div>`;
            };
            blank('l1-status-card', '暂无当前市场状态（待接真实行情识别）');
            blank('l1-regime-grid', '暂无状态分布占比');
            blank('l1-recommendation', '暂无策略推荐（待市场状态识别接入）');
            blank('ha-components', '暂无逐组件健康/延迟探针数据');
        }

        // 与引擎页 P2 监控卡片重复的旧 validation 静态面板：真实模式清空演示数字/列表
        function _clearLegacyMonitorPanels() {
            const blank = (id, msg) => {
                const el = document.getElementById(id);
                if (el) el.innerHTML = `<div style="color: var(--text-secondary); font-size: 12px;">${msg}</div>`;
            };
            blank('sec-old-grid', '暂无安全会话/密钥/审计统计（见引擎页监控卡片）');
            blank('crowd-old-list', '暂无策略拥挤度数据');
            blank('crowd-old-advice', '暂无拥挤度建议');
            blank('obs-old-grid', '暂无系统探针指标（延迟/错误率/CPU/内存）');
            blank('cicd-old-list', '暂无部署记录');
        }

        // 将后端 equityCurve 序列映射为 lightweight-charts 点（time=unix 秒，按时间升序去重）
        function _btCurvePoints(equityCurve, valueKey) {
            if (!Array.isArray(equityCurve)) return [];
            const seen = new Set();
            const pts = [];
            for (const p of equityCurve) {
                if (!p || p.time == null) continue;
                const t = Math.floor(Date.parse(p.time) / 1000);
                if (!Number.isFinite(t)) continue;
                const v = Number(p[valueKey]);
                if (!Number.isFinite(v)) continue;
                if (seen.has(t)) continue;
                seen.add(t);
                pts.push({ time: t, value: v });
            }
            pts.sort((a, b) => a.time - b.time);
            return pts;
        }

        // 拉取单条回测完整结果，渲染权益/回撤曲线；失败或无序列则清空空态
        async function _loadBacktestCurve(runId) {
            if (!runId) {
                initEquityChart([]);
                initDrawdownChart([]);
                return;
            }
            try {
                const res = await ApiService.getBacktestRun(runId);
                const result = (res && res.code === 1 && res.data && res.data.result) ? res.data.result : null;
                const equityPts = result ? _btCurvePoints(result.equityCurve, 'value') : [];
                const ddPts = result ? _btCurvePoints(result.equityCurve, 'drawdown') : [];
                initEquityChart(equityPts);
                initDrawdownChart(ddPts);
            } catch (e) {
                debugLog('回测曲线加载失败: ' + e.message, 'warn');
                initEquityChart([]);
                initDrawdownChart([]);
            }
        }

        async function loadBacktestResults() {
            const resultsPanel = document.getElementById('backtest-results');
            try {
                const resp = await ApiService.getBacktestHistory(20);
                const rows = (resp && resp.code === 1 && Array.isArray(resp.data)) ? resp.data : [];
                if (!rows.length) {
                    backtestIsReal = false;
                    _btBlankResults();
                    return;
                }
                backtestIsReal = true;
                // 真实模式：后端暂无逐策略绩效/月度收益，对比表与热力图清空为 --，静态演示样例不再混淆
                _clearComparisonTable();
                _clearMonthlyHeatmap();
                // 优先最近一条有成交结果的记录；history 已按 id 倒序，否则取第一条
                const row = rows.find(r => r.result_status === 'completed_trades') || rows[0];

                const retEl = document.getElementById('bt-total-return');
                const sharpeEl = document.getElementById('bt-sharpe');
                const ddEl = document.getElementById('bt-drawdown');
                const winEl = document.getElementById('bt-winrate');

                if (retEl) retEl.textContent = _btPct(row.total_return, { signed: true, digits: 2 });
                if (sharpeEl) sharpeEl.textContent = row.sharpe == null ? '--' : Number(row.sharpe).toFixed(2);
                if (ddEl) {
                    if (row.max_drawdown == null) {
                        ddEl.textContent = '--';
                    } else {
                        // 回撤统一展示为 -x.xx%；后端 maxDrawdown 为负数百分数，取绝对值恒带负号
                        const dd = Math.abs(Number(row.max_drawdown));
                        ddEl.textContent = '-' + dd.toFixed(2) + '%';
                    }
                }
                if (winEl) winEl.textContent = row.win_rate == null ? '--' : Number(row.win_rate).toFixed(1) + '%';
                if (resultsPanel) resultsPanel.classList.add('active');
                _loadBacktestCurve(row.id);
            } catch (e) {
                debugLog('回测历史加载失败: ' + e.message, 'error');
                backtestIsReal = false;
                _btBlankResults();
            }
        }

        async function runBacktest() {
            const btn = document.getElementById('run-backtest-btn');
            const btnText = document.getElementById('backtest-btn-text');

            if (btn) btn.disabled = true;
            if (btnText) btnText.innerHTML = '<span class="loading"></span> 加载中...';

            await loadBacktestResults();

            if (btn) btn.disabled = false;
            if (btnText) btnText.textContent = '刷新结果';
        }

        function initDrawdownChart(points) {
            const container = document.getElementById('drawdown-chart');
            if (!container) return;

            if (!drawdownChart) {
                const size = _chartSize(container, 919, 160);
                drawdownChart = LightweightCharts.createChart(container, {
                    layout: {
                        background: { color: 'transparent' },
                        textColor: '#848e9c',
                    },
                    grid: {
                        vertLines: { color: '#1e2329' },
                        horzLines: { color: '#1e2329' },
                    },
                    width: size.width,
                    height: size.height,
                });

                drawdownSeries = drawdownChart.addAreaSeries({
                    lineColor: '#f6465d',
                    topColor: 'rgba(246, 70, 93, 0.3)',
                    bottomColor: 'rgba(246, 70, 93, 0.0)',
                    lineWidth: 2,
                });
            }

            drawdownChart.applyOptions(_chartSize(container, 919, 160));
            drawdownSeries.setData(Array.isArray(points) ? points : []);
        }

        // ========== 日志中心 ==========
        function initLogCenter() {
            // 日志中心三类：decision 决策日志 / trade 交易日志 / system 系统日志
            let logKind = 'decision';
            let logStrategyId = '';
            let decisionLogs = [];
            let tradeLogs = [];
            let logError = '';

            const LOG_LEVEL_COLORS = {
                error: '#f6465d', warn: '#f0b90b', warning: '#f0b90b',
                info: '#8b5cf6', success: '#0ecb81'
            };

            function _logFmtTime(ts) {
                if (ts == null || ts === '') return '--';
                const d = new Date(typeof ts === 'number' ? ts * 1000 : ts);
                if (isNaN(d.getTime())) return String(ts);
                return d.toLocaleString('zh-CN', { hour12: false });
            }
            function _logSideLabel(t) {
                const v = String(t || '').toLowerCase();
                if (v === 'buy' || v === 'long') return '多';
                if (v === 'sell' || v === 'short') return '空';
                if (v === 'close' || v === 'exit' || v === 'flat') return '平仓';
                return v || '--';
            }
            function _normLevel(level) {
                const s = String(level || 'info').toLowerCase();
                return s === 'warning' ? 'warn' : s;
            }
            function _logNum(v) { const n = parseFloat(v); return isNaN(n) ? null : n; }

            async function loadLogStrategies() {
                const sel = document.getElementById('log-strategy-select');
                if (!sel) return;
                const res = await ApiService.getStrategies();
                let list = [];
                if (res && Array.isArray(res.data)) list = res.data;
                else if (res && res.data && Array.isArray(res.data.items)) list = res.data.items;
                if (!list.length) { sel.innerHTML = '<option value="">暂无可用策略</option>'; return; }
                sel.innerHTML = '<option value="">请选择策略</option>' + list.map(s => {
                    const id = s.id;
                    const name = s.strategy_name || s.name || '未命名策略';
                    return `<option value="${id}">${name}</option>`;
                }).join('');
            }

            async function refreshKindLogs() {
                if (logKind === 'system') { renderLogList(); return; }
                // 风控事件：无结构化事件源（G1/G2/G3，C-LOG-01），固定空态，不拉取演示数据
                if (logKind === 'risk') {
                    decisionLogs = []; tradeLogs = []; logError = ''; renderLogList(); return;
                }
                if (!logStrategyId) {
                    decisionLogs = []; tradeLogs = []; logError = ''; renderLogList(); return;
                }
                logError = '';
                if (logKind === 'decision') {
                    const res = await ApiService.getStrategyLogs(logStrategyId, 200);
                    if (res && res._unauthorized) { decisionLogs = []; renderLogList(); return; }
                    if (!res || res.code !== 1 || res._error) {
                        logError = (res && res.msg) || '决策日志加载失败'; decisionLogs = []; renderLogList(); return;
                    }
                    decisionLogs = Array.isArray(res.data) ? res.data : [];
                } else {
                    const res = await ApiService.getStrategyTrades(logStrategyId);
                    if (res && res._unauthorized) { tradeLogs = []; renderLogList(); return; }
                    const arr = (res && res.data && (res.data.trades || res.data.items)) || [];
                    if (!res || res.code !== 1 || res._error) {
                        logError = (res && res.msg) || '交易日志加载失败'; tradeLogs = []; renderLogList(); return;
                    }
                    tradeLogs = Array.isArray(arr) ? arr : [];
                }
                renderLogList();
            }

            function _currentEntries() {
                if (logKind === 'decision') return decisionLogs;
                if (logKind === 'trade') return tradeLogs;
                if (logKind === 'risk') return [];
                return window.debugLogs || [];
            }

            function _filterEntries(entries, filter, search) {
                let out = entries.slice();
                if (filter !== 'all') {
                    out = out.filter(e => {
                        const lv = logKind === 'system' ? String(e.type || '').toLowerCase() : _normLevel(e.level);
                        return lv === filter;
                    });
                }
                if (search) {
                    const s = search.toLowerCase();
                    out = out.filter(e => {
                        let text;
                        if (logKind === 'system') text = String(e.msg || '');
                        else if (logKind === 'trade') text = `${e.symbol||''} ${e.type||''} ${e.close_reason||''} ${e.price||''} ${e.amount||''}`;
                        else text = String(e.message || '');
                        return text.toLowerCase().includes(s);
                    });
                }
                return out;
            }

            function _renderHeader() {
                const header = document.getElementById('log-list-header');
                if (!header) return;
                if (logKind === 'trade') {
                    header.innerHTML = `
                        <div style="width:150px;">时间</div>
                        <div style="width:70px;margin-left:16px;">方向</div>
                        <div style="width:130px;margin-left:16px;">品种</div>
                        <div style="width:110px;margin-left:16px;">价格</div>
                        <div style="width:100px;margin-left:16px;">数量</div>
                        <div style="width:110px;margin-left:16px;">盈亏</div>
                        <div style="flex:1;margin-left:16px;">平仓原因</div>`;
                } else if (logKind === 'decision') {
                    header.innerHTML = `
                        <div style="width:150px;">时间</div>
                        <div style="width:70px;margin-left:16px;">级别</div>
                        <div style="flex:1;margin-left:16px;">决策消息</div>`;
                } else if (logKind === 'risk') {
                    header.innerHTML = `
                        <div style="width:150px;">时间</div>
                        <div style="width:70px;margin-left:16px;">级别</div>
                        <div style="flex:1;margin-left:16px;">风控事件 / 拦截原因</div>`;
                } else {
                    header.innerHTML = `
                        <div style="width:150px;">时间</div>
                        <div style="width:70px;margin-left:16px;">级别</div>
                        <div style="flex:1;margin-left:16px;">消息内容</div>`;
                }
            }

            function _renderDecisionRow(e) {
                const lv = _normLevel(e.level);
                const color = LOG_LEVEL_COLORS[lv] || '#848e9c';
                return `
                    <div style="padding:8px 12px;border-bottom:1px solid var(--bg-border);display:flex;align-items:center;">
                        <div style="width:150px;color:var(--text-secondary);">${_logFmtTime(e.timestamp)}</div>
                        <div style="width:70px;margin-left:16px;">
                            <span style="padding:2px 6px;background:${color}20;color:${color};border-radius:3px;font-size:11px;font-weight:600;">${lv.toUpperCase()}</span>
                        </div>
                        <div style="flex:1;margin-left:16px;color:var(--text-primary);">${e.message || '--'}</div>
                    </div>`;
            }

            function _renderTradeRow(e) {
                const pnl = (e.net_pnl != null) ? _logNum(e.net_pnl) : _logNum(e.profit);
                const pnlTxt = pnl === null ? '--' : ((pnl >= 0 ? '+' : '') + pnl.toFixed(2));
                const pnlColor = pnl === null ? 'var(--text-secondary)' : (pnl >= 0 ? '#0ecb81' : '#f6465d');
                const price = _logNum(e.price);
                const amount = _logNum(e.amount);
                return `
                    <div style="padding:8px 12px;border-bottom:1px solid var(--bg-border);display:flex;align-items:center;">
                        <div style="width:150px;color:var(--text-secondary);">${_logFmtTime(e.created_at)}</div>
                        <div style="width:70px;margin-left:16px;">${_logSideLabel(e.type)}</div>
                        <div style="width:130px;margin-left:16px;color:var(--text-primary);">${e.symbol || '--'}</div>
                        <div style="width:110px;margin-left:16px;">${price === null ? '--' : price.toLocaleString()}</div>
                        <div style="width:100px;margin-left:16px;">${amount === null ? '--' : amount}</div>
                        <div style="width:110px;margin-left:16px;color:${pnlColor};">${pnlTxt}</div>
                        <div style="flex:1;margin-left:16px;color:var(--text-secondary);">${e.close_reason || '--'}</div>
                    </div>`;
            }

            function _renderSystemRow(log) {
                const color = LOG_LEVEL_COLORS[log.type] || '#848e9c';
                return `
                    <div style="padding:8px 12px;border-bottom:1px solid var(--bg-border);display:flex;align-items:center;">
                        <div style="width:150px;color:var(--text-secondary);">${log.time}</div>
                        <div style="width:70px;margin-left:16px;">
                            <span style="padding:2px 6px;background:${color}20;color:${color};border-radius:3px;font-size:11px;font-weight:600;">${String(log.type||'').toUpperCase()}</span>
                        </div>
                        <div style="flex:1;margin-left:16px;color:var(--text-primary);">${log.msg}</div>
                    </div>`;
            }

            function _updateStats(all) {
                const lvOf = e => logKind === 'system' ? String(e.type||'').toLowerCase() : _normLevel(e.level);
                document.getElementById('log-total').textContent = all.length;
                document.getElementById('log-error-count').textContent = all.filter(e => lvOf(e) === 'error').length;
                document.getElementById('log-warn-count').textContent = all.filter(e => lvOf(e) === 'warn').length;
                const apiCount = document.getElementById('log-api-count');
                const apiLabel = document.getElementById('log-api-label');
                if (logKind === 'system') {
                    apiCount.textContent = all.filter(l => String(l.msg || '').includes('API')).length;
                    apiLabel.textContent = 'API请求数';
                } else if (logKind === 'decision') {
                    apiCount.textContent = all.length;
                    apiLabel.textContent = '决策记录';
                } else if (logKind === 'risk') {
                    apiCount.textContent = 0;
                    apiLabel.textContent = '风控事件';
                } else {
                    apiCount.textContent = all.length;
                    apiLabel.textContent = '成交笔数';
                }
            }

            window.renderLogList = function(filter = 'all', search = '') {
                const logList = document.getElementById('log-list');
                if (!logList) return;
                const all = _currentEntries();
                const filtered = _filterEntries(all, filter, search);
                _renderHeader();
                _updateStats(all);

                if (logError) {
                    logList.innerHTML = `<div style="padding:12px;color:#f6465d;text-align:center;font-size:13px;">${logError}</div>`;
                    return;
                }
                if (logKind === 'risk') {
                    logList.innerHTML = '<div style="padding:12px;color:var(--text-secondary);text-align:center;font-size:12px;line-height:1.8;">暂无结构化风控事件：后端无独立风控事件表、拒单原因未结构化、无拦截计数落库（缺口 G1/G2/G3，契约 C-LOG-01 / C-RISK-03）；违规码仅落在 pending_orders.last_error 与决策日志 message 文本，落地前不解析文本猜测违规码。</div>';
                    return;
                }
                if (logKind !== 'system' && !logStrategyId) {
                    logList.innerHTML = '<div style="padding:8px 12px;color:var(--text-secondary);text-align:center;">请选择策略后查看决策 / 交易日志</div>';
                    return;
                }
                if (filtered.length === 0) {
                    logList.innerHTML = '<div style="padding:8px 12px;color:var(--text-secondary);text-align:center;">暂无日志</div>';
                    return;
                }
                const rows = filtered.slice().reverse();
                if (logKind === 'decision') logList.innerHTML = rows.map(_renderDecisionRow).join('');
                else if (logKind === 'trade') logList.innerHTML = rows.map(_renderTradeRow).join('');
                else logList.innerHTML = rows.map(_renderSystemRow).join('');
            };

            function _syncKindUI() {
                const tabs = document.querySelectorAll('#log-kind-tabs button');
                tabs.forEach(b => {
                    const active = b.dataset.kind === logKind;
                    b.style.background = active ? '#f0b90b' : 'var(--bg-secondary)';
                    b.style.color = active ? '#0b0e11' : 'var(--text-primary)';
                    b.style.borderColor = active ? '#f0b90b' : 'var(--bg-border)';
                });
                const sel = document.getElementById('log-strategy-select');
                if (sel) sel.style.display = (logKind === 'system' || logKind === 'risk') ? 'none' : '';
                const clearBtn = document.getElementById('log-clear');
                if (clearBtn) {
                    clearBtn.disabled = logKind !== 'system';
                    clearBtn.style.opacity = logKind === 'system' ? '1' : '0.5';
                }
            }

            window.refreshLogCenter = refreshKindLogs;

            const tabs = document.querySelectorAll('#log-kind-tabs button');
            tabs.forEach(btn => {
                btn.onclick = function() {
                    logKind = btn.dataset.kind;
                    _syncKindUI();
                    refreshKindLogs();
                };
            });

            const strategySel = document.getElementById('log-strategy-select');
            if (strategySel) {
                strategySel.onchange = function() {
                    logStrategyId = this.value;
                    refreshKindLogs();
                };
            }

            const filterSelect = document.getElementById('log-level-filter');
            if (filterSelect) {
                filterSelect.onchange = function() {
                    const search = document.getElementById('log-search').value;
                    window.renderLogList(this.value, search);
                };
            }

            const searchInput = document.getElementById('log-search');
            if (searchInput) {
                searchInput.oninput = function() {
                    const filter = document.getElementById('log-level-filter').value;
                    window.renderLogList(filter, this.value);
                };
            }

            const clearBtn = document.getElementById('log-clear');
            if (clearBtn) {
                clearBtn.onclick = function() {
                    if (logKind !== 'system') return;
                    window.debugLogs = [];
                    window.renderLogList();
                    debugLog('日志已清空', 'info');
                };
            }

            const exportBtn = document.getElementById('log-export');
            if (exportBtn) {
                exportBtn.onclick = function() {
                    const filter = document.getElementById('log-level-filter').value;
                    const search = document.getElementById('log-search').value;
                    const entries = _filterEntries(_currentEntries(), filter, search);
                    let text;
                    if (logKind === 'trade') {
                        text = entries.map(e => `[${_logFmtTime(e.created_at)}] [${_logSideLabel(e.type)}] ${e.symbol||''} px=${e.price||''} amt=${e.amount||''} pnl=${e.net_pnl!=null?e.net_pnl:e.profit} reason=${e.close_reason||''}`).join('\n');
                    } else if (logKind === 'decision') {
                        text = entries.map(e => `[${_logFmtTime(e.timestamp)}] [${_normLevel(e.level).toUpperCase()}] ${e.message||''}`).join('\n');
                    } else if (logKind === 'risk') {
                        text = '暂无结构化风控事件（缺口 G1/G2/G3，契约 C-LOG-01 / C-RISK-03）';
                    } else {
                        text = entries.map(l => `[${l.time}] [${String(l.type||'').toUpperCase()}] ${l.msg}`).join('\n');
                    }
                    const blob = new Blob([text], { type: 'text/plain' });
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = `quantdinger-${logKind}-logs-${new Date().toISOString().slice(0,10)}.txt`;
                    a.click();
                    URL.revokeObjectURL(url);
                    debugLog('日志已导出', 'success');
                };
            }

            _syncKindUI();
            loadLogStrategies();
        }

        // ========== 数据加载 ==========
        async function loadAllData() {
            try {
                const [credentialsRes, summaryRes, strategiesRes, positionsRes] = await Promise.all([
                    ApiService.getCredentials(),
                    ApiService.getDashboardSummary(),
                    ApiService.getStrategies(),
                    ApiService.getPositions()
                ]);

                // 检查是否未登录
                const anyUnauthorized = credentialsRes._unauthorized || summaryRes._unauthorized;
                if (anyUnauthorized) {
                    updateSystemStatus('unauthorized');
                    _setDemoGlobalBadge(true);
                    showToast('请先登录系统', 'warning');
                    // 未登录时使用演示数据
                    updateAccountsList([], false);
                    updateDashboardStats({}, false);
                    updateStrategiesList([], false);
                    updateTradesList([], false);
                    return;
                }

                // 自建后端 credentials/list 返回 {code:1,data:{items:[...]}}，需取 items
                const credData = credentialsRes.data || [];
                const credList = Array.isArray(credData) ? credData : (Array.isArray(credData.items) ? credData.items : []);
                updateAccountsList(credList, !credentialsRes._error && credentialsRes.code === 1);
                updateDashboardStats(summaryRes.data || {}, !summaryRes._error && summaryRes.code === 1);
                updateStrategiesList(strategiesRes.data || [], !strategiesRes._error && strategiesRes.code === 1);
                updatePositionsList(positionsRes.data || [], !positionsRes._error && positionsRes.code === 1);
                updateTradesList((summaryRes.data || {}).recent_trades || [], !summaryRes._error && summaryRes.code === 1);

                // 登录态下任一核心接口非真实（全挂/异常）才挂演示哨兵；全部真实回填则隐藏
                const coreReal = !credentialsRes._error && credentialsRes.code === 1 &&
                    !summaryRes._error && summaryRes.code === 1;
                _setDemoGlobalBadge(!coreReal);
                updateSystemStatus('online');
            } catch (e) {
                debugLog(`数据加载失败: ${e.message}`, 'error');
                _setDemoGlobalBadge(true);
                updateSystemStatus('offline');
                updateAccountsList([], false);
                updateDashboardStats({}, false);
                updateTradesList([], false);
            }
        }

        // 全局演示数据哨兵：仅未登录 / 接口全挂（非真实）时上屏；真实登录态一律隐藏
        function _setDemoGlobalBadge(show) {
            const el = document.getElementById('demo-global-badge');
            if (el) el.style.display = show ? 'inline-block' : 'none';
        }

        function updateSystemStatus(status) {
            const el = document.getElementById('system-status');
            if (!el) return;
            const statusMap = {
                'online': { text: '● 系统正常', color: 'var(--up-color)' },
                'offline': { text: '● 离线模式', color: 'var(--warning-color)' },
                'unauthorized': { text: '● 未登录', color: 'var(--down-color)' }
            };
            const s = statusMap[status] || statusMap['offline'];
            el.textContent = s.text;
            el.style.color = s.color;
        }

        function _credEnvLabel(cred) {
            const env = String(cred.environment || '').toLowerCase();
            if (env === 'demo') return '模拟盘';
            if (env === 'live') return '实盘';
            return cred.enable_demo_trading ? '模拟盘' : '已连接';
        }

        function updateAccountsList(credentials, isReal = false) {
            const accountsList = document.getElementById('accounts-list');
            const modalAccountsList = document.getElementById('modal-accounts-list');
            const navEl = document.getElementById('nav-account-name');

            // 仅未登录 / 接口全挂（非真实）时保留演示兜底；真实模式空凭证走空态，不编演示哨兵
            let demoFallback = [];
            if (!isReal) {
                demoFallback = [{
                    id: 1,
                    name: 'OKX-DEMO',
                    exchange_id: 'okx',
                    api_key_hint: '8a12...0cf2',
                    environment: 'demo'
                }];
            }
            const emptyHtml = '<div style="padding:8px;color:var(--text-tertiary);font-size:12px;">暂无已连接交易账户</div>';

            if (!credentials || credentials.length === 0) {
                const showDemo = !isReal && demoFallback.length;
                const list = showDemo ? demoFallback : [];
                // 顶栏账户名：真实模式无凭证显示 --，不残留写死的「OKX-DEMO 已连接」
                if (navEl) navEl.textContent = list.length ? 'OKX-DEMO 已连接' : '--';
                const render = (cred) => `
                    <div class="account-option" style="padding:10px;border-radius:6px;cursor:pointer;display:flex;align-items:center;justify-content:space-between;margin-bottom:4px;${showDemo ? 'background:var(--bg-hover);' : ''}">
                        <div style="display:flex;align-items:center;gap:10px;">
                            <span style="padding:3px 6px;border-radius:4px;background:var(--brand-primary);color:var(--bg-primary);font-size:10px;font-weight:700;text-transform:uppercase;">${cred.exchange_id || '--'}</span>
                            <div>
                                <div style="font-size:13px;">${cred.name || '--'}</div>
                                <div style="font-size:11px;color:var(--text-secondary);">${cred.api_key_hint || _credEnvLabel(cred)}</div>
                            </div>
                        </div>
                        <div class="status-dot" style="width:6px;height:6px;"></div>
                    </div>`;
                const html = list.length ? list.map(render).join('') : emptyHtml;
                if (accountsList) accountsList.innerHTML = html;
                if (modalAccountsList) modalAccountsList.innerHTML = html;
                return;
            }

            accountsList.innerHTML = credentials.map((cred, idx) => `
                <div class="account-option ${idx === 0 ? 'selected' : ''}" style="padding: 10px; border-radius: 6px; cursor: pointer; display: flex; align-items: center; justify-content: space-between; margin-bottom: 4px; ${idx === 0 ? 'background: var(--bg-hover);' : ''}">
                    <div style="display: flex; align-items: center; gap: 10px;">
                        <span style="padding: 3px 6px; border-radius: 4px; background: var(--brand-primary); color: var(--bg-primary); font-size: 10px; font-weight: 700; text-transform: uppercase;">${cred.exchange_id || '--'}</span>
                        <div>
                            <div style="font-size: 13px;">${cred.name || '--'}</div>
                            <div style="font-size: 11px; color: var(--text-secondary);">${cred.api_key_hint || _credEnvLabel(cred)}</div>
                        </div>
                    </div>
                    <div class="status-dot" style="width: 6px; height: 6px;"></div>
                </div>
            `).join('');

            modalAccountsList.innerHTML = credentials.map((cred, idx) => `
                <div class="credential-option ${idx === 0 ? 'selected' : ''}" style="padding: 12px; border-radius: 6px; cursor: pointer; display: flex; align-items: center; justify-content: space-between; margin-bottom: 4px; ${idx === 0 ? 'background: var(--bg-active);' : ''}">
                    <div style="display: flex; align-items: center; gap: 12px;">
                        <span style="padding: 4px 8px; border-radius: 4px; background: var(--brand-primary); color: var(--bg-primary); font-size: 11px; font-weight: 700; text-transform: uppercase;">${cred.exchange_id || '--'}</span>
                        <div>
                            <div style="font-weight: 600; font-size: 14px;">${cred.name || '--'}</div>
                            <div style="font-size: 11px; color: var(--text-secondary);">${cred.api_key_hint || _credEnvLabel(cred)}</div>
                        </div>
                    </div>
                    <div class="status-dot" style="width: 8px; height: 8px;"></div>
                </div>
            `).join('');

            if (navEl) navEl.textContent = credentials[0] ? `${credentials[0].name || '--'} ${_credEnvLabel(credentials[0])}` : '--';
        }

        function updateDashboardStats(summary, isReal = false) {
            // 真实模式：total-equity 唯一来源为 loadRealPositions（OKX 实时权益），
            // 避免把 summary 的演示哨兵（5000/空）写回造成权益闪变；仅未登录/接口全挂时用演示兜底。
            if (!isReal) {
                if (summary.total_equity) {
                    document.getElementById('total-equity').textContent = 
                        summary.total_equity.toLocaleString('en-US', {minimumFractionDigits: 2});
                } else {
                    document.getElementById('total-equity').textContent = '10,234.56';
                }
            }
            
            // daily_pnl 为 0 也是真实值（今日无平仓盈亏），必须渲染而非回退演示占位
            if (summary.daily_pnl !== undefined && summary.daily_pnl !== null) {
                const el = document.getElementById('daily-pnl');
                const dpnl = Number(summary.daily_pnl) || 0;
                el.textContent = (dpnl >= 0 ? '+' : '') + dpnl.toFixed(2);
                el.style.color = dpnl >= 0 ? 'var(--up-color)' : 'var(--down-color)';
            } else if (!isReal) {
                document.getElementById('daily-pnl').textContent = '+123.45';
                document.getElementById('daily-pnl').style.color = 'var(--up-color)';
            } else {
                const el = document.getElementById('daily-pnl');
                if (el) { el.textContent = '--'; el.style.color = ''; }
            }

            // 交易/胜率/盈亏比/回撤/夏普均来自后端 performance 嵌套字段；
            // 真实模式下 0 或缺失显示真实 0 / "--"，禁止用演示占位数字顶替（E001/E003 教训）。
            const perf = summary.performance || {};

            const tradesEl = document.getElementById('stat-trades');
            if (perf.total_trades !== undefined && perf.total_trades !== null) {
                tradesEl.textContent = perf.total_trades;
            } else if (!isReal) {
                tradesEl.textContent = '12';
            } else {
                tradesEl.textContent = '--';
            }

            const winEl = document.getElementById('stat-winrate');
            if (perf.win_rate !== undefined && perf.win_rate !== null) {
                winEl.textContent = Number(perf.win_rate).toFixed(1) + '%';
            } else if (!isReal) {
                winEl.textContent = '66.7%';
            } else {
                winEl.textContent = '--';
            }

            const plEl = document.getElementById('stat-plratio');
            if (perf.profit_factor !== undefined && perf.profit_factor !== null) {
                plEl.textContent = Number(perf.profit_factor).toFixed(2);
            } else if (!isReal) {
                plEl.textContent = '1.85';
            } else {
                plEl.textContent = '--';
            }

            const ddEl = document.getElementById('stat-drawdown');
            if (perf.max_drawdown_pct !== undefined && perf.max_drawdown_pct !== null) {
                const ddVal = Number(perf.max_drawdown_pct);
                ddEl.textContent = ddVal > 0 ? '-' + ddVal.toFixed(2) + '%' : '0.00%';
            } else if (!isReal) {
                ddEl.textContent = '-3.2%';
            } else {
                ddEl.textContent = '--';
            }

            // 夏普：后端样本不足/零波动返回 null，前端展示 "--"，不编占位 1.85
            const sharpeEl = document.getElementById('stat-sharpe');
            if (perf.sharpe !== undefined && perf.sharpe !== null) {
                sharpeEl.textContent = Number(perf.sharpe).toFixed(2);
            } else if (!isReal) {
                sharpeEl.textContent = '1.85';
            } else {
                sharpeEl.textContent = '--';
            }
        }

        function updateStrategiesList(strategies, isReal = false) {
            const runningEl = document.getElementById('running-strategies');
            const gridEl = document.getElementById('strategies-grid');

            // 不是真实数据（未登录/接口挂）时使用演示兜底；真实模式空策略渲染空态，不编造示例
            const isEmpty = !strategies || strategies.length === 0;
            if (!isReal && isEmpty) {
                strategies = [
                    { id: 1, name: 'ML增强趋势策略', status: 'running', today_pnl: 45.67, win_rate: 65, sharpe: 1.85, max_drawdown: 3.2, total_trades: 45 },
                    { id: 2, name: '均值回归策略', status: 'running', today_pnl: -12.34, win_rate: 58, sharpe: 1.42, max_drawdown: 4.8, total_trades: 128 },
                    { id: 3, name: '突破策略', status: 'stopped', today_pnl: 0, win_rate: 0, sharpe: 0, max_drawdown: 0, total_trades: 0 }
                ];
            } else if (isReal && isEmpty) {
                const emptyHtml = '<div style="padding: 8px; color: var(--text-tertiary); font-size: 12px;">暂无策略</div>';
                if (runningEl) runningEl.innerHTML = emptyHtml;
                if (gridEl) gridEl.innerHTML = emptyHtml;
                return;
            }

            // 智能字段映射：兼容后端不同字段名
            strategies = strategies.map(s => ({
                ...s,
                name: s.name || s.strategy_name || '未命名策略',
                status: s.status || s.execution_mode === 'live' ? 'running' : 'stopped',
                today_pnl: s.today_pnl ?? s.daily_pnl ?? s.pnl_today ?? null,
                win_rate: s.win_rate ?? s.winrate ?? null,
                sharpe: s.sharpe ?? s.sharpe_ratio ?? null,
                max_drawdown: s.max_drawdown ?? s.drawdown ?? null,
                total_trades: s.total_trades ?? s.trade_count ?? null
            }));

            const runningStrategies = strategies.filter(s => s.status === 'running');

            runningEl.innerHTML = runningStrategies.map((s, idx) => `
                <div class="strategy-card running" onclick='openStrategyDetail(${JSON.stringify(s).replace(/'/g, "&apos;")})'>
                    <div class="strategy-header">
                        <span class="strategy-name">${s.name}</span>
                        <span class="strategy-status running">运行中</span>
                    </div>
                    <div class="strategy-metrics">
                        <span>今日: ${s.today_pnl == null ? '--' : (s.today_pnl >= 0 ? '+' : '') + s.today_pnl.toFixed(2)}</span>
                        <span>胜率: ${s.win_rate == null ? '--' : s.win_rate.toFixed(0) + '%'}</span>
                    </div>
                </div>
            `).join('');

            gridEl.innerHTML = strategies.map(s => `
                <div class="strategy-card ${s.status || 'stopped'}" onclick='openStrategyDetail(${JSON.stringify(s).replace(/'/g, "&apos;")})'>
                    <div class="strategy-header">
                        <span class="strategy-name">${s.name}</span>
                        <span class="strategy-status ${s.status || 'stopped'}">${s.status === 'running' ? '运行中' : '已停止'}</span>
                    </div>
                    <div style="font-size: 12px; color: var(--text-secondary); margin-bottom: 12px;">${s.description || '暂无描述'}</div>
                    <div class="strategy-metrics">
                        <span>夏普: ${s.sharpe == null ? '--' : s.sharpe.toFixed(2)}</span>
                        <span>回撤: ${s.max_drawdown == null ? '--' : s.max_drawdown.toFixed(1) + '%'}</span>
                        <span>交易: ${s.total_trades == null ? '--' : s.total_trades}</span>
                    </div>
                </div>
            `).join('');
        }

        function updatePositionsList(positions, isReal = false) {
            const el = document.getElementById('positions-list');
            if (!el) return;
            if (!positions || positions.length === 0) {
                // 真实数据模式：空持仓就是空，禁止编造示例数字（E001/E003 教训：模拟数据=对接失败）
                if (isReal) {
                    el.innerHTML = '<div style="padding: 8px; color: var(--text-tertiary); font-size: 12px;">暂无持仓</div>';
                    return;
                }
                // 演示模式：使用示例数据
                positions = [
                    { symbol: 'BTC/USDT', amount: 0.5, entry_price: 42000, pnl: 234.56 },
                    { symbol: 'ETH/USDT', amount: 2.0, entry_price: 2300, pnl: -45.67 }
                ];
            }
            el.innerHTML = positions.map(p => `
                <div class="position-item">
                    <div class="position-header">
                        <span class="position-symbol">${p.symbol}</span>
                        <span class="position-pnl ${p.pnl >= 0 ? 'up' : 'down'}">${p.pnl >= 0 ? '+' : ''}${p.pnl.toFixed(2)}</span>
                    </div>
                    <div class="position-details">
                        <span>${p.amount} ${p.symbol.split('/')[0]}</span>
                        <span>$${p.entry_price.toLocaleString()}</span>
                    </div>
                </div>
            `).join('');
        }

        function updateTradesList(trades, isReal = false) {
            const el = document.getElementById('trades-list');
            if (!el) return;
            // 真实空态就是空，不编造示例成交（E001/E003 教训：模拟数据=对接失败）
            if (!trades || trades.length === 0) {
                el.innerHTML = '<div style="padding: 8px; color: var(--text-tertiary); font-size: 12px;">暂无成交</div>';
                return;
            }

            const fmtTime = (ts) => {
                const n = Number(ts) || 0;
                if (n <= 0) return '--';
                const d = new Date(n * (n < 1e12 ? 1000 : 1));
                const mm = String(d.getMonth() + 1).padStart(2, '0');
                const dd = String(d.getDate()).padStart(2, '0');
                const hh = String(d.getHours()).padStart(2, '0');
                const mi = String(d.getMinutes()).padStart(2, '0');
                return `${mm}-${dd} ${hh}:${mi}`;
            };
            const sideLabel = (t) => {
                const v = String(t || '').toLowerCase();
                if (v === 'buy' || v === 'long') return '多';
                if (v === 'sell' || v === 'short') return '空';
                if (v === 'close' || v === 'exit' || v === 'flat') return '平仓';
                return v || '--';
            };

            el.innerHTML = trades.map(t => {
                const pnl = (t.net_pnl !== undefined && t.net_pnl !== null) ? Number(t.net_pnl)
                          : (t.profit !== undefined && t.profit !== null ? Number(t.profit) : null);
                const pnlCls = pnl === null ? '' : (pnl >= 0 ? 'up' : 'down');
                const pnlTxt = pnl === null ? '--' : ((pnl >= 0 ? '+' : '') + pnl.toFixed(2));
                const sym = t.symbol || '--';
                const price = Number(t.price) || 0;
                const amount = Number(t.amount) || 0;
                const strat = t.strategy_name || '';
                return `
                    <div class="position-item">
                        <div class="position-header">
                            <span class="position-symbol">${sym}</span>
                            <span class="position-pnl ${pnlCls}">${pnlTxt}</span>
                        </div>
                        <div class="position-details">
                            <span>${sideLabel(t.type)} · ${amount}</span>
                            <span>$${price.toLocaleString()}</span>
                        </div>
                        <div class="position-details" style="margin-top:2px;">
                            <span style="color: var(--text-tertiary);">${strat || '--'}</span>
                            <span style="color: var(--text-tertiary);">${fmtTime(t.created_at)}</span>
                        </div>
                    </div>`;
            }).join('');
        }

        // ========== 窗口大小调整 ==========
        window.addEventListener('resize', () => {
            if (mainChart) {
                const container = document.getElementById('main-chart');
                mainChart.applyOptions({
                    width: container.clientWidth,
                    height: container.clientHeight
                });
            }
            if (equityChart) {
                const container = document.getElementById('equity-chart');
                equityChart.applyOptions(_chartSize(container, 919, 400));
            }
            if (drawdownChart) {
                const container = document.getElementById('drawdown-chart');
                drawdownChart.applyOptions(_chartSize(container, 919, 160));
            }
        });

        // ========== 认证管理 ==========
        const Auth = {
            TOKEN_KEY: 'qd_token',
            USER_KEY: 'qd_user',
            
            getToken() {
                return localStorage.getItem(this.TOKEN_KEY);
            },
            
            setToken(token) {
                localStorage.setItem(this.TOKEN_KEY, token);
            },
            
            getUser() {
                const u = localStorage.getItem(this.USER_KEY);
                return u ? JSON.parse(u) : null;
            },
            
            setUser(user) {
                localStorage.setItem(this.USER_KEY, JSON.stringify(user));
            },
            
            isLoggedIn() {
                return !!this.getToken();
            },
            
            logout() {
                localStorage.removeItem(this.TOKEN_KEY);
                localStorage.removeItem(this.USER_KEY);
                this.showLogin();
            },
            
            showLogin() {
                document.getElementById('login-page').style.display = 'flex';
                document.getElementById('main-app').style.display = 'none';
            },
            
            showMain() {
                document.getElementById('login-page').style.display = 'none';
                document.getElementById('main-app').style.display = 'block';
            },
            
            async login(username, password) {
                try {
                    debugLog(`尝试登录: ${username}`, 'info');
                    const res = await fetch('/api/auth/login', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ username, password })
                    });
                    const data = await res.json();
                    if (data.code === 1 && data.data.token) {
                        this.setToken(data.data.token);
                        this.setUser(data.data.userinfo);
                        debugLog(`登录成功: ${data.data.userinfo.username}`, 'success');
                        _setDemoGlobalBadge(false);
                        this.showMain();
                        loadAllData();
                        return true;
                    } else {
                        debugLog(`登录失败: ${data.msg}`, 'error');
                        return false;
                    }
                } catch (e) {
                    debugLog(`登录请求失败: ${e.message}`, 'error');
                    return false;
                }
            }
        };

        // ========== API请求拦截器（自动添加token） ==========
        const originalFetch2 = window.fetch;
        window.fetch = async function(url, options = {}) {
            // 跳过登录接口本身
            if (!url.includes('/api/auth/login')) {
                const token = Auth.getToken();
                if (token) {
                    options.headers = { ...options.headers, 'Authorization': `Bearer ${token}` };
                }
            }
            const response = await originalFetch2(url, options);
            // 401自动跳转登录
            if (response.status === 401 && !url.includes('/api/auth/login')) {
                debugLog('Token失效，跳转到登录页', 'warn');
                Auth.logout();
            }
            return response;
        };

        // ========== 登录按钮事件 ==========
        document.getElementById('login-btn').addEventListener('click', async () => {
            const username = document.getElementById('login-username').value.trim();
            const password = document.getElementById('login-password').value.trim();
            const errorEl = document.getElementById('login-error');
            const statusEl = document.getElementById('login-status');
            
            if (!username || !password) {
                errorEl.textContent = '请输入用户名和密码';
                errorEl.style.display = 'block';
                return;
            }
            
            const btn = document.getElementById('login-btn');
            btn.disabled = true;
            btn.textContent = '登录中...';
            errorEl.style.display = 'none';
            statusEl.textContent = '正在验证身份...';
            
            const success = await Auth.login(username, password);
            
            btn.disabled = false;
            btn.textContent = '登 录';
            
            if (!success) {
                errorEl.textContent = '用户名或密码错误';
                errorEl.style.display = 'block';
                statusEl.textContent = '';
            }
        });

        // 回车登录
        document.getElementById('login-password').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                document.getElementById('login-btn').click();
            }
        });

        // ========== AI验证层数据加载 ==========
        async function loadValidationData() {
            debugLog('加载AI验证层数据', 'info');
            try {
                // 加载验证模块状态
                const statusRes = await fetch('/api/validation/status', {
                    headers: { 'Authorization': 'Bearer ' + Auth.getToken() }
                });
                if (!statusRes.ok) throw new Error('API返回' + statusRes.status);
                const statusData = await statusRes.json();
                if (statusData.code === 1 && statusData.data) {
                    renderValidationModules(statusData.data.modules);
                    renderDriftMonitor(statusData.data.modules);
                    // 后端暂无逐策略健康度绩效，真实模式清空静态演示卡片
                    _clearHealthMonitorCards();
                    // 后端暂无数据集质量汇总，真实模式清空静态演示评分
                    _clearDataQuality();
                    // 后端暂无 L1 状态/分布与逐组件探针，真实模式清空静态演示
                    _clearRegimeAndHa();
                    // 与引擎 P2 卡片重复的旧静态面板，真实模式清空演示数字/列表
                    _clearLegacyMonitorPanels();
                    debugLog(`验证模块状态加载成功: ${statusData.data.total}个模块`, 'success');
                }
                
                // 加载审计日志
                const logsRes = await fetch('/api/validation/audit-logs?limit=20', {
                    headers: { 'Authorization': 'Bearer ' + Auth.getToken() }
                });
                if (logsRes.ok) {
                    const logsData = await logsRes.json();
                    if (logsData.code === 1 && logsData.data) {
                        renderAuditLogs(logsData.data.logs);
                        debugLog(`审计日志加载成功: ${logsData.data.total}条`, 'success');
                    }
                }
                
                // 加载压力测试结果
                const stressRes = await fetch('/api/validation/stress-test', {
                    headers: { 'Authorization': 'Bearer ' + Auth.getToken() }
                });
                if (stressRes.ok) {
                    const stressData = await stressRes.json();
                    if (stressData.code === 1 && stressData.data) {
                        renderStressTest(stressData.data);
                        debugLog(`压力测试结果加载成功: ${stressData.data.total_scenarios}个情景`, 'success');
                    } else {
                        _clearStressTest();
                    }
                } else {
                    _clearStressTest();
                }
                
                // 加载交易日志与绩效归因
                const journalRes = await fetch('/api/p1/journal/analyze?days=30', {
                    headers: { 'Authorization': 'Bearer ' + Auth.getToken() }
                });
                if (journalRes.ok) {
                    const journalData = await journalRes.json();
                    if (journalData.success && journalData.data) {
                        renderJournalAnalysis(journalData.data);
                        debugLog(`绩效归因加载成功: ${journalData.data.total_trades}笔`, 'success');
                    }
                }

                // TCA 交易成本汇总；无订单/失败时清空静态演示成本
                const tcaRes = await fetch('/api/tca/cost-summary', {
                    headers: { 'Authorization': 'Bearer ' + Auth.getToken() }
                });
                if (tcaRes.ok) {
                    const tcaData = await tcaRes.json();
                    if (tcaData.success && tcaData.data) {
                        renderTcaSummary(tcaData.data);
                    } else {
                        _clearTca();
                    }
                } else {
                    _clearTca();
                }

                // 过拟合三重验证（PBO / CPCV / DSR）；缺样本时后端返回 null，前端渲染 --
                const overfitRes = await fetch('/api/p1/overfitting/status', {
                    headers: { 'Authorization': 'Bearer ' + Auth.getToken() }
                });
                if (overfitRes.ok) {
                    const overfitData = await overfitRes.json();
                    if (overfitData.success && overfitData.data) {
                        renderOverfittingSummary(overfitData.data);
                    }
                }

                // 更新时间
                const now = new Date();
                document.getElementById('validation-time').textContent = now.toLocaleTimeString();

            } catch (err) {
                debugLog(`AI验证层API暂不可用: ${err.message}`, 'warn');
                // API不可用时保留空态 --，不回填演示哨兵数字
            }
        }
        
        function renderOverfittingSummary(data) {
            const pboEl = document.getElementById('pbo-value');
            const cpcvEl = document.getElementById('cpcv-value');
            const dsrEl = document.getElementById('dsr-value');
            if (!pboEl || !cpcvEl || !dsrEl) return;

            const pbo = data.pbo && data.pbo.pbo;
            pboEl.textContent = pbo == null ? '--' : Number(pbo).toFixed(3);

            const stable = data.cpcv && data.cpcv.is_stable;
            cpcvEl.textContent = stable == null ? '--' : (stable ? '通过' : '不稳定');

            const dsr = data.dsr && data.dsr.deflated_sharpe;
            dsrEl.textContent = dsr == null ? '--' : Number(dsr).toFixed(3);
        }

        function renderValidationModules(modules) {
            const container = document.getElementById('validation-modules');
            if (!container || !modules) return;
            
            const levelColors = {
                high: '#8b5cf6',
                medium: '#0ecb81',
                low: '#848e9c'
            };
            
            container.innerHTML = modules.map(m => {
                const badge = {
                    connected: { text: '已连接', color: '#0ecb81', bg: 'rgba(14, 203, 129, 0.1)' },
                    healthy: { text: '健康', color: '#0ecb81', bg: 'rgba(14, 203, 129, 0.1)' },
                    pending: { text: '待接入', color: '#848e9c', bg: 'rgba(132, 142, 156, 0.12)' }
                }[m.status] || { text: '待接入', color: '#848e9c', bg: 'rgba(132, 142, 156, 0.12)' };
                const mark = (m.status === 'connected' || m.status === 'healthy') ? '✓ ' : '';
                return `
                <div style="display: flex; justify-content: space-between; align-items: center; padding: 12px 16px; background: var(--bg-primary); border-radius: 8px; border-left: 3px solid ${levelColors[m.level] || '#848e9c'};">
                    <div>
                        <span style="font-size: 13px;">${m.name}</span>
                        ${m.details ? `<div style="font-size: 11px; color: var(--text-secondary); margin-top: 4px;">${m.details}</div>` : ''}
                    </div>
                    <span style="padding: 2px 8px; background: ${badge.bg}; color: ${badge.color}; border-radius: 4px; font-size: 11px;">
                        ${mark}${badge.text}
                    </span>
                </div>`;
            }).join('');
        }

        function renderDriftMonitor(modules) {
            const dataEl = document.getElementById('drift-data');
            const conceptEl = document.getElementById('drift-concept');
            const statusEl = document.getElementById('drift-status');
            if (!dataEl || !conceptEl) return;
            const drift = (modules || []).find(m => m.id === 'drift_monitor');
            if (!drift) return; // 后端未返回漂移模块时保留空态占位
            const details = drift.details || '';
            const dataMatch = details.match(/数据漂移[:：]\s*([^,，]*)/);
            const conceptMatch = details.match(/概念漂移[:：]\s*([^,，]*)/);
            if (dataMatch) dataEl.textContent = dataMatch[1].trim();
            if (conceptMatch) conceptEl.textContent = conceptMatch[1].trim();
            if (statusEl) {
                const ok = drift.status === 'healthy' || drift.status === 'connected';
                const pending = drift.status === 'pending';
                if (ok) {
                    statusEl.textContent = '正常';
                    statusEl.style.color = '#0ecb81';
                    statusEl.style.background = 'rgba(14, 203, 129, 0.1)';
                } else if (pending) {
                    statusEl.textContent = '待接入';
                    statusEl.style.color = '#848e9c';
                    statusEl.style.background = 'rgba(132, 142, 156, 0.12)';
                } else {
                    statusEl.textContent = '异常';
                    statusEl.style.color = '#f6465d';
                    statusEl.style.background = 'rgba(246, 70, 93, 0.1)';
                }
            }
        }

        function renderAuditLogs(logs) {
            const container = document.getElementById('audit-logs');
            if (!container) return;

            if (!Array.isArray(logs) || logs.length === 0) {
                container.innerHTML = '<div style="padding: 8px 12px; color: var(--text-tertiary); font-size: 12px;">暂无决策审计日志</div>';
                return;
            }

            const levelColors = {
                INFO: '#f0b90b',
                WARN: '#f6465d',
                ERROR: '#f6465d'
            };

            container.innerHTML = logs.map(log => `
                <div style="padding: 8px 12px; background: var(--bg-primary); border-radius: 6px;">
                    <span style="color: var(--text-secondary);">${log.time}</span>
                    <span style="margin-left: 8px; color: ${levelColors[log.level] || '#f0b90b'}; font-weight: 600;">${log.level}</span>
                    <span style="margin-left: 8px; color: var(--text-secondary);">${log.message}</span>
                </div>
            `).join('');
        }

        function renderJournalAnalysis(d) {
            if (!d) return;
            const tradesEl = document.getElementById('journal-trades');
            if (tradesEl) tradesEl.textContent = (d.total_trades == null ? '--' : String(d.total_trades));
            const wrEl = document.getElementById('journal-winrate');
            if (wrEl) wrEl.textContent = d.win_rate == null ? '--' : Number(d.win_rate).toFixed(1) + '%';
            const pfEl = document.getElementById('journal-pf');
            if (pfEl) pfEl.textContent = d.profit_factor == null ? '--' : Number(d.profit_factor).toFixed(2);
            const expEl = document.getElementById('journal-expectancy');
            if (expEl) expEl.textContent = d.expectancy == null ? '--' : (Number(d.expectancy) >= 0 ? '+' : '') + Number(d.expectancy).toFixed(2) + 'R';

            const biasList = document.getElementById('journal-bias-list');
            if (biasList) {
                const biases = Array.isArray(d.behavioral_biases) ? d.behavioral_biases : [];
                biasList.innerHTML = biases.length
                    ? biases.map(b => `<div>• <strong>${b.type || '偏差'}：</strong> ${b.description || ''}</div>`).join('')
                    : '<div>暂无行为偏差数据</div>';
            }
            const recEl = document.getElementById('journal-recommendation');
            if (recEl) {
                const recs = Array.isArray(d.recommendations) ? d.recommendations : [];
                recEl.textContent = recs.length ? '• 改进建议：' + recs[0] : '';
            }
        }

        function _stressCards() {
            return document.querySelectorAll('#page-validation [style*="border-top: 3px solid"]');
        }

        // 接口异常/无情景时清空演示哨兵，所有指标置 --，不留静态假数值
        function _clearStressTest() {
            _stressCards().forEach((card) => {
                const nameEl = card.querySelector('[style*="font-size: 12px"]');
                const ddEl = card.querySelector('[style*="font-size: 20px"]');
                const descEl = card.querySelector('[style*="font-size: 11px"]');
                if (nameEl) nameEl.textContent = '--';
                if (ddEl) ddEl.textContent = '--';
                if (descEl) descEl.textContent = '--';
            });
            const mainEl = document.getElementById('stress-score-main');
            const sumEl = document.getElementById('stress-score-summary');
            if (mainEl) mainEl.textContent = '综合风险评分：-- / 100';
            if (sumEl) sumEl.textContent = '';
        }

        function renderStressTest(data) {
            // 真实契约：仅当后端基于真实持仓/权益完成冲击测算并显式标记 data_kind==='real' 才渲染；
            // 内置演示情景、缺标记或无情景一律清空空态，杜绝演示评分/回撤顶替真实压力测试结果
            if (!data || data.data_kind !== 'real' || !Array.isArray(data.scenarios) || data.scenarios.length === 0) {
                _clearStressTest();
                return;
            }

            const colorMap = {
                red: '#f6465d',
                orange: '#f0b90b',
                green: '#0ecb81',
                purple: '#8b5cf6'
            };

            // 更新压力测试卡片（名称/数值/颜色/描述均以后端为准）
            const cards = _stressCards();
            data.scenarios.forEach((s, i) => {
                const card = cards[i];
                if (!card) return;
                const color = colorMap[s.color] || '#848e9c';
                card.style.borderTopColor = color;
                const nameEl = card.querySelector('[style*="font-size: 12px"]');
                const ddEl = card.querySelector('[style*="font-size: 20px"]');
                const descEl = card.querySelector('[style*="font-size: 11px"]');
                if (nameEl) nameEl.textContent = s.name || '--';
                if (ddEl) {
                    const v = Number(s.drawdown);
                    ddEl.textContent = Number.isFinite(v) ? (v > 0 ? '+' : '') + v.toFixed(2) + '%' : '--';
                    ddEl.style.color = color;
                }
                if (descEl) descEl.textContent = s.description || '--';
            });

            // 更新综合风险评分
            const mainEl = document.getElementById('stress-score-main');
            const sumEl = document.getElementById('stress-score-summary');
            if (!mainEl) return;
            if (data.overall_risk_score == null) {
                mainEl.textContent = '综合风险评分：-- / 100';
                if (sumEl) sumEl.textContent = '';
                return;
            }
            mainEl.textContent = `✓ 综合风险评分：${data.overall_risk_score}/100（${data.risk_level || '--'}）`;
            if (sumEl) sumEl.textContent = data.summary || '';
        }
        
        // ========== 风险仪表盘数据加载 ==========
        async function loadRiskData() {
            debugLog('加载风险仪表盘数据', 'info');
            try {
                // 自建后端真实路由：/api/risk/portfolio（无 /dashboard）
                const res = await fetch('/api/risk/portfolio', {
                    headers: { 'Authorization': 'Bearer ' + Auth.getToken() }
                });
                if (!res.ok) throw new Error('API返回' + res.status);
                const data = await res.json();
                if (data.success && data.data) {
                    riskIsReal = true;
                    // 后端暂无策略级风险预算，真实模式清空静态演示占比
                    _clearRiskBudget();
                    renderRiskDashboard(data.data);
                    renderRiskThreshold(data.data);
                    debugLog(`风险数据加载成功`, 'success');
                } else {
                    riskIsReal = false;
                    _clearRiskThreshold();
                }
            } catch (err) {
                riskIsReal = false;
                debugLog(`风险API暂不可用: ${err.message}`, 'warn');
                // API不可用时保留空态 --，不回填演示哨兵数字
                _clearRiskThreshold();
            }
            // 风控引擎内存告警（独立只读请求，失败不阻塞组合快照）
            loadRiskAlerts();
            // 更新时间
            const now = new Date();
            document.getElementById('risk-update-time').textContent = '更新于 ' + now.toLocaleTimeString();
        }

        function _clearRiskThreshold() {
            ['risk-dd-current', 'risk-dd-limit', 'risk-equity', 'risk-daily-loss-limit'].forEach(id => {
                const el = document.getElementById(id);
                if (el) el.textContent = '--';
            });
            const bar = document.getElementById('risk-dd-bar');
            if (bar) { bar.style.width = '0%'; bar.style.background = '#0ecb81'; }
        }

        // 账户回撤 / 亏损阈值可视化：仅回填 /api/risk/portfolio 已透出的真实字段
        function renderRiskThreshold(data) {
            if (!data) { _clearRiskThreshold(); return; }
            const num = v => (v == null || isNaN(Number(v))) ? null : Number(v);
            const dd = num(data.current_drawdown_pct);
            const limit = num(data.max_drawdown_limit_pct);
            const eq = num(data.current_equity);
            const peak = num(data.peak_equity);

            const ddEl = document.getElementById('risk-dd-current');
            if (ddEl) ddEl.textContent = dd == null ? '--' : dd.toFixed(1) + '%';
            const limEl = document.getElementById('risk-dd-limit');
            if (limEl) limEl.textContent = limit == null ? '--' : limit.toFixed(1) + '%';
            const eqEl = document.getElementById('risk-equity');
            if (eqEl) {
                eqEl.textContent = (eq == null ? '--' : eq.toFixed(2)) + (peak != null ? ' / ' + peak.toFixed(2) : '');
            }
            // 单日亏损限额后端未透出（C-RISK-01），保持空态，不用配置默认值冒充
            const dlEl = document.getElementById('risk-daily-loss-limit');
            if (dlEl) dlEl.textContent = '--';

            const bar = document.getElementById('risk-dd-bar');
            if (bar) {
                let pct = 0;
                if (dd != null && limit != null && limit > 0) pct = Math.min(100, Math.max(0, dd / limit * 100));
                bar.style.width = pct + '%';
                bar.style.background = pct >= 80 ? '#f6465d' : pct >= 50 ? '#f0b90b' : '#0ecb81';
            }
        }

        const RISK_ALERT_COLORS = { error: '#f6465d', warn: '#f0b90b', warning: '#f0b90b', info: '#8b5cf6', success: '#0ecb81' };

        async function loadRiskAlerts() {
            const listEl = document.getElementById('risk-alert-list');
            const countEl = document.getElementById('risk-alert-count');
            if (!listEl) return;
            const emptyHtml = '<div style="padding:12px;color:var(--text-secondary);text-align:center;font-size:12px;">暂无风控告警 / 拦截事件</div>';
            try {
                const res = await fetch('/api/risk/alerts', {
                    headers: { 'Authorization': 'Bearer ' + Auth.getToken() }
                });
                if (!res.ok) throw new Error('API返回' + res.status);
                const body = await res.json();
                const alerts = (body && body.success && Array.isArray(body.data)) ? body.data : [];
                if (countEl) countEl.textContent = alerts.length ? `共 ${alerts.length} 条` : '';
                if (!alerts.length) { listEl.innerHTML = emptyHtml; return; }
                listEl.innerHTML = alerts.map(a => {
                    const lv = String(a.level || 'info').toLowerCase();
                    const color = RISK_ALERT_COLORS[lv] || '#848e9c';
                    const meta = [a.symbol, a.position_id != null ? `#${a.position_id}` : '', a.action_required ? `动作: ${a.action_required}` : ''].filter(Boolean).join(' · ');
                    return `
                        <div style="padding:12px;background:var(--bg-primary);border-left:3px solid ${color};border-radius:8px;">
                            <div style="display:flex;gap:8px;align-items:center;margin-bottom:4px;">
                                <span style="padding:2px 6px;background:${color}20;color:${color};border-radius:3px;font-size:11px;font-weight:600;">${lv.toUpperCase()}</span>
                                <span style="font-size:12px;font-weight:600;color:#eaecef;">${a.alert_type || a.type || '风控告警'}</span>
                                <span style="flex:1;"></span>
                                <span style="font-size:11px;color:var(--text-secondary);">${_riskAlertTime(a.timestamp)}</span>
                            </div>
                            <div style="font-size:12px;color:var(--text-secondary);line-height:1.6;">${a.message || '--'}</div>
                            ${meta ? `<div style="font-size:11px;color:var(--text-secondary);margin-top:4px;">${meta}</div>` : ''}
                        </div>`;
                }).join('');
            } catch (err) {
                debugLog(`风控告警接口暂不可用: ${err.message}`, 'warn');
                listEl.innerHTML = emptyHtml;
                if (countEl) countEl.textContent = '';
            }
        }

        function _riskAlertTime(ts) {
            if (ts == null || ts === '') return '--';
            const d = new Date(typeof ts === 'number' ? ts * 1000 : ts);
            return isNaN(d.getTime()) ? String(ts) : d.toLocaleString('zh-CN', { hour12: false });
        }
        
        function renderRiskDashboard(data) {
            // 自建后端 /api/risk/portfolio 真实字段映射
            if (data.current_drawdown_pct !== undefined && data.current_drawdown_pct !== null) {
                data.daily_drawdown = data.current_drawdown_pct;
            }
            if (data.risk_level) {
                debugLog(`账户风险等级: ${data.risk_level}`, 'info');
            }
            if (data.total_exposure) {
                const el = document.getElementById('risk-total-exposure');
                el.textContent = data.total_exposure.toFixed(1) + '%';
                el.style.color = data.total_exposure > 15 ? 'var(--down-color)' : 'var(--up-color)';
            }
            if (data.max_strategy_risk) {
                const el = document.getElementById('risk-max-strategy');
                el.textContent = data.max_strategy_risk.toFixed(1) + '%';
                el.style.color = data.max_strategy_risk > 8 ? 'var(--down-color)' : 'var(--warning-color)';
            }
            if (data.avg_correlation) {
                document.getElementById('risk-correlation').textContent = data.avg_correlation.toFixed(2);
            }
            if (data.daily_drawdown != null) {
                const el = document.getElementById('risk-daily-drawdown');
                el.textContent = data.daily_drawdown.toFixed(1) + '%';
            }
            if (data.var_95) {
                document.getElementById('risk-var').textContent = data.var_95.toFixed(2) + '%';
            }
            if (data.cvar_95) {
                document.getElementById('risk-cvar').textContent = data.cvar_95.toFixed(2) + '%';
            }
        }

        // ========== 核心引擎数据加载 ==========
        async function loadEngineData() {
            debugLog('加载核心引擎数据', 'info');
            
            // 1. 五层市场识别架构
            const layersEl = document.getElementById('market-layers-list');
            const layerStatusColor = (status) => {
                const s = String(status || '').toLowerCase();
                if (['active', 'healthy', 'done', 'online'].includes(s)) return '#0ecb81';
                if (['error', 'unhealthy', 'failed'].includes(s)) return '#f6465d';
                if (['watch', 'degraded'].includes(s)) return '#f0b90b';
                return '#848e9c';
            };
            try {
                const res = await fetch('/api/p1/market-layers/summary');
                const data = await res.json();
                const layers = (data.success && data.data && data.data.layers) || [];
                if (layers.length) {
                    const html = layers.map(l =>
                        `<div>• <span style="color: #5e72e4; font-weight: 600;">${l.level}</span> ${l.name} <span style="color: ${layerStatusColor(l.status)};">${l.status || 'pending'}</span><br>
                         <span style="font-size: 11px; color: var(--text-secondary); padding-left: 20px;">${l.desc}</span></div>`
                    ).join('');
                    if (layersEl) layersEl.innerHTML = html;
                } else if (layersEl) {
                    layersEl.innerHTML = '<div style="color: var(--text-tertiary); font-size:12px; padding:4px 0;">暂无层级数据，待接入</div>';
                }
            } catch (e) {
                debugLog(`五层市场识别加载失败: ${e.message}`, 'error');
                if (layersEl) layersEl.innerHTML = '<div style="color: var(--text-tertiary); font-size:12px; padding:4px 0;">数据不可用，待接入</div>';
            }

            // 2. 策略优化引擎状态
            const optEl = document.getElementById('optimizer-status');
            try {
                const res = await fetch('/api/p1/optimizer/status');
                const data = await res.json();
                if (data.success && data.data) {
                    const s = data.data;
                    if (optEl) optEl.innerHTML = `
                        <div>• 因子数量: <span style="color: #f0b90b; font-weight: 600;">${s.factor_count ?? '--'}</span> 个</div>
                        <div>• 累计试验: <span style="color: #f0b90b; font-weight: 600;">${s.total_trials ?? '--'}</span> 次</div>
                        <div>• 已优化策略: <span style="color: #f0b90b; font-weight: 600;">${s.optimized_strategies ?? '--'}</span> 个</div>
                        <div style="font-size: 11px; color: var(--text-secondary); margin-top: 8px;">🛡️ ${s.overfitting_defense || '待接入'}</div>
                    `;
                } else if (optEl) {
                    optEl.innerHTML = '<div style="color: var(--text-tertiary); font-size:12px; padding:4px 0;">暂无优化引擎状态，待接入</div>';
                }
            } catch (e) {
                debugLog(`优化引擎状态加载失败: ${e.message}`, 'error');
                if (optEl) optEl.innerHTML = '<div style="color: var(--text-tertiary); font-size:12px; padding:4px 0;">数据不可用，待接入</div>';
            }

            // 3. 因子库列表
            const factorEl = document.getElementById('factor-list');
            try {
                const res = await fetch('/api/p1/optimizer/factors');
                const data = await res.json();
                const factors = (data.success && data.data && data.data.factors) || [];
                if (factors.length) {
                    const html = factors.map(f =>
                        `<span style="display: inline-block; background: rgba(240,185,11,0.1); color: #f0b90b; padding: 2px 8px; border-radius: 4px; margin: 2px; font-size: 10px;">${f.name}</span>`
                    ).join('');
                    if (factorEl) factorEl.innerHTML = html;
                } else if (factorEl) {
                    factorEl.textContent = '暂无已注册因子，待接入';
                }
            } catch (e) {
                debugLog(`因子库加载失败: ${e.message}`, 'error');
                if (factorEl) factorEl.textContent = '数据不可用，待接入';
            }

            // 4. 策略健康度
            const healthEl = document.getElementById('engine-health-list');
            try {
                const res = await fetch('/api/p1/strategy-health/summary');
                const data = await res.json();
                const s = (data.success && data.data) || null;
                if (s && (s.total || 0) > 0) {
                    const html = `
                        <div>• 总策略数: <span style="font-weight: 600;">${s.total}</span></div>
                        <div>• 健康运行: <span style="color: #0ecb81; font-weight: 600;">${s.active ?? '--'}</span></div>
                        <div>• 观察预警: <span style="color: #f0b90b; font-weight: 600;">${s.watch ?? '--'}</span></div>
                        <div>• 暂停退役: <span style="color: #f6465d; font-weight: 600;">${s.suspended ?? '--'}</span></div>
                        <div>• 平均健康分: <span style="font-weight: 600;">${s.avg_health_score ?? '--'}</span> / 100</div>
                        <div style="font-size: 11px; color: var(--text-secondary); margin-top: 8px;">绿区运行 → 黄区减仓 → 红区退役</div>
                    `;
                    if (healthEl) healthEl.innerHTML = html;
                } else if (healthEl) {
                    healthEl.innerHTML = '<div style="color: var(--text-tertiary); font-size:12px; padding:4px 0;">暂无已接入策略，待接入</div>';
                }
            } catch (e) {
                debugLog(`策略健康度加载失败: ${e.message}`, 'error');
                if (healthEl) healthEl.innerHTML = '<div style="color: var(--text-tertiary); font-size:12px; padding:4px 0;">数据不可用，待接入</div>';
            }

            // 5. 综合市场分析
            const maEl = document.getElementById('market-analysis-result');
            const maBadge = document.getElementById('market-analysis-badge');
            if (Auth.isLoggedIn()) {
                // 真实模式：后端暂无基于真实行情的综合分析端点，空态收口，不拉演示端点随机噪声
                if (maEl) maEl.innerHTML = '<div style="padding:8px;color:var(--text-tertiary);font-size:12px;">暂无真实综合市场分析，待接入</div>';
                if (maBadge) { maBadge.textContent = '待接入'; maBadge.style.color = 'var(--text-tertiary)'; }
            } else {
                // 未登录同样不拉演示端点：演示方向/置信度/入场区不得冒充真实分析
                if (maEl) maEl.innerHTML = '<div style="padding:8px;color:var(--text-tertiary);font-size:12px;">暂无真实综合市场分析，待接入</div>';
                if (maBadge) { maBadge.textContent = '待接入'; maBadge.style.color = 'var(--text-tertiary)'; }
            }

            // 6. P1/P2 企业级模块卡片实时数据
            loadP2ModuleCards();
        }

        // ========== AI 复盘模块（只读归因，不触发交易） ==========
        let reviewStrategies = [];

        function _reviewEl(id) { return document.getElementById(id); }

        function _reviewNum(v, digits = 2) {
            if (v == null || v === '' || isNaN(Number(v))) return '--';
            return Number(v).toFixed(digits);
        }

        function _reviewPct(v, digits = 1) {
            if (v == null || v === '' || isNaN(Number(v))) return '--';
            return Number(v).toFixed(digits) + '%';
        }

        function _reviewTime(ts) {
            if (ts == null || ts === '') return '--';
            const d = new Date(typeof ts === 'number' ? ts * 1000 : ts);
            if (isNaN(d.getTime())) return String(ts);
            return d.toLocaleString('zh-CN', { hour12: false });
        }

        async function loadReviewStrategies() {
            const sel = _reviewEl('review-strategy-select');
            if (!sel) return;
            const res = await ApiService.getStrategies();
            let list = [];
            if (res && Array.isArray(res.data)) list = res.data;
            else if (res && res.data && Array.isArray(res.data.items)) list = res.data.items;
            reviewStrategies = list;
            if (!list.length) {
                sel.innerHTML = '<option value="">暂无可用策略</option>';
                return;
            }
            sel.innerHTML = '<option value="">请选择策略</option>' + list.map(s => {
                const id = s.id;
                const name = s.strategy_name || s.name || '未命名策略';
                return `<option value="${id}">${name}</option>`;
            }).join('');
        }

        function _reviewDiagColor(severity) {
            const s = String(severity || '').toLowerCase();
            if (s === 'error' || s === 'critical') return '#f6465d';
            if (s === 'warn' || s === 'warning') return '#f0b90b';
            return '#848e9c';
        }

        function _reviewRecColor(priority) {
            const p = String(priority || '').toLowerCase();
            if (p === 'high') return '#f6465d';
            if (p === 'medium') return '#f0b90b';
            return '#0ecb81';
        }

        // 归因统计：后端暂无亏损根因分类 / 止损触发 / 过早止盈字段（C-REVIEW-01/02/03），固定空态 --
        function _clearReviewAttribution() {
            ['review-rootcause', 'review-stoploss', 'review-premature-tp'].forEach(id => {
                const el = _reviewEl(id);
                if (el) el.textContent = '--';
            });
        }

        function renderReviewReport(report) {
            _clearReviewAttribution();
            const meta = _reviewEl('review-strategy-meta');
            const m = report.strategy || {};
            meta.style.display = 'block';
            const metaBits = [
                m.name, m.symbol, m.timeframe, m.status, m.exchange, m.market_type
            ].filter(Boolean);
            meta.innerHTML = `
                <div style="font-weight: 600; margin-bottom: 8px; color: #eaecef;">${m.name || '策略复盘'}</div>
                <div style="font-size: 12px; color: var(--text-secondary);">${metaBits.join(' · ') || '—'}</div>
                <div style="font-size: 12px; color: var(--text-secondary); margin-top: 6px;">复盘周期：近 ${report.lookback_days || 30} 天 · 生成于 ${_reviewTime(report.generated_at)}</div>
            `;

            const metrics = report.metrics || {};
            const cards = [
                { label: '平仓盈亏笔数', value: _reviewNum(metrics.closed_trades_with_pnl, 0) },
                { label: '胜率', value: _reviewPct(metrics.win_rate) },
                { label: '盈亏比', value: _reviewNum(metrics.profit_factor) },
                { label: '期望值/笔', value: _reviewNum(metrics.expectancy) },
                { label: '区间净盈亏', value: _reviewNum(metrics.window_net_pnl) },
                { label: '区间收益', value: _reviewPct(metrics.window_return_pct) },
                { label: '区间最大回撤', value: _reviewPct(metrics.window_max_drawdown_pct) },
                { label: '最大连亏', value: _reviewNum(metrics.max_consecutive_losses, 0) },
                { label: '手续费', value: _reviewNum(metrics.total_commission, 4) },
                { label: '当前持仓', value: _reviewNum(metrics.open_position_count, 0) }
            ];
            _reviewEl('review-metrics').innerHTML = cards.map(c => `
                <div style="background: var(--bg-primary); border-radius: 8px; padding: 14px;">
                    <div style="font-size: 12px; color: var(--text-secondary); margin-bottom: 6px;">${c.label}</div>
                    <div style="font-size: 18px; font-weight: 700;">${c.value}</div>
                </div>
            `).join('');

            const diag = Array.isArray(report.diagnostics) ? report.diagnostics : [];
            const diagEl = _reviewEl('review-diagnostics');
            if (!diag.length) {
                diagEl.innerHTML = '<div style="color: var(--text-secondary); font-size: 13px;">暂无规则诊断项</div>';
            } else {
                diagEl.innerHTML = diag.map(d => {
                    const color = _reviewDiagColor(d.severity);
                    return `
                        <div style="background: var(--bg-primary); border-left: 3px solid ${color}; border-radius: 8px; padding: 12px;">
                            <div style="display: flex; gap: 8px; align-items: center; margin-bottom: 4px;">
                                <span style="font-weight: 600; font-size: 13px; color: #eaecef;">${d.title || '诊断项'}</span>
                                <span style="font-size: 11px; color: ${color};">${d.severity || 'info'}</span>
                            </div>
                            <div style="font-size: 12px; color: var(--text-secondary); line-height: 1.6;">${d.detail || ''}</div>
                        </div>`;
                }).join('');
            }

            const rec = Array.isArray(report.recommendations) ? report.recommendations : [];
            const recEl = _reviewEl('review-recommendations');
            if (!rec.length) {
                recEl.innerHTML = '<div style="color: var(--text-secondary); font-size: 13px;">暂无改进建议</div>';
            } else {
                recEl.innerHTML = rec.map(r => {
                    const color = _reviewRecColor(r.priority);
                    return `
                        <div style="background: var(--bg-primary); border-left: 3px solid ${color}; border-radius: 8px; padding: 12px;">
                            <div style="display: flex; gap: 8px; align-items: center; margin-bottom: 4px;">
                                <span style="font-weight: 600; font-size: 13px; color: #eaecef;">${r.title || '建议'}</span>
                                <span style="font-size: 11px; color: ${color};">${r.priority || 'low'}</span>
                            </div>
                            <div style="font-size: 12px; color: var(--text-secondary); line-height: 1.6;">${r.detail || ''}</div>
                        </div>`;
                }).join('');
            }

            const ai = report.ai || {};
            const aiBox = _reviewEl('review-ai');
            const aiBody = _reviewEl('review-ai-body');
            const aiHas = ai.status === 'ok' && (ai.summary || (ai.diagnosis || []).length || (ai.recommendations || []).length || (ai.cautions || []).length);
            if (aiHas) {
                aiBox.style.display = 'block';
                const listBlock = (title, arr, color) => {
                    if (!Array.isArray(arr) || !arr.length) return '';
                    return `<div style="margin-top: 10px;"><div style="font-size: 12px; color: ${color}; margin-bottom: 6px;">${title}</div>` +
                        arr.map(x => `<div style="font-size: 12px; color: var(--text-secondary); line-height: 1.6; margin-bottom: 4px;">· ${x}</div>`).join('') + '</div>';
                };
                aiBody.innerHTML = `
                    <div style="font-size: 13px; color: var(--text-primary); line-height: 1.7;">${ai.summary || ''}</div>
                    ${listBlock('诊断要点', ai.diagnosis, '#f0b90b')}
                    ${listBlock('AI 建议', ai.recommendations, '#0ecb81')}
                    ${listBlock('风险提示', ai.cautions, '#f6465d')}
                `;
            } else {
                aiBox.style.display = 'none';
                aiBody.innerHTML = '';
            }

            const b = report.billing;
            const bEl = _reviewEl('review-billing');
            if (b) {
                bEl.style.display = 'block';
                const saved = report.history_saved ? '已归档到历史复盘' : '未归档';
                bEl.innerHTML = `计费：${b.enabled ? `本次扣除 ${b.charged || 0} 积分（剩余 ${_reviewNum(b.remaining, 0)}）` : '规则复盘免费'} · ${saved}${report.history_id ? ` · 记录 #${report.history_id}` : ''}`;
            } else {
                bEl.style.display = 'none';
            }
        }

        async function generateReviewReport() {
            const sel = _reviewEl('review-strategy-select');
            const status = _reviewEl('review-status');
            const btn = _reviewEl('review-generate-btn');
            const sid = sel ? sel.value : '';
            if (!sid) {
                status.textContent = '请先选择策略。';
                return;
            }
            const lookback = parseInt(_reviewEl('review-lookback').value, 10) || 30;
            const includeAi = _reviewEl('review-include-ai').checked;
            _clearReviewAttribution();
            status.textContent = '正在生成复盘报告…';
            status.style.color = 'var(--text-secondary)';
            if (btn) btn.disabled = true;
            try {
                const res = await ApiService.postReviewReport({
                    id: Number(sid),
                    lookback_days: lookback,
                    include_ai: includeAi,
                    language: 'zh-CN'
                });
                if (res._unauthorized) {
                    status.textContent = '未登录或登录已过期，请重新进入页面。';
                    return;
                }
                if (res.code === 1 && res.data) {
                    renderReviewReport(res.data);
                    const aiStatus = (res.data.ai || {}).status || 'skipped';
                    status.textContent = `复盘已生成（近 ${lookback} 天，AI 状态：${aiStatus}）。`;
                    loadReviewHistory();
                } else {
                    const data = res.data || {};
                    if (data.error_type === 'INSUFFICIENT_CREDITS') {
                        status.textContent = '积分不足，无法调用 AI 总结；可取消「含 AI 总结」后使用规则复盘。';
                    } else {
                        status.textContent = '复盘生成失败：' + (res.msg || '未知错误');
                    }
                }
            } catch (e) {
                status.textContent = '复盘生成异常：' + (e.message || e);
                debugLog('复盘生成异常: ' + (e.message || e), 'error');
            } finally {
                if (btn) btn.disabled = false;
            }
        }

        async function loadReviewHistory() {
            const sel = _reviewEl('review-strategy-select');
            const listEl = _reviewEl('review-history-list');
            if (!listEl) return;
            const sid = sel ? sel.value : '';
            if (!sid) {
                listEl.innerHTML = '<div style="padding: 12px; color: var(--text-secondary); text-align: center; font-size: 13px;">选择策略后查看历史复盘记录</div>';
                return;
            }
            const res = await ApiService.getReviewHistory(sid, 20);
            let hist = [];
            if (res && res.code === 1) {
                hist = Array.isArray(res.data) ? res.data : (res.data && res.data.items) || [];
            }
            if (!hist.length) {
                listEl.innerHTML = '<div style="padding: 12px; color: var(--text-secondary); text-align: center; font-size: 13px;">暂无历史复盘记录</div>';
                return;
            }
            listEl.innerHTML = hist.map(h => `
                <div style="background: var(--bg-primary); border-radius: 8px; padding: 12px; display: flex; flex-wrap: wrap; gap: 12px; align-items: center; font-size: 12px;">
                    <span style="color: var(--text-secondary);">#${h.id}</span>
                    <span style="color: var(--text-primary);">近 ${h.lookback_days || 30} 天</span>
                    <span>净盈亏 ${_reviewNum(h.total_net_pnl)}</span>
                    <span>收益 ${_reviewPct(h.total_return_pct)}</span>
                    <span>胜率 ${_reviewPct(h.win_rate)}</span>
                    <span>回撤 ${_reviewPct(h.max_drawdown_pct)}</span>
                    <span style="color: var(--text-secondary);">AI：${h.ai_status || 'skipped'}</span>
                    <span style="flex: 1;"></span>
                    <span style="color: var(--text-secondary);">${_reviewTime(h.created_at)}</span>
                </div>
                ${h.summary ? `<div style="font-size: 12px; color: var(--text-secondary); line-height: 1.6; padding: 0 12px 10px 12px;">${h.summary}</div>` : ''}
            `).join('');
        }

        function initReviewModule() {
            const genBtn = _reviewEl('review-generate-btn');
            if (genBtn && !genBtn.dataset.bound) {
                genBtn.dataset.bound = '1';
                genBtn.addEventListener('click', generateReviewReport);
            }
            const histBtn = _reviewEl('review-history-refresh');
            if (histBtn && !histBtn.dataset.bound) {
                histBtn.dataset.bound = '1';
                histBtn.addEventListener('click', loadReviewHistory);
            }
            const sel = _reviewEl('review-strategy-select');
            if (sel && !sel.dataset.bound) {
                sel.dataset.bound = '1';
                sel.addEventListener('change', loadReviewHistory);
            }
        }


        const P2_LAMP = {
            green: '#0ecb81',
            yellow: '#f0b90b',
            red: '#f6465d',
            gray: '#848e9c'
        };

        function p2PaintLamp(key, level) {
            const color = P2_LAMP[level] || P2_LAMP.gray;
            const dot = document.getElementById(`p2-dot-${key}`);
            const card = document.getElementById(`p2-card-${key}`);
            if (dot) {
                dot.style.background = color;
                dot.style.boxShadow = `0 0 6px ${color}`;
            }
            if (card) card.style.borderLeftColor = color;
        }

        function p2SetState(key, text, color) {
            const el = document.getElementById(`p2-state-${key}`);
            if (el) {
                el.textContent = text;
                el.style.color = color || 'var(--text-secondary)';
            }
        }

        function p2SetMetrics(key, html) {
            const el = document.getElementById(`p2-metrics-${key}`);
            if (el) el.innerHTML = html;
        }

        function p2Stamp(key) {
            const el = document.getElementById(`p2-updated-${key}`);
            if (el) el.textContent = '更新于 ' + new Date().toLocaleTimeString('zh-CN', { hour12: false });
        }

        function p2Metric(label, value, color) {
            return `<div style="display:flex;justify-content:space-between;line-height:1.9;">
                <span style="color: var(--text-secondary);">${label}</span>
                <span style="font-weight:600; color:${color || '#eaecef'};">${value}</span>
            </div>`;
        }

        async function p2FetchJson(path) {
            // 8秒客户端超时：后端不可达时降级为"数据不可用"，避免卡片卡在"加载中"
            const timeout = new Promise((_, reject) =>
                setTimeout(() => reject(new Error('timeout')), 8000)
            );
            const res = await Promise.race([fetch(path), timeout]);
            if (!res.ok) throw new Error('HTTP ' + res.status);
            return await res.json();
        }

        // 失败统一降级：显示"数据不可用"，不抛错到控制台外
        function p2Fail(key, msg) {
            p2PaintLamp(key, 'gray');
            p2SetState(key, 'OFFLINE', P2_LAMP.gray);
            p2SetMetrics(key, `<div style="color: var(--text-secondary);">${msg || '数据不可用'}</div>`);
        }

        async function loadP2ModuleCards() {
            // 1. 高可用与灾备  GET /api/p1/health
            try {
                const r = await p2FetchJson('/api/p1/health');
                if (!r.success) throw new Error(r.error || 'success=false');
                const d = r.data || {};
                const st = d.overall_status || 'unknown';
                const level = st === 'healthy' ? 'green' : st === 'degraded' ? 'yellow' : st === 'unhealthy' ? 'red' : 'gray';
                p2PaintLamp('ha', level);
                p2SetState('ha', st.toUpperCase(), P2_LAMP[level]);
                p2SetMetrics('ha',
                    p2Metric('可用率', (d.availability_pct || 0).toFixed(1) + '%', P2_LAMP[level]) +
                    p2Metric('健康服务', `${d.healthy ?? 0}/${d.total_services ?? 0}`) +
                    p2Metric('累计故障', String(d.total_failures ?? 0), (d.total_failures ?? 0) > 0 ? P2_LAMP.yellow : '#eaecef') +
                    p2Metric('故障切换', String(d.total_failovers ?? 0))
                );
                p2Stamp('ha');
            } catch (e) { p2Fail('ha', '数据不可用'); debugLog(`P2[高可用]加载失败: ${e.message}`, 'error'); }

            // 2. 交易日志与归因  GET /api/p1/journal/analyze?days=30
            try {
                const r = await p2FetchJson('/api/p1/journal/analyze?days=30');
                if (!r.success) throw new Error(r.error || 'success=false');
                const d = r.data || {};
                const trades = d.total_trades ?? 0;
                const level = trades > 0 ? 'green' : 'gray';
                p2PaintLamp('journal', level);
                p2SetState('journal', trades > 0 ? 'ANALYZED' : 'NO DATA', P2_LAMP[level]);
                p2SetMetrics('journal',
                    p2Metric('周期', d.period || '-') +
                    p2Metric('总交易', String(trades), P2_LAMP.green) +
                    p2Metric('胜率', Number(d.win_rate || 0).toFixed(1) + '%') +
                    p2Metric('净利', (d.total_pnl || 0).toFixed(2)) +
                    p2Metric('盈亏比', (d.profit_factor || 0).toFixed(2))
                );
                p2Stamp('journal');
            } catch (e) { p2Fail('journal', '数据不可用'); debugLog(`P2[交易归因]加载失败: ${e.message}`, 'error'); }

            // 3. 安全与合规  GET /api/p1/security/summary
            try {
                const r = await p2FetchJson('/api/p1/security/summary');
                if (!r.success) throw new Error(r.error || 'success=false');
                const d = r.data || {};
                const lv = d.security_level || 'good';
                const level = lv === 'good' ? 'green' : lv === 'warning' ? 'yellow' : 'red';
                p2PaintLamp('security', level);
                p2SetState('security', lv.toUpperCase(), P2_LAMP[level]);
                p2SetMetrics('security',
                    p2Metric('活跃会话', String(d.active_sessions ?? 0)) +
                    p2Metric('活跃API密钥', String(d.active_api_keys ?? 0)) +
                    p2Metric('审计日志', String(d.total_audit_logs ?? 0)) +
                    p2Metric('严重告警', String(d.critical_alerts ?? 0), (d.critical_alerts ?? 0) > 0 ? P2_LAMP.red : P2_LAMP.green)
                );
                p2Stamp('security');
            } catch (e) { p2Fail('security', '数据不可用'); debugLog(`P2[安全合规]加载失败: ${e.message}`, 'error'); }

            // 4. 策略拥挤度监控  GET /api/p2/crowding/summary
            try {
                const r = await p2FetchJson('/api/p2/crowding/summary');
                if (!r.success) throw new Error(r.error || 'success=false');
                const d = r.data || {};
                if (d.status === 'no_strategies' || !d.total_strategies) {
                    p2PaintLamp('crowding', 'gray');
                    p2SetState('crowding', 'NO DATA', P2_LAMP.gray);
                    p2SetMetrics('crowding', '<div style="color: var(--text-secondary);">暂无策略注册到拥挤度监控</div>');
                } else {
                    const dist = d.distribution || {};
                    const hi = (dist.high || 0) + (dist.extreme || 0);
                    const level = (dist.extreme || 0) > 0 ? 'red' : hi > 0 ? 'yellow' : 'green';
                    p2PaintLamp('crowding', level);
                    p2SetState('crowding', level === 'green' ? 'NORMAL' : 'WATCH', P2_LAMP[level]);
                    p2SetMetrics('crowding',
                        p2Metric('监控策略', String(d.total_strategies ?? 0), P2_LAMP.green) +
                        p2Metric('平均拥挤分', (d.avg_crowding_score || 0).toFixed(1) + '/100', (d.avg_crowding_score || 0) >= 50 ? P2_LAMP.yellow : P2_LAMP.green) +
                        p2Metric('高/极高拥挤', String(hi), hi > 0 ? P2_LAMP.red : P2_LAMP.green) +
                        `<div style="margin-top:4px; color: var(--text-secondary);">⚠️ ${d.warning || '-'}</div>`
                    );
                }
                p2Stamp('crowding');
            } catch (e) { p2Fail('crowding', '数据不可用'); debugLog(`P2[拥挤度]加载失败: ${e.message}`, 'error'); }

            // 5. 可观测性与告警  GET /api/p2/observability/summary
            try {
                const r = await p2FetchJson('/api/p2/observability/summary');
                if (!r.success) throw new Error(r.error || 'success=false');
                const d = r.data || {};
                const st = d.status || 'healthy';
                const level = st === 'healthy' ? 'green' : st === 'warning' ? 'yellow' : 'red';
                p2PaintLamp('obs', level);
                p2SetState('obs', st.toUpperCase(), P2_LAMP[level]);
                p2SetMetrics('obs',
                    p2Metric('活跃告警', String(d.active_alerts ?? 0), (d.active_alerts ?? 0) > 0 ? P2_LAMP.yellow : P2_LAMP.green) +
                    p2Metric('严重告警', String(d.critical_alerts ?? 0), (d.critical_alerts ?? 0) > 0 ? P2_LAMP.red : P2_LAMP.green) +
                    p2Metric('累计告警', String(d.total_alerts ?? 0))
                );
                p2Stamp('obs');
            } catch (e) { p2Fail('obs', '数据不可用'); debugLog(`P2[可观测性]加载失败: ${e.message}`, 'error'); }

            // 6. CI/CD与部署  GET /api/p2/cicd/status
            try {
                const r = await p2FetchJson('/api/p2/cicd/status');
                if (!r.success) throw new Error(r.error || 'success=false');
                const d = r.data || {};
                const latest = d.latest_deployment;
                const st = latest ? latest.status : 'idle';
                const level = !latest ? 'gray' : st === 'success' ? 'green' : (st === 'failed' || st === 'rolled_back') ? 'red' : 'yellow';
                p2PaintLamp('cicd', level);
                p2SetState('cicd', String(st).toUpperCase(), P2_LAMP[level]);
                p2SetMetrics('cicd',
                    p2Metric('当前版本', 'v' + (d.current_version || '-'), P2_LAMP.green) +
                    p2Metric('累计部署', String(d.total_deployments ?? 0)) +
                    p2Metric('最新部署', latest ? `${latest.version} (${latest.status})` : '无记录', level === 'red' ? P2_LAMP.red : '#eaecef') +
                    p2Metric('自动部署', d.auto_deploy ? '开启' : '人工确认', P2_LAMP.yellow)
                );
                p2Stamp('cicd');
            } catch (e) { p2Fail('cicd', '数据不可用'); debugLog(`P2[CI/CD]加载失败: ${e.message}`, 'error'); }
        }

        // ========== API账户管理 ==========
        function openApiAccountModal() {
            document.getElementById('apiAccountModal').style.display = 'flex';
            debugLog('打开API账户设置弹窗', 'info');
        }

        function closeApiAccountModal() {
            document.getElementById('apiAccountModal').style.display = 'none';
        }

        async function saveApiAccount() {
            const name = document.getElementById('api-account-name').value.trim();
            const exchange = document.getElementById('api-exchange').value;
            const apiKey = document.getElementById('api-key').value.trim();
            const apiSecret = document.getElementById('api-secret').value.trim();
            const passphrase = document.getElementById('api-passphrase').value.trim();
            const permRead = document.getElementById('api-perm-read').checked;
            const permTrade = document.getElementById('api-perm-trade').checked;

            if (!name || !apiKey || !apiSecret) {
                alert('请填写完整：备注名、API Key、API Secret');
                return;
            }

            debugLog(`保存API账户: ${name} (${exchange})`, 'info');

            try {
                // 统一走标准凭证库（Fernet 加密入库 + live_trading.factory 探测），
                // 与 dashboard/positions 的权益口径共用同一条链，避免旧内存字典链
                // 测出的真实余额与仪表盘回退口径分裂。
                const credPayload = {
                    exchange_id: exchange || 'okx',
                    api_key: apiKey,
                    secret_key: apiSecret,
                    passphrase: passphrase,
                    environment: 'demo',   // 弹窗当前绑定 OKX 模拟盘（与旧 is_demo 一致）
                    market_scope: 'both'
                };

                // 1) 先探测（只读私账接口）
                const testRes = await fetch('/api/credentials/test', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(credPayload)
                });
                const testData = await testRes.json();

                if (testData.code !== 1) {
                    alert(`❌ 连接失败: ${testData.msg || 'CREDENTIAL_CONNECTION_FAILED'}`);
                    return;
                }

                // 2) 加密入库（持久化，重启不丢，dashboard 可选中）
                const createRes = await fetch('/api/credentials/create', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name, ...credPayload })
                });
                const createData = await createRes.json();
                if (createData.code !== 1) {
                    alert(`❌ 保存凭证失败: ${createData.msg || 'CREATE_FAILED'}`);
                    return;
                }

                // 3) 用已入库凭证取真实 totalEq（与仪表盘同一条链），用于回显
                let equityText = '已连接';
                const cid = createData.data && createData.data.id;
                if (cid) {
                    const chkRes = await fetch('/api/account/exchange-connections/test', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ credential_id: cid })
                    });
                    const chkData = await chkRes.json();
                    const eq = chkData.data && chkData.data.equity;
                    if (chkData.code === 1 && eq != null) {
                        equityText = `$${Number(eq).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
                    }
                }

                alert(`✅ 连接成功！账户余额: ${equityText}`);
                closeApiAccountModal();
                loadAccountsList();
                // 刷新仪表盘总权益（清除 30s 缓存前的旧回退值）
                if (typeof loadDashboard === 'function') { try { loadDashboard(); } catch (e) {} }
                debugLog('API账户保存成功（标准凭证库）', 'success');
            } catch (e) {
                debugLog(`API账户保存失败: ${e.message}`, 'error');
                alert(`⚠️ 保存失败: ${e.message}`);
            }
        }

        async function loadAccountsList() {
            const res = await ApiService.getCredentials();
            const data = res.data || [];
            const list = Array.isArray(data) ? data : (Array.isArray(data.items) ? data.items : []);
            const isReal = !res._error && res.code === 1;
            updateAccountsList(list, isReal);
        }

        // 绑定添加账户按钮
        document.addEventListener('DOMContentLoaded', () => {
            const btn = document.getElementById('btn-add-account');
            if (btn) btn.addEventListener('click', openApiAccountModal);
        });

        // ========== 真实行情数据（OKX） ==========
        async function fetchRealPrice() {
            try {
                const res = await fetch('/api/market/ticker?symbol=BTC-USDT');
                const data = await res.json();
                if (data.success) {
                    const price = data.data.last;
                    const priceEl = document.getElementById('chart-price');
                    const badgeEl = document.getElementById('data-source-badge');
                    if (priceEl) priceEl.textContent = '$' + price.toLocaleString();
                    if (badgeEl) badgeEl.innerHTML = '<span style="color: #0ecb81; font-size: 11px;">● LIVE 实时数据</span>';
                    debugLog(`真实价格更新: $${price}`, 'info');
                }
            } catch (e) {
                debugLog(`获取真实价格失败: ${e.message}`, 'error');
            }
        }

        // 加载真实持仓
        async function loadRealPositions() {
            try {
                const res = await fetch('/api/account/positions');
                const data = await res.json();
                // 自建后端 account/positions 返回 {code:1,data:{positions:[],items:[]}}（无 success 字段）
                if ((data.success || data.code === 1) && data.data) {
                    const positions = data.data.positions || data.data.items || [];
                    const totalEq = data.data.total_equity || (data.data.equity ? '$' + data.data.equity : null);
                    
                    // 更新总权益显示（仅当有真实值时才覆盖，避免把演示 5,000 顶掉）
                    if (totalEq) {
                        const totalEqEl = document.getElementById('total-equity');
                        if (totalEqEl) totalEqEl.textContent = totalEq.replace('$', '');
                    }
                    
                    // 更新持仓列表
                    const positionsEl = document.getElementById('positions-list');
                    if (positionsEl) {
                        if (positions.length > 0) {
                            positionsEl.innerHTML = positions.map(p => `
                                <div style="padding: 6px 8px; border-bottom: 1px solid var(--border-color); display: flex; justify-content: space-between; font-size: 12px;">
                                    <span style="color: var(--text-primary);">${p.symbol}</span>
                                    <span style="color: var(--text-secondary); font-family: var(--font-mono);">${p.amount} ≈ $${p.value_usd.toLocaleString()}</span>
                                </div>
                            `).join('');
                        } else {
                            positionsEl.innerHTML = '<div style="padding: 8px; color: var(--text-tertiary); font-size: 12px;">暂无持仓</div>';
                        }
                    }
                    debugLog(`持仓更新成功: ${positions.length}个品种`, 'success');
                }
            } catch (e) {
                debugLog(`获取持仓失败: ${e.message}`, 'error');
            }
        }

        // 加载真实K线数据到图表
        // 统一入口：复用 loadKlineData（真实 /api/indicator/kline + 渲染 + 模拟兜底）
        // 历史教训（E009）：此前双调用点并存（indicator/kline 渲染 + market/kline 空拉），
        // 后者每30s拉100根K线却只改badge不画图，属冗余流量；现统一为静默刷新真实图表。
        async function fetchRealKline(symbol = 'BTC-USDT', bar = '1H', limit = 100) {
            return loadKlineData(true);
        }

        // ========== 初始化 ==========
        // 开发模式：自动真实登录自建后端（admin/admin123），不再使用假 dev-token
        (async () => {
            let authed = Auth.isLoggedIn();
            if (!authed) {
                debugLog('自动登录自建后端...', 'info');
                const ok = await Auth.login('admin', 'admin123');
                authed = ok;
            }
            if (authed) {
                _setDemoGlobalBadge(false);
                Auth.showMain();
                initMainChart();
                initLogCenter();
                loadAllData();
                // 启动真实价格轮询（每5秒更新）
                fetchRealPrice();
                setInterval(fetchRealPrice, 5000);
                // 启动真实K线加载（每30秒刷新一次）
                fetchRealKline();
                setInterval(() => fetchRealKline(), 30000);
                // 启动持仓轮询（每30秒更新）
                loadRealPositions();
                setInterval(loadRealPositions, 30000);
            } else {
                Auth.showLogin();
            }
        })();

        // 每30秒刷新一次数据
        setInterval(() => {
            if (Auth.isLoggedIn()) loadAllData();
        }, 30000);

        // 每15秒刷新P1/P2模块卡片（仅在核心引擎页可见时请求，避免空跑）
        setInterval(() => {
            const enginePage = document.getElementById('page-engine');
            if (enginePage && enginePage.classList.contains('active') && Auth.isLoggedIn()) {
                loadP2ModuleCards();
            }
        }, 15000);
    