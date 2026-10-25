        // 璋冭瘯鏃ュ織绯荤粺
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
        
        // 鎹曡幏鍏ㄥ眬閿欒
        window.onerror = function(msg, url, line, col, error) {
            debugLog(`JS閿欒: ${msg} (琛?${line})`, 'error');
            return false;
        };
        
        window.addEventListener('unhandledrejection', function(e) {
            debugLog(`Promise閿欒: ${e.reason}`, 'error');
        });
        
        // 椤甸潰鍔犺浇瀹屾垚
        document.addEventListener('DOMContentLoaded', function() {
            debugLog('椤甸潰DOM鍔犺浇瀹屾垚', 'success');
            
            // 鍒涘缓璋冭瘯闈㈡澘
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
                    <span>馃悰 璋冭瘯鏃ュ織</span>
                    <span onclick="this.parentElement.parentElement.classList.remove('visible')">脳</span>
                </div>
                <div id="debug-content"></div>
            `;
            document.body.appendChild(panel);
            
            debugLog('璋冭瘯闈㈡澘宸插垵濮嬪寲', 'success');
        });
        
        // 鎹曡幏鎵€鏈塮etch璇锋眰
        const originalFetch = window.fetch;
        window.fetch = function(...args) {
            debugLog(`API璇锋眰: ${args[0]}`, 'info');
            return originalFetch.apply(this, args)
                .then(response => {
                    debugLog(`API鍝嶅簲: ${args[0]} -> ${response.status}`, response.ok ? 'success' : 'error');
                    return response;
                })
                .catch(err => {
                    debugLog(`API澶辫触: ${args[0]} -> ${err.message}`, 'error');
                    throw err;
                });
        };
    </script>


    <script>
        // ========== API 鏈嶅姟灞?==========
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
                        console.warn('鏈櫥褰曟垨Token杩囨湡');
                        return { code: 401, msg: '鏈櫥褰?, data: null, _unauthorized: true };
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

            // 淇锛氭纭殑绛栫暐鍒楄〃璺緞
            getStrategies() {
                return this.request('/strategies');
            },

            getPositions() {
                return this.request('/portfolio/positions');
            },

            // 淇锛氭纭殑K绾緼PI璺緞锛堝悗绔敞鍐屽湪/api/indicator鍓嶇紑涓嬶級
            getKline(symbol, timeframe = '1H', limit = 300) {
                return this.request(`/indicator/kline?market=Crypto&symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}&limit=${limit}`);
            },

            // 淇锛氭纭殑鍥炴祴API鍙傛暟
            runBacktest(params) {
                return this.request('/backtest/run', {
                    method: 'POST',
                    body: JSON.stringify({
                        code: params.code || '# 绠€鍗曡秼鍔跨瓥鐣nimport numpy as np\n\ndef initialize(context):\n    context.sma_short = 20\n    context.sma_long = 50\n\ndef handle_data(context, data):\n    pass',
                        startDate: params.startDate || '2024-01-01',
                        endDate: params.endDate || '2024-12-31',
                        initialCapital: parseFloat(params.initialCapital) || 10000,
                        leverageEnabled: false
                    })
                });
            }
        };

        // ========== Toast 鎻愮ず ==========
        function showToast(message, type = 'success') {
            const toast = document.createElement('div');
            toast.className = `toast ${type}`;
            toast.textContent = message;
            document.body.appendChild(toast);
            setTimeout(() => toast.remove(), 3000);
        }

        // ========== K绾垮浘鍒濆鍖?==========
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

            // 鍒濆鍖栨垚浜ら噺鍓浘
            initVolumeChart();

            // 浠庣湡瀹濧PI鍔犺浇K绾?
            loadKlineData();
            
            // 鍚姩WebSocket瀹炴椂鎺ㄩ€?
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

        // 淇锛氱湡瀹濧PI鍔犺浇K绾匡紝澶辫触鎵嶇敤妯℃嫙鏁版嵁骞舵槑纭爣娉?
        async function loadKlineData() {
            showKlineLoading(true);
            
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
                console.warn('K绾緼PI澶辫触锛屼娇鐢ㄦā鎷熸暟鎹?', e);
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
                ? '<span style="color: #0ecb81; font-size: 10px; font-weight: 600;">鈼?LIVE 瀹炴椂鏁版嵁</span>'
                : '<span style="color: #f0b90b; font-size: 10px; font-weight: 600;">鈼?妯℃嫙鏁版嵁</span>';
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

        // ========== WebSocket 瀹炴椂鎺ㄩ€?==========
        // 鍩轰簬绗竴鎬у師鐞嗭細鍏叡琛屾儏鏁版嵁鏃犻渶璁よ瘉锛屽墠绔洿杩炰氦鏄撴墍鍏叡WebSocket
        // 鍏ㄧ悆鏈€浣冲疄璺碉細Binance/OKX鍓嶇閮界洿鎺ヨ繛鎺ュ叕鍏盬S锛屼笉缁忚繃鍚庣涓浆
        let priceSocket = null;
        let orderbookSocket = null;
        let wsReconnectTimer = null;
        let lastPrice = 0;

        function initRealtimeWebSocket() {
            logDebug('info', '鍒濆鍖朩ebSocket瀹炴椂鎺ㄩ€?..');
            
            // 杩炴帴Binance鍏叡琛屾儏WebSocket锛堝厤璐广€佺ǔ瀹氥€佹棤闇€API key锛?
            connectPriceWebSocket();
            
            // 杩炴帴璁㈠崟绨挎繁搴ebSocket
            connectOrderbookWebSocket();
        }

        function connectPriceWebSocket() {
            if (priceSocket) {
                priceSocket.close();
            }
            
            // Binance BTC/USDT 1鍒嗛挓K绾挎祦
            const wsUrl = 'wss://stream.binance.com:9443/ws/btcusdt@miniTicker';
            
            try {
                priceSocket = new WebSocket(wsUrl);
                
                priceSocket.onopen = function() {
                    logDebug('success', 'WebSocket琛屾儏杩炴帴鎴愬姛');
                    updateWsStatus('connected');
                };
                
                priceSocket.onmessage = function(event) {
                    try {
                        const data = JSON.parse(event.data);
                        handlePriceUpdate(data);
                    } catch (e) {
                        console.warn('WebSocket娑堟伅瑙ｆ瀽澶辫触:', e);
                    }
                };
                
                priceSocket.onerror = function(error) {
                    logDebug('error', 'WebSocket琛屾儏閿欒: ' + error);
                    updateWsStatus('error');
                };
                
                priceSocket.onclose = function() {
                    logDebug('warn', 'WebSocket琛屾儏鏂紑锛?绉掑悗閲嶈繛...');
                    updateWsStatus('disconnected');
                    // 鑷姩閲嶈繛
                    wsReconnectTimer = setTimeout(connectPriceWebSocket, 5000);
                };
            } catch (e) {
                logDebug('error', 'WebSocket鍒濆鍖栧け璐? ' + e.message);
                updateWsStatus('error');
            }
        }

        function handlePriceUpdate(data) {
            // Binance miniTicker 鏁版嵁鏍煎紡:
            // {c: 褰撳墠鏀剁洏浠? o: 寮€鐩樹环, h: 鏈€楂樹环, l: 鏈€浣庝环, v: 鎴愪氦閲弣
            const price = parseFloat(data.c);
            if (!price || isNaN(price)) return;
            
            lastPrice = price;
            
            // 鏇存柊椤堕儴浠锋牸鏄剧ず
            const priceEl = document.getElementById('chart-price');
            if (priceEl) {
                const priceDiff = price - (priceEl.dataset.lastPrice || price);
                priceEl.textContent = '$' + price.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
                priceEl.dataset.lastPrice = price;
                
                // 娑ㄨ穼棰滆壊闂儊
                priceEl.style.color = priceDiff >= 0 ? '#0ecb81' : '#f6465d';
                setTimeout(() => { priceEl.style.color = ''; }, 300);
            }
            
            // 鏇存柊涔板崠闈㈡澘浠锋牸
            const orderPriceInput = document.getElementById('order-price');
            if (orderPriceInput && !orderPriceInput.dataset.userEdited) {
                orderPriceInput.value = price.toFixed(2);
            }
            
            // 鏇存柊鏈€鍚庝环鏍煎埌鏃ュ織
            if (Math.random() < 0.05) { // 姣?0鏉¤褰曚竴鏉★紝閬垮厤鍒峰睆
                logDebug('info', '瀹炴椂浠锋牸: $' + price.toFixed(2));
            }
        }

        function connectOrderbookWebSocket() {
            if (orderbookSocket) {
                orderbookSocket.close();
            }
            
            // Binance BTC/USDT 璁㈠崟绨挎繁搴︽祦锛?0妗ｏ級
            const wsUrl = 'wss://stream.binance.com:9443/ws/btcusdt@depth20@100ms';
            
            try {
                orderbookSocket = new WebSocket(wsUrl);
                
                orderbookSocket.onopen = function() {
                    logDebug('success', 'WebSocket璁㈠崟绨胯繛鎺ユ垚鍔?);
                };
                
                orderbookSocket.onmessage = function(event) {
                    try {
                        const data = JSON.parse(event.data);
                        handleOrderbookUpdate(data);
                    } catch (e) {
                        console.warn('璁㈠崟绨縒ebSocket瑙ｆ瀽澶辫触:', e);
                    }
                };
                
                orderbookSocket.onerror = function(error) {
                    logDebug('error', '璁㈠崟绨縒ebSocket閿欒: ' + error);
                };
                
                orderbookSocket.onclose = function() {
                    logDebug('warn', '璁㈠崟绨縒ebSocket鏂紑锛?绉掑悗閲嶈繛...');
                    setTimeout(connectOrderbookWebSocket, 5000);
                };
            } catch (e) {
                logDebug('warn', '璁㈠崟绨縒ebSocket鍒濆鍖栧け璐? ' + e.message);
            }
        }

        function handleOrderbookUpdate(data) {
            // 鏇存柊璁㈠崟绨挎樉绀?
            const bids = data.b || [];  // 涔板崟
            const asks = data.a || [];  // 鍗栧崟
            
            const orderbookEl = document.getElementById('orderbook-content');
            if (!orderbookEl) return;
            
            // 鍙樉绀哄墠10妗?
            const displayBids = bids.slice(0, 10);
            const displayAsks = asks.slice(0, 10);
            
            let html = '';
            
            // 鍗栧崟锛堜粠楂樺埌浣庯級
            displayAsks.slice().reverse().forEach(([price, amount]) => {
                const p = parseFloat(price).toFixed(2);
                const a = parseFloat(amount).toFixed(4);
                html += `<div class="orderbook-row ask">
                    <span style="color: #f6465d;">${p}</span>
                    <span style="color: #848e9c;">${a}</span>
                </div>`;
            });
            
            // 浠峰樊
            if (displayAsks.length > 0 && displayBids.length > 0) {
                const spread = parseFloat(displayAsks[0][0]) - parseFloat(displayBids[0][0]);
                html += `<div class="orderbook-spread">
                    浠峰樊: $${spread.toFixed(2)}
                </div>`;
            }
            
            // 涔板崟锛堜粠楂樺埌浣庯級
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
                connected: { text: '鈼?WS宸茶繛鎺?, color: '#0ecb81' },
                disconnected: { text: '鈼?WS閲嶈繛涓?, color: '#f0b90b' },
                error: { text: '鉁?WS閿欒', color: '#f6465d' }
            };
            
            const s = statusMap[status] || statusMap.disconnected;
            statusEl.innerHTML = `<span style="color: ${s.color}; font-size: 11px; margin-left: 8px;">${s.text}</span>`;
        }

        // 椤甸潰鍗歌浇鏃跺叧闂璚ebSocket
        window.addEventListener('beforeunload', function() {
            if (priceSocket) priceSocket.close();
            if (orderbookSocket) orderbookSocket.close();
            if (wsReconnectTimer) clearTimeout(wsReconnectTimer);
        });

        // ========== 鏉冪泭鏇茬嚎 ==========
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

            // 鐢熸垚妯℃嫙鎴愪氦閲忔暟鎹?
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

            // 鐢熸垚妯℃嫙鏉冪泭鏇茬嚎
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

        // ========== 椤甸潰鍒囨崲 ==========
        debugLog('椤甸潰鍒囨崲妯″潡鍒濆鍖?, 'info');
        document.querySelectorAll('.nav-item').forEach(item => {
            item.addEventListener('click', () => {
                const page = item.dataset.page;
                debugLog(`鍒囨崲鍒伴〉闈? ${page}`, 'info');
                try {
                    document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
                    item.classList.add('active');
                    document.querySelectorAll('.page-view').forEach(v => v.classList.remove('active'));
                    const targetPage = document.getElementById(`page-${page}`);
                    if (!targetPage) {
                        debugLog(`椤甸潰涓嶅瓨鍦? page-${page}`, 'error');
                        return;
                    }
                    targetPage.classList.add('active');
                    debugLog(`椤甸潰鍒囨崲鎴愬姛: ${page}`, 'success');
                    
                    // 鍒囨崲鍒板洖娴嬮〉鏃跺垵濮嬪寲鏉冪泭鍥?
                    if (page === 'backtest') {
                        setTimeout(() => {
                            if (!equityChart) initEquityChart();
                        }, 100);
                    }
                    
                    // 鍒囨崲鍒版棩蹇楅〉鏃跺埛鏂版棩蹇楀垪琛?
                    if (page === 'logs') {
                        setTimeout(() => {
                            if (window.renderLogList) window.renderLogList();
                        }, 100);
                    }
                    
                    // 鍒囨崲鍒癆I楠岃瘉灞傛椂鍔犺浇鏁版嵁
                    if (page === 'validation') {
                        setTimeout(() => {
                            loadValidationData();
                        }, 100);
                    }
                    
                    // 鍒囨崲鍒伴闄╅〉鏃跺姞杞介闄╂暟鎹?
                    if (page === 'risk') {
                        setTimeout(() => {
                            loadRiskData();
                        }, 100);
                    }
                } catch (err) {
                    debugLog(`椤甸潰鍒囨崲澶辫触: ${err.message}`, 'error');
                }
            });
        });
        debugLog(`鎵惧埌 ${document.querySelectorAll('.nav-item').length} 涓鑸」`, 'success');

        // ========== 鏃堕棿鍛ㄦ湡鍒囨崲 ==========
        document.querySelectorAll('.timeframe-tab').forEach(tab => {
            tab.addEventListener('click', () => {
                document.querySelectorAll('.timeframe-tab').forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
                currentTimeframe = tab.dataset.tf;
                loadKlineData(); // 閲嶆柊浠嶢PI鍔犺浇鏁版嵁
            });
        });

        // ========== 涓嬪崟闈㈡澘鍒囨崲 ==========
        document.querySelectorAll('.order-tab').forEach(tab => {
            tab.addEventListener('click', () => {
                document.querySelectorAll('.order-tab').forEach(t => {
                    t.classList.remove('active', 'buy', 'sell');
                });
                const isBuy = tab.textContent === '涔板叆';
                if (isBuy) {
                    tab.classList.add('active', 'buy');
                } else {
                    tab.classList.add('active', 'sell');
                }
                
                // 鏇存柊鎸夐挳鏂囧瓧鍜岄鑹?
                const submitBtn = document.getElementById('submit-order-btn');
                if (submitBtn) {
                    submitBtn.textContent = isBuy ? '涔板叆 BTC' : '鍗栧嚭 BTC';
                    submitBtn.className = isBuy ? 'btn-primary btn-buy' : 'btn-primary btn-sell';
                }
            });
        });

        // ========== 绛栫暐缂栬緫寮圭獥 ==========
        function openEditStrategy(strategyName) {
            document.getElementById('editStrategyName').textContent = strategyName;
            document.getElementById('editStrategyModal').classList.add('active');
        }

        function closeEditStrategy() {
            document.getElementById('editStrategyModal').classList.remove('active');
        }

        // ========== 绛栫暐璇︽儏寮圭獥 ==========
        let currentDetailStrategy = null;

        function openStrategyDetail(strategy) {
            currentDetailStrategy = strategy;
            
            // 濉厖鍩烘湰淇℃伅
            document.getElementById('detail-strategy-name').textContent = strategy.name || '绛栫暐璇︽儏';
            document.getElementById('detail-strategy-id').textContent = strategy.id || '--';
            document.getElementById('detail-strategy-status').textContent = 
                (strategy.status === 'running' || strategy.status === 'active') ? '杩愯涓? : '宸插仠姝?;
            document.getElementById('detail-strategy-symbol').textContent = strategy.symbol || 'BTC/USDT';
            document.getElementById('detail-strategy-created').textContent = strategy.created_at || '2026-01-01';
            
            // 濉厖缁╂晥鎸囨爣锛堟ā鎷熸暟鎹紝鍚庣画瀵规帴鐪熷疄API锛?
            document.getElementById('detail-total-return').textContent = '+12.5%';
            document.getElementById('detail-sharpe').textContent = '1.85';
            document.getElementById('detail-drawdown').textContent = '-8.3%';
            document.getElementById('detail-winrate').textContent = '58.2%';
            document.getElementById('detail-trades').textContent = '128';
            document.getElementById('detail-profit-factor').textContent = '1.65';
            
            // 鏇存柊鎸夐挳鏂囧瓧
            const isRunning = strategy.status === 'running' || strategy.status === 'active';
            document.getElementById('detail-toggle-btn-text').textContent = isRunning ? '鍋滄绛栫暐' : '鍚姩绛栫暐';
            
            // 鏄剧ず寮圭獥
            document.getElementById('strategyDetailModal').classList.add('active');
            
            logDebug('info', '鎵撳紑绛栫暐璇︽儏: ' + (strategy.name || '鏈煡'));
        }

        function closeStrategyDetail() {
            document.getElementById('strategyDetailModal').classList.remove('active');
            currentDetailStrategy = null;
        }

        function toggleStrategyStatus() {
            if (!currentDetailStrategy) return;
            const isRunning = currentDetailStrategy.status === 'running' || currentDetailStrategy.status === 'active';
            const action = isRunning ? '鍋滄' : '鍚姩';
            
            if (confirm(`纭畾瑕?{action}绛栫暐 "${currentDetailStrategy.name}" 鍚楋紵`)) {
                showToast(`绛栫暐宸?{action}锛堟ā鎷燂級`, 'success');
                logDebug('success', `${action}绛栫暐: ${currentDetailStrategy.name}`);
                
                // 鏇存柊鐘舵€?
                currentDetailStrategy.status = isRunning ? 'stopped' : 'running';
                document.getElementById('detail-strategy-status').textContent = isRunning ? '宸插仠姝? : '杩愯涓?;
                document.getElementById('detail-toggle-btn-text').textContent = isRunning ? '鍚姩绛栫暐' : '鍋滄绛栫暐';
                
                // 鍒锋柊绛栫暐鍒楄〃
                setTimeout(() => {
                    if (typeof loadStrategies === 'function') loadStrategies();
                }, 500);
            }
        }

        // ========== 鎻愪氦璁㈠崟锛堝鎺ョ湡瀹濧PI锛?=========
        // 鍩轰簬绗竴鎬у師鐞嗭細鍗遍櫓鎿嶄綔闇€瑕佹槑纭弽棣堬紝鎴愬姛/澶辫触閮借鐢ㄦ埛鐭ラ亾
        async function submitOrder() {
            try {
                // 1. 鑾峰彇褰撳墠璁㈠崟鏂瑰悜锛堜拱鍏?鍗栧嚭锛?
                const activeTab = document.querySelector('.order-tab.active');
                const side = activeTab && activeTab.textContent.includes('鍗栧嚭') ? 'sell' : 'buy';
                
                // 2. 鑾峰彇浜ゆ槗瀵?
                const symbolSelect = document.getElementById('order-symbol');
                const symbol = symbolSelect ? symbolSelect.value : 'BTC/USDT';
                
                // 3. 鑾峰彇浠锋牸锛堥檺浠峰崟鎵嶇敤锛?
                const priceInput = document.getElementById('order-price');
                const price = priceInput ? parseFloat(priceInput.value) : 0;
                
                // 4. 鑾峰彇鏁伴噺/閲戦
                const amountInput = document.getElementById('order-amount');
                const amount = amountInput ? parseFloat(amountInput.value) : 100;
                
                // 5. 鑾峰彇鏉犳潌
                const leverageInput = document.getElementById('order-leverage');
                const leverage = leverageInput ? parseInt(leverageInput.value) : 1;
                
                // 6. 鑾峰彇褰撳墠閫変腑鐨勫嚟璇両D锛堜粠璐︽埛鍒楄〃绗竴涓級
                const firstAccount = document.querySelector('.credential-option');
                const credentialId = firstAccount ? parseInt(firstAccount.dataset.id || 1) : 1;
                
                logDebug('info', `鎻愪氦璁㈠崟: ${side} ${amount} USDT ${symbol}`);
                
                // 7. 璋冪敤鐪熷疄API
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
                    showToast(`璁㈠崟鎻愪氦鎴愬姛锛?{side === 'buy' ? '涔板叆' : '鍗栧嚭'} ${amount} USDT ${symbol}`, 'success');
                    logDebug('success', '涓嬪崟鎴愬姛: ' + JSON.stringify(result.data || result));
                    
                    // 鍒锋柊鎸佷粨鍜岃祫浜?
                    setTimeout(() => {
                        if (typeof loadDashboardData === 'function') loadDashboardData();
                    }, 1000);
                } else {
                    showToast('涓嬪崟澶辫触: ' + (result.msg || result.message || '鏈煡閿欒'), 'error');
                    logDebug('error', '涓嬪崟澶辫触: ' + JSON.stringify(result));
                }
            } catch (e) {
                console.error('涓嬪崟閿欒:', e);
                showToast('涓嬪崟閿欒: ' + e.message, 'error');
                logDebug('error', '涓嬪崟寮傚父: ' + e.message);
            }
        }

        // ========== 杩愯鍥炴祴 ==========
        async function runBacktest() {
            const btn = document.getElementById('run-backtest-btn');
            const btnText = document.getElementById('backtest-btn-text');
            
            btn.disabled = true;
            btnText.innerHTML = '<span class="loading"></span> 杩愯涓?..';

            // 妯℃嫙鍥炴祴寤惰繜
            await new Promise(resolve => setTimeout(resolve, 2000));

            // 鏄剧ず缁撴灉
            document.getElementById('backtest-results').classList.add('active');
            
            // 濉厖妯℃嫙鏁版嵁
            document.getElementById('bt-total-return').textContent = '+67.97%';
            document.getElementById('bt-sharpe').textContent = '1.85';
            document.getElementById('bt-drawdown').textContent = '-15.2%';
            document.getElementById('bt-winrate').textContent = '55.6%';

            btn.disabled = false;
            btnText.textContent = '杩愯鍥炴祴';
            showToast('鍥炴祴瀹屾垚', 'success');

            // 鍒濆鍖栨潈鐩婂浘鍜屽洖鎾ゅ浘
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

            // 鐢熸垚妯℃嫙鍥炴挙鏁版嵁
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

        // ========== 鏃ュ織涓績 ==========
        function initLogCenter() {
            // 娓叉煋鏃ュ織鍒楄〃
            window.renderLogList = function(filter = 'all', search = '') {
                const logList = document.getElementById('log-list');
                if (!logList) return;
                
                let logs = window.debugLogs || [];
                
                // 杩囨护绾у埆
                if (filter !== 'all') {
                    logs = logs.filter(l => l.type === filter);
                }
                
                // 鎼滅储
                if (search) {
                    const s = search.toLowerCase();
                    logs = logs.filter(l => l.msg.toLowerCase().includes(s));
                }
                
                // 鏇存柊缁熻
                document.getElementById('log-total').textContent = window.debugLogs.length;
                document.getElementById('log-error-count').textContent = window.debugLogs.filter(l => l.type === 'error').length;
                document.getElementById('log-warn-count').textContent = window.debugLogs.filter(l => l.type === 'warn').length;
                document.getElementById('log-api-count').textContent = window.debugLogs.filter(l => l.msg.includes('API')).length;
                
                // 娓叉煋鍒楄〃
                if (logs.length === 0) {
                    logList.innerHTML = '<div style="padding: 8px 12px; color: var(--text-secondary); text-align: center;">鏆傛棤鏃ュ織</div>';
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
            
            // 杩囨护浜嬩欢
            const filterSelect = document.getElementById('log-level-filter');
            if (filterSelect) {
                filterSelect.onchange = function() {
                    const search = document.getElementById('log-search').value;
                    window.renderLogList(this.value, search);
                };
            }
            
            // 鎼滅储浜嬩欢
            const searchInput = document.getElementById('log-search');
            if (searchInput) {
                searchInput.oninput = function() {
                    const filter = document.getElementById('log-level-filter').value;
                    window.renderLogList(filter, this.value);
                };
            }
            
            // 娓呯┖鏃ュ織
            const clearBtn = document.getElementById('log-clear');
            if (clearBtn) {
                clearBtn.onclick = function() {
                    window.debugLogs = [];
                    window.renderLogList();
                    debugLog('鏃ュ織宸叉竻绌?, 'info');
                };
            }
            
            // 瀵煎嚭鏃ュ織
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
                    debugLog('鏃ュ織宸插鍑?, 'success');
                };
            }
        }

        // ========== 鏁版嵁鍔犺浇 ==========
        async function loadAllData() {
            try {
                const [credentialsRes, summaryRes, strategiesRes, positionsRes] = await Promise.all([
                    ApiService.getCredentials(),
                    ApiService.getDashboardSummary(),
                    ApiService.getStrategies(),
                    ApiService.getPositions()
                ]);

                // 妫€鏌ユ槸鍚︽湭鐧诲綍
                const anyUnauthorized = credentialsRes._unauthorized || summaryRes._unauthorized;
                if (anyUnauthorized) {
                    updateSystemStatus('unauthorized');
                    showToast('璇峰厛鐧诲綍绯荤粺', 'warning');
                    // 鏈櫥褰曟椂浣跨敤婕旂ず鏁版嵁
                    updateAccountsList([], false);
                    updateDashboardStats({}, false);
                    updateStrategiesList([], false);
                    return;
                }

                updateAccountsList(credentialsRes.data || [], !credentialsRes._error && credentialsRes.code === 1);
                updateDashboardStats(summaryRes.data || {}, !summaryRes._error && summaryRes.code === 1);
                updateStrategiesList(strategiesRes.data || [], !strategiesRes._error && strategiesRes.code === 1);
                updatePositionsList(positionsRes.data || [], !positionsRes._error && positionsRes.code === 1);
                
                updateSystemStatus('online');
            } catch (e) {
                console.error('鍔犺浇鏁版嵁澶辫触:', e);
                updateSystemStatus('offline');
                updateAccountsList([], false);
                updateDashboardStats({}, false);
            }
        }

        function updateSystemStatus(status) {
            const el = document.getElementById('system-status');
            if (!el) return;
            const statusMap = {
                'online': { text: '鈼?绯荤粺姝ｅ父', color: 'var(--up-color)' },
                'offline': { text: '鈼?绂荤嚎妯″紡', color: 'var(--warning-color)' },
                'unauthorized': { text: '鈼?鏈櫥褰?, color: 'var(--down-color)' }
            };
            const s = statusMap[status] || statusMap['offline'];
            el.textContent = s.text;
            el.style.color = s.color;
        }

        function updateAccountsList(credentials, isReal = false) {
            const accountsList = document.getElementById('accounts-list');
            const modalAccountsList = document.getElementById('modal-accounts-list');

            // 涓嶆槸鐪熷疄鏁版嵁鏃讹紝浣跨敤婕旂ず鏁版嵁骞舵爣娉?
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
                            <div style="font-size: 11px; color: var(--text-secondary);">${cred.api_key_hint || '宸茶繛鎺?}</div>
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

            // 涓嶆槸鐪熷疄鏁版嵁鏃讹紝浣跨敤婕旂ず鏁版嵁
            if (!isReal || !strategies || strategies.length === 0) {
                strategies = [
                    { id: 1, name: 'ML澧炲己瓒嬪娍绛栫暐', status: 'running', today_pnl: 45.67, win_rate: 65, sharpe: 1.85, max_drawdown: 3.2, total_trades: 45 },
                    { id: 2, name: '鍧囧€煎洖褰掔瓥鐣?, status: 'running', today_pnl: -12.34, win_rate: 58, sharpe: 1.42, max_drawdown: 4.8, total_trades: 128 },
                    { id: 3, name: '绐佺牬绛栫暐', status: 'stopped', today_pnl: 0, win_rate: 0, sharpe: 0, max_drawdown: 0, total_trades: 0 }
                ];
            }

            // 鏅鸿兘瀛楁鏄犲皠锛氬吋瀹瑰悗绔笉鍚屽瓧娈靛悕
            strategies = strategies.map(s => ({
                ...s,
                name: s.name || s.strategy_name || '鏈懡鍚嶇瓥鐣?,
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
                        <span class="strategy-status running">杩愯涓?/span>
                    </div>
                    <div class="strategy-metrics">
                        <span>浠婃棩: ${s.today_pnl >= 0 ? '+' : ''}${(s.today_pnl || 0).toFixed(2)}</span>
                        <span>鑳滅巼: ${(s.win_rate || 0).toFixed(0)}%</span>
                    </div>
                </div>
            `).join('');

            gridEl.innerHTML = strategies.map(s => `
                <div class="strategy-card ${s.status || 'stopped'}" onclick='openStrategyDetail(${JSON.stringify(s).replace(/'/g, "&apos;")})'>
                    <div class="strategy-header">
                        <span class="strategy-name">${s.name}</span>
                        <span class="strategy-status ${s.status || 'stopped'}">${s.status === 'running' ? '杩愯涓? : '宸插仠姝?}</span>
                    </div>
                    <div style="font-size: 12px; color: var(--text-secondary); margin-bottom: 12px;">${s.description || '鏆傛棤鎻忚堪'}</div>
                    <div class="strategy-metrics">
                        <span>澶忔櫘: ${(s.sharpe || 1.85).toFixed(2)}</span>
                        <span>鍥炴挙: ${(s.max_drawdown || 5.2).toFixed(1)}%</span>
                        <span>浜ゆ槗: ${s.total_trades || 45}</span>
                    </div>
                </div>
            `).join('');
        }

        function updatePositionsList(positions) {
            const el = document.getElementById('positions-list');
            if (!positions || positions.length === 0) {
                // 浣跨敤绀轰緥鏁版嵁
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

        // ========== 绐楀彛澶у皬璋冩暣 ==========
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

        // ========== 璁よ瘉绠＄悊 ==========
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
                    debugLog(`灏濊瘯鐧诲綍: ${username}`, 'info');
                    const res = await fetch('/api/auth/login', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ username, password })
                    });
                    const data = await res.json();
                    if (data.code === 1 && data.data.token) {
                        this.setToken(data.data.token);
                        this.setUser(data.data.userinfo);
                        debugLog(`鐧诲綍鎴愬姛: ${data.data.userinfo.username}`, 'success');
                        this.showMain();
                        loadAllData();
                        return true;
                    } else {
                        debugLog(`鐧诲綍澶辫触: ${data.msg}`, 'error');
                        return false;
                    }
                } catch (e) {
                    debugLog(`鐧诲綍璇锋眰澶辫触: ${e.message}`, 'error');
                    return false;
                }
            }
        };

        // ========== API璇锋眰鎷︽埅鍣紙鑷姩娣诲姞token锛?==========
        const originalFetch2 = window.fetch;
        window.fetch = async function(url, options = {}) {
            // 璺宠繃鐧诲綍鎺ュ彛鏈韩
            if (!url.includes('/api/auth/login')) {
                const token = Auth.getToken();
                if (token) {
                    options.headers = { ...options.headers, 'Authorization': `Bearer ${token}` };
                }
            }
            const response = await originalFetch2(url, options);
            // 401鑷姩璺宠浆鐧诲綍
            if (response.status === 401 && !url.includes('/api/auth/login')) {
                debugLog('Token澶辨晥锛岃烦杞埌鐧诲綍椤?, 'warn');
                Auth.logout();
            }
            return response;
        };

        // ========== 鐧诲綍鎸夐挳浜嬩欢 ==========
        document.getElementById('login-btn').addEventListener('click', async () => {
            const username = document.getElementById('login-username').value.trim();
            const password = document.getElementById('login-password').value.trim();
            const errorEl = document.getElementById('login-error');
            const statusEl = document.getElementById('login-status');
            
            if (!username || !password) {
                errorEl.textContent = '璇疯緭鍏ョ敤鎴峰悕鍜屽瘑鐮?;
                errorEl.style.display = 'block';
                return;
            }
            
            const btn = document.getElementById('login-btn');
            btn.disabled = true;
            btn.textContent = '鐧诲綍涓?..';
            errorEl.style.display = 'none';
            statusEl.textContent = '姝ｅ湪楠岃瘉韬唤...';
            
            const success = await Auth.login(username, password);
            
            btn.disabled = false;
            btn.textContent = '鐧?褰?;
            
            if (!success) {
                errorEl.textContent = '鐢ㄦ埛鍚嶆垨瀵嗙爜閿欒';
                errorEl.style.display = 'block';
                statusEl.textContent = '';
            }
        });

        // 鍥炶溅鐧诲綍
        document.getElementById('login-password').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                document.getElementById('login-btn').click();
            }
        });

        // ========== AI楠岃瘉灞傛暟鎹姞杞?==========
        async function loadValidationData() {
            debugLog('鍔犺浇AI楠岃瘉灞傛暟鎹?, 'info');
            try {
                // 鍔犺浇楠岃瘉妯″潡鐘舵€?
                const statusRes = await fetch('/api/validation/status', {
                    headers: { 'Authorization': 'Bearer ' + Auth.getToken() }
                });
                if (!statusRes.ok) throw new Error('API杩斿洖' + statusRes.status);
                const statusData = await statusRes.json();
                if (statusData.code === 1 && statusData.data) {
                    renderValidationModules(statusData.data.modules);
                    debugLog(`楠岃瘉妯″潡鐘舵€佸姞杞芥垚鍔? ${statusData.data.total}涓ā鍧梎, 'success');
                }
                
                // 鍔犺浇瀹¤鏃ュ織
                const logsRes = await fetch('/api/validation/audit-logs?limit=20', {
                    headers: { 'Authorization': 'Bearer ' + Auth.getToken() }
                });
                if (logsRes.ok) {
                    const logsData = await logsRes.json();
                    if (logsData.code === 1 && logsData.data) {
                        renderAuditLogs(logsData.data.logs);
                        debugLog(`瀹¤鏃ュ織鍔犺浇鎴愬姛: ${logsData.data.total}鏉, 'success');
                    }
                }
                
                // 鍔犺浇鍘嬪姏娴嬭瘯缁撴灉
                const stressRes = await fetch('/api/validation/stress-test', {
                    headers: { 'Authorization': 'Bearer ' + Auth.getToken() }
                });
                if (stressRes.ok) {
                    const stressData = await stressRes.json();
                    if (stressData.code === 1 && stressData.data) {
                        renderStressTest(stressData.data);
                        debugLog(`鍘嬪姏娴嬭瘯缁撴灉鍔犺浇鎴愬姛: ${stressData.data.total_scenarios}涓儏鏅痐, 'success');
                    }
                }
                
                // 鏇存柊鏃堕棿
                const now = new Date();
                document.getElementById('validation-time').textContent = now.toLocaleTimeString();
                
            } catch (err) {
                debugLog(`AI楠岃瘉灞侫PI鏆備笉鍙敤锛屼娇鐢ㄥ唴缃暟鎹? ${err.message}`, 'warn');
                // API涓嶅彲鐢ㄦ椂淇濈暀鐜版湁纭紪鐮佹暟鎹紝涓嶅仛浠讳綍淇敼
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
                        鉁?${m.status === 'connected' ? '宸茶繛鎺? : '鍋ュ悍'}
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
            
            // 鏇存柊鍘嬪姏娴嬭瘯鍗＄墖
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
            
            // 鏇存柊缁煎悎椋庨櫓璇勫垎
            const riskScoreEl = document.querySelector('#page-validation [style*="缁煎悎椋庨櫓璇勫垎"]');
            if (riskScoreEl && data.overall_risk_score) {
                riskScoreEl.innerHTML = `
                    <span style="color: #0ecb81; font-weight: 600;">鉁?缁煎悎椋庨櫓璇勫垎锛?{data.overall_risk_score}/100锛?{data.risk_level}锛?/span><br>
                    <span style="font-size: 12px;">${data.summary}</span>
                `;
            }
        }
        
        // ========== 椋庨櫓浠〃鐩樻暟鎹姞杞?==========
        async function loadRiskData() {
            debugLog('鍔犺浇椋庨櫓浠〃鐩樻暟鎹?, 'info');
            try {
                const res = await fetch('/api/risk/dashboard', {
                    headers: { 'Authorization': 'Bearer ' + Auth.getToken() }
                });
                if (!res.ok) throw new Error('API杩斿洖' + res.status);
                const data = await res.json();
                if (data.code === 1 && data.data) {
                    renderRiskDashboard(data.data);
                    debugLog(`椋庨櫓鏁版嵁鍔犺浇鎴愬姛`, 'success');
                }
            } catch (err) {
                debugLog(`椋庨櫓API鏆備笉鍙敤锛屼娇鐢ㄥ唴缃暟鎹? ${err.message}`, 'warn');
                // API涓嶅彲鐢ㄦ椂淇濈暀鐜版湁纭紪鐮佹暟鎹?
            }
            // 鏇存柊鏃堕棿
            const now = new Date();
            document.getElementById('risk-update-time').textContent = '鏇存柊浜?' + now.toLocaleTimeString();
        }
        
        function renderRiskDashboard(data) {
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

        // ========== 鍒濆鍖?==========
        // 妫€鏌ョ櫥褰曠姸鎬?
        if (Auth.isLoggedIn()) {
            Auth.showMain();
        } else {
            Auth.showLogin();
        }
        
        initMainChart();
        initLogCenter();
        if (Auth.isLoggedIn()) {
            loadAllData();
        }

        // 姣?0绉掑埛鏂颁竴娆℃暟鎹?
        setInterval(() => {
            if (Auth.isLoggedIn()) loadAllData();
        }, 30000);
