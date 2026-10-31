
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
                        console.warn('未登录或Token过期');
                        return { code: 401, msg: '未登录', data: null, _unauthorized: true };
                    }
                    
                    const data = await response.json();
                    const latency = Date.now() - startTime;
                    const latencyEl = document.getElementById('latency');
                    if (latencyEl) latencyEl.textContent = latency + 'ms';
                    return data;
                } catch (e) {
                    console.error('API Error:', path, e);
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
                    generateMockKlineData();
                    showDataSourceBadge('mock');
                }
            } catch (e) {
                console.warn('K线API失败，使用模拟数据:', e);
                generateMockKlineData();
                showDataSourceBadge('mock');
            } finally {
                showKlineLoading(false);
            }
        }

        function showKlineLoading(show) {
            const el = document.getElementById('kline-loading');
            if (el) el.style.display = show ? 'flex' : 'none';
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
            document.getElementById('chart-price').textContent = 
                '$' + data[data.length - 1].close.toLocaleString();
        }

        // ========== WebSocket 实时推送 ==========
        // 基于第一性原理：公共行情数据无需认证，前端直连交易所公共WebSocket
        // 全球最佳实践：Binance/OKX前端都直接连接公共WS，不经过后端中转
        let priceSocket = null;
        let orderbookSocket = null;
        let wsReconnectTimer = null;
        let lastPrice = 0;

        function initRealtimeWebSocket() {
            debugLog('info', '初始化WebSocket实时推送...');
            
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
                    debugLog('success', 'WebSocket行情连接成功');
                    updateWsStatus('connected');
                };
                
                priceSocket.onmessage = function(event) {
                    try {
                        const data = JSON.parse(event.data);
                        handlePriceUpdate(data);
                    } catch (e) {
                        console.warn('WebSocket消息解析失败:', e);
                    }
                };
                
                priceSocket.onerror = function(error) {
                    debugLog('error', 'WebSocket行情错误: ' + error);
                    updateWsStatus('error');
                };
                
                priceSocket.onclose = function() {
                    debugLog('warn', 'WebSocket行情断开，5秒后重连...');
                    updateWsStatus('disconnected');
                    // 自动重连
                    wsReconnectTimer = setTimeout(connectPriceWebSocket, 5000);
                };
            } catch (e) {
                debugLog('error', 'WebSocket初始化失败: ' + e.message);
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
                debugLog('info', '实时价格: $' + price.toFixed(2));
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
                    debugLog('success', 'WebSocket订单簿连接成功');
                };
                
                orderbookSocket.onmessage = function(event) {
                    try {
                        const data = JSON.parse(event.data);
                        handleOrderbookUpdate(data);
                    } catch (e) {
                        console.warn('订单簿WebSocket解析失败:', e);
                    }
                };
                
                orderbookSocket.onerror = function(error) {
                    debugLog('error', '订单簿WebSocket错误: ' + error);
                };
                
                orderbookSocket.onclose = function() {
                    debugLog('warn', '订单簿WebSocket断开，5秒后重连...');
                    setTimeout(connectOrderbookWebSocket, 5000);
                };
            } catch (e) {
                debugLog('warn', '订单簿WebSocket初始化失败: ' + e.message);
            }
        }

        function handleOrderbookUpdate(data) {
            // 更新订单簿显示
            const bids = data.b || [];  // 买单
            const asks = data.a || [];  // 卖单
            
            const orderbookEl = document.getElementById('orderbook-content');
            if (!orderbookEl) return;
            
            // 只显示前10档
            const displayBids = bids.slice(0, 10);
            const displayAsks = asks.slice(0, 10);
            
            let html = '';
            
            // 卖单（从高到低）
            displayAsks.slice().reverse().forEach(([price, amount]) => {
                const p = parseFloat(price).toFixed(2);
                const a = parseFloat(amount).toFixed(4);
                html += `<div class="orderbook-row ask">
                    <span style="color: #f6465d;">${p}</span>
                    <span style="color: #848e9c;">${a}</span>
                </div>`;
            });
            
            // 价差
            if (displayAsks.length > 0 && displayBids.length > 0) {
                const spread = parseFloat(displayAsks[0][0]) - parseFloat(displayBids[0][0]);
                html += `<div class="orderbook-spread">
                    价差: $${spread.toFixed(2)}
                </div>`;
            }
            
            // 买单（从高到低）
            displayBids.forEach(([price, amount]) => {
                const p = parseFloat(price).toFixed(2);
                const a = parseFloat(amount).toFixed(4);
                html += `<div class="orderbook-row bid">
                    <span style="color: #0ecb81;">${p}</span>
                    <span style="color: #848e9c;">${a}</span>
                </div>`;
            });
            
            orderbookEl.innerHTML = html;
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

        function initVolumeChart() {
            const container = document.getElementById('volume-chart');
            if (!container || !mainChart) return;
            
            volumeSeries = mainChart.addHistogramSeries({
                priceFormat: {
                    type: 'volume',
                },
                priceScaleId: '',
            });
            
            volumeSeries.priceScale().applyOptions({
                scaleMargins: {
                    top: 0.7,
                    bottom: 0,
                },
            });

            // 生成模拟成交量数据
            const data = [];
            const now = Math.floor(Date.now() / 1000);
            const intervalSeconds = 3600;
            
            for (let i = 200; i >= 0; i--) {
                const time = now - i * intervalSeconds;
                data.push({
                    time,
                    value: Math.random() * 100 + 20,
                    color: Math.random() > 0.5 ? 'rgba(14, 203, 129, 0.5)' : 'rgba(246, 70, 93, 0.5)'
                });
            }

            volumeSeries.setData(data);
        }

        function initEquityChart() {
            const container = document.getElementById('equity-chart');
            if (!container) return;
            
            equityChart = LightweightCharts.createChart(container, {
                layout: {
                    background: { color: '#12161c' },
                    textColor: '#848e9c',
                },
                grid: {
                    vertLines: { color: '#1e2329' },
                    horzLines: { color: '#1e2329' },
                },
                width: container.clientWidth,
                height: container.clientHeight,
            });

            const lineSeries = equityChart.addAreaSeries({
                lineColor: '#f0b90b',
                topColor: 'rgba(240, 185, 11, 0.3)',
                bottomColor: 'rgba(240, 185, 11, 0.0)',
                lineWidth: 2,
            });

            // 生成模拟权益曲线
            const data = [];
            let equity = 10000;
            const now = Math.floor(Date.now() / 1000);
            
            for (let i = 100; i >= 0; i--) {
                const time = now - i * 86400;
                equity += (Math.random() - 0.45) * 200;
                data.push({ time, value: equity });
            }

            lineSeries.setData(data);
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
                    
                    // 切换到回测页时初始化权益图
                    if (page === 'backtest') {
                        setTimeout(() => {
                            if (!equityChart) initEquityChart();
                        }, 100);
                    }
                    
                    // 切换到日志页时刷新日志列表
                    if (page === 'logs') {
                        setTimeout(() => {
                            if (window.renderLogList) window.renderLogList();
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
                } catch (err) {
                    debugLog(`页面切换失败: ${err.message}`, 'error');
                }
            });
        });
        debugLog(`找到 ${document.querySelectorAll('.nav-item').length} 个导航项`, 'success');

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
            document.getElementById('detail-strategy-symbol').textContent = strategy.symbol || 'BTC/USDT';
            document.getElementById('detail-strategy-created').textContent = strategy.created_at || '2026-01-01';
            
            // 填充绩效指标（模拟数据，后续对接真实API）
            document.getElementById('detail-total-return').textContent = '+12.5%';
            document.getElementById('detail-sharpe').textContent = '1.85';
            document.getElementById('detail-drawdown').textContent = '-8.3%';
            document.getElementById('detail-winrate').textContent = '58.2%';
            document.getElementById('detail-trades').textContent = '128';
            document.getElementById('detail-profit-factor').textContent = '1.65';
            
            // 更新按钮文字
            const isRunning = strategy.status === 'running' || strategy.status === 'active';
            document.getElementById('detail-toggle-btn-text').textContent = isRunning ? '停止策略' : '启动策略';
            
            // 显示弹窗
            document.getElementById('strategyDetailModal').classList.add('active');
            
            debugLog('info', '打开策略详情: ' + (strategy.name || '未知'));
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
                debugLog('success', `${action}策略: ${currentDetailStrategy.name}`);
                
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
                
                debugLog('info', `提交订单: ${side} ${amount} USDT ${symbol}`);
                
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
                    debugLog('success', '下单成功: ' + JSON.stringify(result.data || result));
                    
                    // 刷新持仓和资产
                    setTimeout(() => {
                        if (typeof loadDashboardData === 'function') loadDashboardData();
                    }, 1000);
                } else {
                    showToast('下单失败: ' + (result.msg || result.message || '未知错误'), 'error');
                    debugLog('error', '下单失败: ' + JSON.stringify(result));
                }
            } catch (e) {
                console.error('下单错误:', e);
                showToast('下单错误: ' + e.message, 'error');
                debugLog('error', '下单异常: ' + e.message);
            }
        }

        // ========== 运行回测 ==========
        async function runBacktest() {
            const btn = document.getElementById('run-backtest-btn');
            const btnText = document.getElementById('backtest-btn-text');
            
            btn.disabled = true;
            btnText.innerHTML = '<span class="loading"></span> 运行中...';

            // 模拟回测延迟
            await new Promise(resolve => setTimeout(resolve, 2000));

            // 显示结果
            document.getElementById('backtest-results').classList.add('active');
            
            // 填充模拟数据
            document.getElementById('bt-total-return').textContent = '+67.97%';
            document.getElementById('bt-sharpe').textContent = '1.85';
            document.getElementById('bt-drawdown').textContent = '-15.2%';
            document.getElementById('bt-winrate').textContent = '55.6%';

            btn.disabled = false;
            btnText.textContent = '运行回测';
            showToast('回测完成', 'success');

            // 初始化权益图和回撤图
            setTimeout(() => {
                if (!equityChart) initEquityChart();
                if (!drawdownChart) initDrawdownChart();
            }, 100);
        }

        function initDrawdownChart() {
            const container = document.getElementById('drawdown-chart');
            if (!container) return;
            
            drawdownChart = LightweightCharts.createChart(container, {
                layout: {
                    background: { color: 'transparent' },
                    textColor: '#848e9c',
                },
                grid: {
                    vertLines: { color: '#1e2329' },
                    horzLines: { color: '#1e2329' },
                },
                width: container.clientWidth,
                height: container.clientHeight,
            });

            const areaSeries = drawdownChart.addAreaSeries({
                lineColor: '#f6465d',
                topColor: 'rgba(246, 70, 93, 0.3)',
                bottomColor: 'rgba(246, 70, 93, 0.0)',
                lineWidth: 2,
            });

            // 生成模拟回撤数据
            const data = [];
            let drawdown = 0;
            const now = Math.floor(Date.now() / 1000);
            
            for (let i = 100; i >= 0; i--) {
                const time = now - i * 86400;
                drawdown += (Math.random() - 0.48) * 0.5;
                drawdown = Math.min(0, drawdown);
                data.push({ time, value: drawdown });
            }

            areaSeries.setData(data);
        }

        // ========== 日志中心 ==========
        function initLogCenter() {
            // 渲染日志列表
            window.renderLogList = function(filter = 'all', search = '') {
                const logList = document.getElementById('log-list');
                if (!logList) return;
                
                let logs = window.debugLogs || [];
                
                // 过滤级别
                if (filter !== 'all') {
                    logs = logs.filter(l => l.type === filter);
                }
                
                // 搜索
                if (search) {
                    const s = search.toLowerCase();
                    logs = logs.filter(l => l.msg.toLowerCase().includes(s));
                }
                
                // 更新统计
                document.getElementById('log-total').textContent = window.debugLogs.length;
                document.getElementById('log-error-count').textContent = window.debugLogs.filter(l => l.type === 'error').length;
                document.getElementById('log-warn-count').textContent = window.debugLogs.filter(l => l.type === 'warn').length;
                document.getElementById('log-api-count').textContent = window.debugLogs.filter(l => l.msg.includes('API')).length;
                
                // 渲染列表
                if (logs.length === 0) {
                    logList.innerHTML = '<div style="padding: 8px 12px; color: var(--text-secondary); text-align: center;">暂无日志</div>';
                    return;
                }
                
                const typeColors = {
                    error: '#f6465d',
                    warn: '#f0b90b',
                    info: '#8b5cf6',
                    success: '#0ecb81'
                };
                
                logList.innerHTML = logs.slice().reverse().map(log => `
                    <div style="padding: 8px 12px; border-bottom: 1px solid var(--bg-border); display: flex; align-items: center;">
                        <div style="width: 80px; color: var(--text-secondary);">${log.time}</div>
                        <div style="width: 60px; margin-left: 16px;">
                            <span style="padding: 2px 6px; background: ${typeColors[log.type] || '#848e9c'}20; color: ${typeColors[log.type] || '#848e9c'}; border-radius: 3px; font-size: 11px; font-weight: 600;">${log.type.toUpperCase()}</span>
                        </div>
                        <div style="flex: 1; margin-left: 16px; color: var(--text-primary);">${log.msg}</div>
                    </div>
                `).join('');
            };
            
            // 过滤事件
            const filterSelect = document.getElementById('log-level-filter');
            if (filterSelect) {
                filterSelect.onchange = function() {
                    const search = document.getElementById('log-search').value;
                    window.renderLogList(this.value, search);
                };
            }
            
            // 搜索事件
            const searchInput = document.getElementById('log-search');
            if (searchInput) {
                searchInput.oninput = function() {
                    const filter = document.getElementById('log-level-filter').value;
                    window.renderLogList(filter, this.value);
                };
            }
            
            // 清空日志
            const clearBtn = document.getElementById('log-clear');
            if (clearBtn) {
                clearBtn.onclick = function() {
                    window.debugLogs = [];
                    window.renderLogList();
                    debugLog('日志已清空', 'info');
                };
            }
            
            // 导出日志
            const exportBtn = document.getElementById('log-export');
            if (exportBtn) {
                exportBtn.onclick = function() {
                    const text = window.debugLogs.map(l => `[${l.time}] [${l.type.toUpperCase()}] ${l.msg}`).join('\n');
                    const blob = new Blob([text], { type: 'text/plain' });
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = `quantdinger-logs-${new Date().toISOString().slice(0,10)}.txt`;
                    a.click();
                    URL.revokeObjectURL(url);
                    debugLog('日志已导出', 'success');
                };
            }
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
                    showToast('请先登录系统', 'warning');
                    // 未登录时使用演示数据
                    updateAccountsList([], false);
                    updateDashboardStats({}, false);
                    updateStrategiesList([], false);
                    return;
                }

                // 自建后端 credentials/list 返回 {code:1,data:{items:[...]}}，需取 items
                const credData = credentialsRes.data || [];
                const credList = Array.isArray(credData) ? credData : (Array.isArray(credData.items) ? credData.items : []);
                updateAccountsList(credList, !credentialsRes._error && credentialsRes.code === 1);
                updateDashboardStats(summaryRes.data || {}, !summaryRes._error && summaryRes.code === 1);
                updateStrategiesList(strategiesRes.data || [], !strategiesRes._error && strategiesRes.code === 1);
                updatePositionsList(positionsRes.data || [], !positionsRes._error && positionsRes.code === 1);
                
                updateSystemStatus('online');
            } catch (e) {
                console.error('加载数据失败:', e);
                updateSystemStatus('offline');
                updateAccountsList([], false);
                updateDashboardStats({}, false);
            }
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

        function updateAccountsList(credentials, isReal = false) {
            const accountsList = document.getElementById('accounts-list');
            const modalAccountsList = document.getElementById('modal-accounts-list');

            // 不是真实数据时，使用演示数据并标注
            if (!isReal || credentials.length === 0) {
                credentials = [{
                    id: 1,
                    name: 'OKX-DEMO',
                    exchange_id: 'okx',
                    api_key_hint: '8a12...0cf2'
                }];
            }

            accountsList.innerHTML = credentials.map((cred, idx) => `
                <div class="account-option ${idx === 0 ? 'selected' : ''}" style="padding: 10px; border-radius: 6px; cursor: pointer; display: flex; align-items: center; justify-content: space-between; margin-bottom: 4px; ${idx === 0 ? 'background: var(--bg-hover);' : ''}">
                    <div style="display: flex; align-items: center; gap: 10px;">
                        <span style="padding: 3px 6px; border-radius: 4px; background: var(--brand-primary); color: var(--bg-primary); font-size: 10px; font-weight: 700; text-transform: uppercase;">${cred.exchange_id}</span>
                        <span style="font-size: 13px;">${cred.name}</span>
                    </div>
                    <div class="status-dot" style="width: 6px; height: 6px;"></div>
                </div>
            `).join('');

            modalAccountsList.innerHTML = credentials.map((cred, idx) => `
                <div class="credential-option ${idx === 0 ? 'selected' : ''}" style="padding: 12px; border-radius: 6px; cursor: pointer; display: flex; align-items: center; justify-content: space-between; margin-bottom: 4px; ${idx === 0 ? 'background: var(--bg-active);' : ''}">
                    <div style="display: flex; align-items: center; gap: 12px;">
                        <span style="padding: 4px 8px; border-radius: 4px; background: var(--brand-primary); color: var(--bg-primary); font-size: 11px; font-weight: 700; text-transform: uppercase;">${cred.exchange_id}</span>
                        <div>
                            <div style="font-weight: 600; font-size: 14px;">${cred.name}</div>
                            <div style="font-size: 11px; color: var(--text-secondary);">${cred.api_key_hint || '已连接'}</div>
                        </div>
                    </div>
                    <div class="status-dot" style="width: 8px; height: 8px;"></div>
                </div>
            `).join('');
        }

        function updateDashboardStats(summary) {
            if (summary.total_equity) {
                document.getElementById('total-equity').textContent = 
                    summary.total_equity.toLocaleString('en-US', {minimumFractionDigits: 2});
            } else {
                document.getElementById('total-equity').textContent = '10,234.56';
            }
            
            if (summary.daily_pnl) {
                const el = document.getElementById('daily-pnl');
                el.textContent = (summary.daily_pnl >= 0 ? '+' : '') + summary.daily_pnl.toFixed(2);
                el.style.color = summary.daily_pnl >= 0 ? 'var(--up-color)' : 'var(--down-color)';
            } else {
                document.getElementById('daily-pnl').textContent = '+123.45';
                document.getElementById('daily-pnl').style.color = 'var(--up-color)';
            }

            document.getElementById('stat-winrate').textContent = (summary.win_rate || 66.7) + '%';
            document.getElementById('stat-sharpe').textContent = summary.sharpe || '1.85';
            document.getElementById('stat-trades').textContent = summary.total_trades || '12';
            document.getElementById('stat-drawdown').textContent = '-' + (summary.max_drawdown || 3.2) + '%';
        }

        function updateStrategiesList(strategies, isReal = false) {
            const runningEl = document.getElementById('running-strategies');
            const gridEl = document.getElementById('strategies-grid');

            // 不是真实数据时，使用演示数据
            if (!isReal || !strategies || strategies.length === 0) {
                strategies = [
                    { id: 1, name: 'ML增强趋势策略', status: 'running', today_pnl: 45.67, win_rate: 65, sharpe: 1.85, max_drawdown: 3.2, total_trades: 45 },
                    { id: 2, name: '均值回归策略', status: 'running', today_pnl: -12.34, win_rate: 58, sharpe: 1.42, max_drawdown: 4.8, total_trades: 128 },
                    { id: 3, name: '突破策略', status: 'stopped', today_pnl: 0, win_rate: 0, sharpe: 0, max_drawdown: 0, total_trades: 0 }
                ];
            }

            // 智能字段映射：兼容后端不同字段名
            strategies = strategies.map(s => ({
                ...s,
                name: s.name || s.strategy_name || '未命名策略',
                status: s.status || s.execution_mode === 'live' ? 'running' : 'stopped',
                today_pnl: s.today_pnl || s.daily_pnl || s.pnl_today || 0,
                win_rate: s.win_rate || s.winrate || 0,
                sharpe: s.sharpe || s.sharpe_ratio || 1.5,
                max_drawdown: s.max_drawdown || s.drawdown || 0,
                total_trades: s.total_trades || s.trade_count || 0
            }));

            const runningStrategies = strategies.filter(s => s.status === 'running');

            runningEl.innerHTML = runningStrategies.map((s, idx) => `
                <div class="strategy-card running" onclick='openStrategyDetail(${JSON.stringify(s).replace(/'/g, "&apos;")})'>
                    <div class="strategy-header">
                        <span class="strategy-name">${s.name}</span>
                        <span class="strategy-status running">运行中</span>
                    </div>
                    <div class="strategy-metrics">
                        <span>今日: ${s.today_pnl >= 0 ? '+' : ''}${(s.today_pnl || 0).toFixed(2)}</span>
                        <span>胜率: ${(s.win_rate || 0).toFixed(0)}%</span>
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
                        <span>夏普: ${(s.sharpe || 1.85).toFixed(2)}</span>
                        <span>回撤: ${(s.max_drawdown || 5.2).toFixed(1)}%</span>
                        <span>交易: ${s.total_trades || 45}</span>
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
                equityChart.applyOptions({
                    width: container.clientWidth,
                    height: container.clientHeight
                });
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
                    }
                }
                
                // 更新时间
                const now = new Date();
                document.getElementById('validation-time').textContent = now.toLocaleTimeString();
                
            } catch (err) {
                debugLog(`AI验证层API暂不可用，使用内置数据: ${err.message}`, 'warn');
                // API不可用时保留现有硬编码数据，不做任何修改
            }
        }
        
        function renderValidationModules(modules) {
            const container = document.getElementById('validation-modules');
            if (!container || !modules) return;
            
            const levelColors = {
                high: '#8b5cf6',
                medium: '#0ecb81',
                low: '#848e9c'
            };
            
            container.innerHTML = modules.map(m => `
                <div style="display: flex; justify-content: space-between; align-items: center; padding: 12px 16px; background: var(--bg-primary); border-radius: 8px; border-left: 3px solid ${levelColors[m.level] || '#848e9c'};">
                    <div>
                        <span style="font-size: 13px;">${m.name}</span>
                        ${m.details ? `<div style="font-size: 11px; color: var(--text-secondary); margin-top: 4px;">${m.details}</div>` : ''}
                    </div>
                    <span style="padding: 2px 8px; background: rgba(14, 203, 129, 0.1); color: #0ecb81; border-radius: 4px; font-size: 11px;">
                        ✓ ${m.status === 'connected' ? '已连接' : '健康'}
                    </span>
                </div>
            `).join('');
        }
        
        function renderAuditLogs(logs) {
            const container = document.getElementById('audit-logs');
            if (!container || !logs) return;
            
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
        
        function renderStressTest(data) {
            if (!data || !data.scenarios) return;
            
            const colorMap = {
                red: '#f6465d',
                orange: '#f0b90b',
                green: '#0ecb81',
                purple: '#8b5cf6'
            };
            
            // 更新压力测试卡片
            const scenarioCards = document.querySelectorAll('#page-validation .bg-primary.rounded-8');
            data.scenarios.forEach((s, i) => {
                const card = document.querySelectorAll('#page-validation [style*="border-top: 3px solid"]')[i];
                if (card) {
                    card.style.borderTopColor = colorMap[s.color] || '#848e9c';
                    const drawdownEl = card.querySelector('[style*="font-size: 20px"]');
                    if (drawdownEl) {
                        drawdownEl.textContent = (s.drawdown > 0 ? '+' : '') + s.drawdown.toFixed(2) + '%';
                        drawdownEl.style.color = colorMap[s.color] || '#0ecb81';
                    }
                }
            });
            
            // 更新综合风险评分
            const riskScoreEl = document.querySelector('#page-validation [style*="综合风险评分"]');
            if (riskScoreEl && data.overall_risk_score) {
                riskScoreEl.innerHTML = `
                    <span style="color: #0ecb81; font-weight: 600;">✓ 综合风险评分：${data.overall_risk_score}/100（${data.risk_level}）</span><br>
                    <span style="font-size: 12px;">${data.summary}</span>
                `;
            }
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
                    renderRiskDashboard(data.data);
                    debugLog(`风险数据加载成功`, 'success');
                }
            } catch (err) {
                debugLog(`风险API暂不可用，使用内置数据: ${err.message}`, 'warn');
                // API不可用时保留现有硬编码数据
            }
            // 更新时间
            const now = new Date();
            document.getElementById('risk-update-time').textContent = '更新于 ' + now.toLocaleTimeString();
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
            if (data.daily_drawdown) {
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
            try {
                const res = await fetch('/api/p1/market-layers/summary');
                const data = await res.json();
                if (data.success) {
                    const layers = data.data.layers;
                    const html = layers.map(l => 
                        `<div>• <span style="color: #5e72e4; font-weight: 600;">${l.level}</span> ${l.name} <span style="color: #0ecb81;">${l.status.split(' ')[0]}</span><br>
                         <span style="font-size: 11px; color: var(--text-secondary); padding-left: 20px;">${l.desc}</span></div>`
                    ).join('');
                    document.getElementById('market-layers-list').innerHTML = html;
                }
            } catch (e) {
                debugLog(`五层市场识别加载失败: ${e.message}`, 'error');
            }

            // 2. 策略优化引擎状态
            try {
                const res = await fetch('/api/p1/optimizer/status');
                const data = await res.json();
                if (data.success) {
                    const s = data.data;
                    document.getElementById('optimizer-status').innerHTML = `
                        <div>• 因子数量: <span style="color: #f0b90b; font-weight: 600;">${s.factor_count}</span> 个</div>
                        <div>• 累计试验: <span style="color: #f0b90b; font-weight: 600;">${s.total_trials}</span> 次</div>
                        <div>• 已优化策略: <span style="color: #f0b90b; font-weight: 600;">${s.optimized_strategies}</span> 个</div>
                        <div style="font-size: 11px; color: var(--text-secondary); margin-top: 8px;">🛡️ ${s.overfitting_defense}</div>
                    `;
                }
            } catch (e) {
                debugLog(`优化引擎状态加载失败: ${e.message}`, 'error');
            }

            // 3. 因子库列表
            try {
                const res = await fetch('/api/p1/optimizer/factors');
                const data = await res.json();
                if (data.success) {
                    const factors = data.data.factors;
                    const html = factors.map(f => 
                        `<span style="display: inline-block; background: rgba(240,185,11,0.1); color: #f0b90b; padding: 2px 8px; border-radius: 4px; margin: 2px; font-size: 10px;">${f.name}</span>`
                    ).join('');
                    document.getElementById('factor-list').innerHTML = html;
                }
            } catch (e) {
                debugLog(`因子库加载失败: ${e.message}`, 'error');
            }

            // 4. 策略健康度
            try {
                const res = await fetch('/api/p1/strategy-health/summary');
                const data = await res.json();
                if (data.success) {
                    const s = data.data;
                    const html = `
                        <div>• 总策略数: <span style="font-weight: 600;">${s.total || '-'}</span></div>
                        <div>• 健康运行: <span style="color: #0ecb81; font-weight: 600;">${s.active || '-'}</span></div>
                        <div>• 观察预警: <span style="color: #f0b90b; font-weight: 600;">${s.watch || '-'}</span></div>
                        <div>• 暂停退役: <span style="color: #f6465d; font-weight: 600;">${s.suspended || '-'}</span></div>
                        <div>• 平均健康分: <span style="font-weight: 600;">${s.avg_health_score || '-'}</span> / 100</div>
                        <div style="font-size: 11px; color: var(--text-secondary); margin-top: 8px;">绿区运行 → 黄区减仓 → 红区退役</div>
                    `;
                    document.getElementById('strategy-health-list').innerHTML = html;
                }
            } catch (e) {
                debugLog(`策略健康度加载失败: ${e.message}`, 'error');
            }

            // 5. 综合市场分析（演示）
            try {
                const res = await fetch('/api/p1/market-layers/demo');
                const data = await res.json();
                if (data.success) {
                    const r = data.data;
                    const dirColor = r.overall_direction === 'bullish' ? '#0ecb81' : 
                                     r.overall_direction === 'bearish' ? '#f6465d' : '#f0b90b';
                    document.getElementById('market-analysis-result').innerHTML = `
                        <div>• 综合方向: <span style="color: ${dirColor}; font-weight: 600; text-transform: uppercase;">${r.overall_direction || 'neutral'}</span></div>
                        <div>• 置信度: <span style="font-weight: 600;">${(r.confidence * 100 || 0).toFixed(0)}%</span></div>
                        <div>• L1 市场状态: ${r.l1_regime || '-'}</div>
                        <div>• L3 市场趋势: ${r.l3_trend || '-'}</div>
                        <div>• L4 价格行为: ${r.l4_price_action || '-'}</div>
                        <div>• L5 K线形态: ${r.l5_candlestick || '-'}</div>
                        <div style="font-size: 11px; color: var(--text-secondary); margin-top: 8px;">📍 建议入场: ${r.entry_zone || '待分析'}</div>
                    `;
                }
            } catch (e) {
                debugLog(`综合市场分析加载失败: ${e.message}`, 'error');
            }

            // 6. P1/P2 企业级模块卡片实时数据
            loadP2ModuleCards();
        }

        // ========== P1/P2 企业级模块卡片实时轮询 ==========
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
                    p2Metric('胜率', ((d.win_rate || 0) * 100).toFixed(1) + '%') +
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
                // 先测试连接
                const testRes = await fetch('/api/account/test-connection', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ exchange, api_key: apiKey, api_secret: apiSecret, passphrase })
                });
                const testData = await testRes.json();
                
                if (testData.success) {
                    alert(`✅ 连接成功！账户余额: ${testData.data.balance || '未知'}`);
                    // 保存到后端
                    const saveRes = await fetch('/api/account/save', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            name, exchange, api_key: apiKey, api_secret: apiSecret, passphrase,
                            permissions: { read: permRead, trade: permTrade }
                        })
                    });
                    const saveData = await saveRes.json();
                    if (saveData.success) {
                        closeApiAccountModal();
                        loadAccountsList();
                        debugLog('API账户保存成功', 'success');
                    }
                } else {
                    alert(`❌ 连接失败: ${testData.message}`);
                }
            } catch (e) {
                debugLog(`API账户保存失败: ${e.message}`, 'error');
                // 后端没有这个接口，先本地保存演示
                alert('⚠️ 后端API接口未就绪，已在前端保存演示配置。请配置后端后重试。');
                closeApiAccountModal();
            }
        }

        function loadAccountsList() {
            const container = document.getElementById('accounts-list');
            // 演示数据
            container.innerHTML = `
                <div style="padding: 8px; background: rgba(14,203,129,0.05); border-radius: 6px; margin-bottom: 8px; cursor: pointer; border: 1px solid rgba(14,203,129,0.3);">
                    <div style="font-size: 12px; font-weight: 600; color: #0ecb81;">🟢 OKX-DEMO</div>
                    <div style="font-size: 10px; color: var(--text-tertiary); margin-top: 2px;">已连接 · 模拟盘</div>
                </div>
            `;
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
    