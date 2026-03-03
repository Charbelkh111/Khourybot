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
    "reason": "Scanning...",
    "pair_name": "EUR/JPY",
    "pair_id": "frxEURJPY",
    "timestamp": 0,
    "entryTime": "",
    "isSignal": False,
    "logs": []
}

ASSETS = {"frxEURUSD": "EUR/USD", "frxEURJPY": "EUR/JPY", "frxEURGBP": "EUR/GBP"}

def add_log(msg):
    bot_config["logs"].append(f"[{time.strftime('%H:%M:%S')}] {msg}")
    if len(bot_config["logs"]) > 5: bot_config["logs"].pop(0)

# --- محرك التحليل (RSI + M1 + M5) ---
def perform_analysis(ticks, asset_id):
    global bot_config
    try:
        # 1. حساب RSI من 1000 تيك (تقسيم لشموع دقيقة)
        candle_closes = [ticks[i] for i in range(59, len(ticks), 60)]
        period = 14
        rsi_val = 50
        if len(candle_closes) > period:
            deltas = [candle_closes[i+1] - candle_closes[i] for i in range(len(candle_closes)-1)]
            up = sum([d for d in deltas[-period:] if d > 0]) / period
            down = sum([-d for d in deltas[-period:] if d < 0]) / period
            rsi_val = 100 - (100 / (1 + (up/down if down != 0 else 100)))

        current_price = ticks[-1]
        
        # 2. اتجاه آخر 60 تيك (M1)
        price_m1 = ticks[-60] if len(ticks) >= 60 else ticks[0]
        m1_trend = "UP" if current_price > price_m1 else "DOWN"
        
        # 3. اتجاه آخر 300 تيك (M5)
        price_m5 = ticks[-300] if len(ticks) >= 300 else ticks[0]
        m5_trend = "UP" if current_price > price_m5 else "DOWN"

        # --- التحقق من الشروط ---
        is_call = (rsi_val > 50) and (m1_trend == "UP") and (m5_trend == "UP")
        is_put = (rsi_val < 50) and (m1_trend == "DOWN") and (m5_trend == "DOWN")

        # عرض التحليل دائماً حتى لو لا توجد إشارة
        bot_config.update({
            "isSignal": is_call or is_put,
            "direction": "CALL 🟢" if is_call else ("PUT 🔴" if is_put else "NO SIGNAL"),
            "reason": f"RSI: {round(rsi_val,1)} | M1: {m1_trend} | M5: {m5_trend}",
            "timestamp": time.time(),
            "entryTime": (datetime.now() + timedelta(seconds=10)).strftime("%H:%M"),
            "pair_name": ASSETS[asset_id]
        })
        add_log(f"Scan Done: RSI {round(rsi_val,1)}")

    except Exception as e:
        add_log(f"Error: {str(e)}")

def smart_ws_worker():
    while True:
        now = datetime.now()
        if bot_config["isRunning"] and now.second == 50:
            try:
                ws = websocket.create_connection("wss://blue.derivws.com/websockets/v3?app_id=16929", timeout=12)
                ws.send(json.dumps({"ticks_history": bot_config["pair_id"], "count": 1000, "end": "latest", "style": "ticks"}))
                res = json.loads(ws.recv())
                if "history" in res:
                    perform_analysis(res["history"]["prices"], bot_config["pair_id"])
                ws.close()
                time.sleep(5)
            except Exception as e:
                add_log("Network Error")
        time.sleep(0.5)

UI = """
<!DOCTYPE html>
<html>
<head>
    <title>KHOURY AI V2</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        :root { --neon: #00f3ff; --red: #ff4757; }
        body { background: #06070a; color: white; font-family: sans-serif; text-align: center; padding: 20px; }
        .box { max-width: 400px; margin: auto; }
        .clock { font-size: 50px; color: var(--neon); margin: 20px 0; text-shadow: 0 0 15px var(--neon); }
        .display-area { border: 2px solid var(--neon); padding: 30px; border-radius: 20px; margin: 20px 0; background: rgba(0,243,255,0.02); min-height: 180px; }
        .btn { padding: 15px; border-radius: 10px; border: 1px solid var(--neon); background: none; color: var(--neon); font-weight: bold; cursor: pointer; width: 48%; }
        .btn-start { background: var(--neon); color: black; }
        select { background: #000; border: 1px solid #333; color: var(--neon); padding: 12px; width: 100%; border-radius: 10px; margin-bottom: 20px; }
    </style>
</head>
<body>
    <div class="box">
        <h2 style="color:var(--neon)">KHOURY AI V2</h2>
        <select id="pair">
            <option value="frxEURJPY">EUR/JPY</option>
            <option value="frxEURUSD">EUR/USD</option>
        </select>
        <div class="clock" id="clk">00:00:00</div>
        <div style="display:flex; justify-content: space-between;">
            <button class="btn btn-start" onclick="ctl('start')">START</button>
            <button class="btn" style="border-color:var(--red); color:var(--red);" onclick="ctl('stop')">STOP</button>
        </div>
        <div class="display-area" id="mainDisp">
            <p style="color:#444">WAITING FOR SEC 50...</p>
        </div>
    </div>
    <script>
        async function ctl(a) { await fetch(`/api/cmd?action=${a}&pair=${document.getElementById('pair').value}`); }
        async function update() {
            document.getElementById('clk').innerText = new Date().toTimeString().split(' ')[0];
            const r = await fetch('/api/status');
            const d = await r.json();
            const disp = document.getElementById('mainDisp');
            
            if (d.show) {
                disp.innerHTML = `<div style="text-align:left">
                    <h3 style="color:${d.isSignal ? 'var(--neon)' : 'white'}">${d.dir}</h3>
                    <p style="font-size:14px;">${d.reason}</p>
                    <hr style="border:0; border-top:1px solid #333">
                    <b>ENTRY: ${d.entry}</b>
                </div>`;
            } else {
                let s = new Date().getSeconds();
                let wait = 50 - s; if(wait < 0) wait += 60;
                disp.innerHTML = `<p style="color:#555">ANALYZING IN ${wait}s...</p>`;
            }
        }
        setInterval(update, 1000);
    </script>
</body>
</html>
"""

@app.route('/')
def home(): return render_template_string(UI)

@app.route('/api/cmd')
def cmd():
    bot_config["isRunning"] = (request.args.get('action') == 'start')
    bot_config["pair_id"] = request.args.get('pair')
    if not bot_config["isRunning"]: bot_config["timestamp"] = 0
    return jsonify({"ok": True})

@app.route('/api/status')
def get_status():
    # الرسالة تظهر لمدة 45 ثانية لتغطية وقت الانتظار
    show = (time.time() - bot_config["timestamp"]) < 45 and bot_config["timestamp"] > 0
    return jsonify({"show": show, "isSignal": bot_config["isSignal"], "dir": bot_config["direction"], "reason": bot_config["reason"], "entry": bot_config["entryTime"]})

if __name__ == "__main__":
    threading.Thread(target=smart_ws_worker, daemon=True).start()
    app.run(host='0.0.0.0', port=5000)
