import os
import json
import time
import threading
from flask import Flask, jsonify, render_template_string, request
import websocket
from datetime import datetime, timedelta

app = Flask(__name__)

# --- إعدادات النظام ---
bot_config = {
    "isRunning": False,
    "direction": "WAITING",
    "reason": "System Initializing...",
    "pair_name": "EUR/USD",
    "pair_id": "frxEURUSD",
    "timestamp": 0,
    "entryTime": "",
    "isSignal": False,
    "logs": []
}

ASSETS = {
    "frxEURUSD": "EUR/USD", "frxEURJPY": "EUR/JPY", 
    "frxEURGBP": "EUR/GBP", "frxGBPUSD": "GBP/USD", "frxUSDJPY": "USD/JPY"
}

def add_log(msg):
    bot_config["logs"].append(f"[{time.strftime('%H:%M:%S')}] {msg}")
    if len(bot_config["logs"]) > 5: bot_config["logs"].pop(0)

def calculate_rsi(prices, period=14):
    if len(prices) < period + 1: return 50
    deltas = [prices[i+1] - prices[i] for i in range(len(prices)-1)]
    up = sum([max(d, 0) for d in deltas[-period:]]) / period
    down = sum([max(-d, 0) for d in deltas[-period:]]) / period
    if down == 0: return 100
    rs = up / down
    return 100 - (100 / (1 + rs))

def perform_analysis(ticks, times, asset_id):
    global bot_config
    
    # حساب RSI من آخر 1000 تيك (تقريباً 16 شمعة دقيقة)
    candle_closes = [ticks[i] for i in range(59, len(ticks), 60)]
    rsi_val = calculate_rsi(candle_closes, 14)
    current_price = ticks[-1]
    now = datetime.now()
    
    # تحديد أسعار البداية
    start_of_5m = now.replace(minute=(now.minute // 5) * 5, second=0, microsecond=0)
    start_of_1m = now.replace(second=0, microsecond=0)
    
    price_at_5m = next((ticks[i] for i, t in enumerate(times) if datetime.fromtimestamp(int(t)) >= start_of_5m), ticks[0])
    price_at_1m = next((ticks[i] for i, t in enumerate(times) if datetime.fromtimestamp(int(t)) >= start_of_1m), ticks[-60] if len(ticks) > 60 else ticks[0])

    reason = ""
    is_call = (rsi_val > 50) and (current_price > price_at_5m) and (current_price > price_at_1m)
    is_put = (rsi_val < 50) and (current_price < price_at_5m) and (current_price < price_at_1m)

    # تحديد سبب الرفض بدقة
    if not is_call and not is_put:
        if rsi_val > 45 and rsi_val < 55: reason = "RSI Neutral (Sideways)"
        elif rsi_val > 50 and current_price < price_at_5m: reason = "M5 Trend is Down (Against RSI)"
        elif rsi_val < 50 and current_price > price_at_5m: reason = "M5 Trend is Up (Against RSI)"
        else: reason = "M1/M5 No Sync"

    next_entry = (now + timedelta(seconds=10)).strftime("%H:%M")

    # تحديث الحالة فوراً
    bot_config.update({
        "isSignal": is_call or is_put,
        "direction": "CALL 🟢" if is_call else ("PUT 🔴" if is_put else "NO SIGNAL"),
        "reason": "Conditions Met" if (is_call or is_put) else reason,
        "timestamp": time.time(),
        "entryTime": next_entry if (is_call or is_put) else "",
        "pair_name": ASSETS[asset_id]
    })
    add_log(f"Analysis Done: {bot_config['direction']} | {reason}")

def smart_ws_worker():
    while True:
        now = datetime.now()
        # يحلل عند الثانية 50 من كل دقيقة
        if bot_config["isRunning"] and now.second == 50:
            try:
                ws = websocket.create_connection("wss://blue.derivws.com/websockets/v3?app_id=16929", timeout=10)
                ws.send(json.dumps({"ticks_history": bot_config["pair_id"], "count": 1000, "end": "latest", "style": "ticks"}))
                res = json.loads(ws.recv())
                if "history" in res:
                    perform_analysis(res["history"]["prices"], res["history"]["times"], bot_config["pair_id"])
                ws.close()
                time.sleep(2) # تجنب التكرار في نفس الثانية
            except Exception as e:
                add_log(f"Socket Error: {str(e)}")
        time.sleep(0.1)

UI = """
<!DOCTYPE html>
<html>
<head>
    <title>KHOURY AI V2</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        :root { --neon: #00f3ff; --green: #39ff14; --red: #ff4757; }
        body { background: #06070a; color: white; font-family: 'Courier New', monospace; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; }
        .box { background: #0a0c10; padding: 25px; border-radius: 15px; border: 1px solid var(--neon); width: 340px; text-align: center; box-shadow: 0 0 20px rgba(0,243,255,0.1); }
        select, .btn { width: 100%; padding: 12px; margin: 10px 0; border-radius: 5px; border: 1px solid var(--neon); background: transparent; color: var(--neon); cursor: pointer; font-weight: bold; }
        .btn:hover { background: var(--neon); color: #000; }
        #mainDisp { border: 1px solid #222; margin: 15px 0; padding: 20px; min-height: 120px; border-radius: 10px; background: rgba(255,255,255,0.02); }
        .log-box { height: 60px; font-size: 10px; color: #555; overflow-y: hidden; text-align: left; border-top: 1px solid #222; padding-top: 10px; }
        .status-on { color: var(--green); } .status-off { color: var(--red); }
    </style>
</head>
<body>
    <div class="box">
        <h3 style="margin:0; color:var(--neon)">KHOURY AI M1</h3>
        <p id="statusTxt" class="status-off" style="font-size:12px">● SYSTEM OFFLINE</p>
        
        <select id="asset">
            {% for id, name in assets.items() %}
            <option value="{{id}}">{{name}}</option>
            {% endfor %}
        </select>

        <div id="mainDisp">
            <div style="font-size:12px; color:#666">WAITING FOR ANALYSIS...</div>
        </div>

        <button class="btn" onclick="ctl('start')">START ENGINE</button>
        <button class="btn" style="border-color:var(--red); color:var(--red)" onclick="ctl('stop')">STOP</button>
        
        <div class="log-box" id="lBox"></div>
    </div>

    <script>
        async function ctl(a) { 
            await fetch(`/api/cmd?action=${a}&pair=${document.getElementById('asset').value}`);
            document.getElementById('statusTxt').innerText = a === 'start' ? "● SYSTEM ACTIVE" : "● SYSTEM OFFLINE";
            document.getElementById('statusTxt').className = a === 'start' ? "status-on" : "status-off";
        }

        async function update() {
            const r = await fetch('/api/status');
            const d = await r.json();
            const disp = document.getElementById('mainDisp');
            
            if (d.active_msg) {
                let color = d.isSignal ? "var(--green)" : "var(--red)";
                disp.innerHTML = `<div style="text-align:left">
                    <b style="color:${color}">${d.direction}</b><br>
                    <small>Pair: ${d.pair}</small><br>
                    <small>Reason: ${d.reason}</small><br>
                    ${d.isSignal ? '<b>ENTRY: ' + d.entry + '</b>' : ''}
                </div>`;
            } else {
                let sec = new Date().getSeconds();
                let wait = 50 - sec;
                if (wait < 0) wait = 60 + wait;
                disp.innerHTML = `<div style="color:#444">NEXT ANALYSIS IN:<br><span style="font-size:25px">${wait}s</span></div>`;
            }
            document.getElementById('lBox').innerHTML = d.logs.join('<br>');
        }
        setInterval(update, 1000);
    </script>
</body>
</html>
"""

@app.route('/')
def home(): return render_template_string(UI, assets=ASSETS)

@app.route('/api/cmd')
def cmd():
    bot_config["isRunning"] = (request.args.get('action') == 'start')
    bot_config["pair_id"] = request.args.get('pair')
    if not bot_config["isRunning"]: bot_config["timestamp"] = 0
    return jsonify({"ok": True})

@app.route('/api/status')
def get_status():
    # تظهر الرسالة لمدة 30 ثانية بعد التحليل
    active_msg = (time.time() - bot_config["timestamp"]) < 30 and bot_config["timestamp"] > 0
    return jsonify({
        "active_msg": active_msg,
        "isSignal": bot_config["isSignal"],
        "direction": bot_config["direction"],
        "reason": bot_config["reason"],
        "pair": bot_config["pair_name"],
        "entry": bot_config["entryTime"],
        "logs": bot_config["logs"]
    })

if __name__ == "__main__":
    threading.Thread(target=smart_ws_worker, daemon=True).start()
    app.run(host='0.0.0.0', port=5000, debug=False)
