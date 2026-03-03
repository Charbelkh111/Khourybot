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
    "displayMsg": "WAITING",
    "direction": "",
    "strength": 0,
    "pair_name": "EUR/USD",
    "pair_id": "frxEURUSD",
    "timestamp": 0,
    "entryTime": "",
    "isSignal": False,
    "logs": []
}

ASSETS = {
    "frxEURUSD": "EUR/USD", 
    "frxEURJPY": "EUR/JPY", 
    "frxEURGBP": "EUR/GBP",
    "frxGBPUSD": "GBP/USD",
    "frxUSDJPY": "USD/JPY"
}

def add_log(msg):
    bot_config["logs"].append(f"[{time.strftime('%H:%M:%S')}] {msg}")
    if len(bot_config["logs"]) > 5: bot_config["logs"].pop(0)

# --- محرك الحسابات (RSI) ---
def calculate_rsi(prices, period=14):
    if len(prices) < period + 1: return 50
    deltas = [prices[i+1] - prices[i] for i in range(len(prices)-1)]
    up = sum([max(d, 0) for d in deltas[-period:]]) / period
    down = sum([max(-d, 0) for d in deltas[-period:]]) / period
    if down == 0: return 100
    rs = up / down
    return 100 - (100 / (1 + rs))

# --- تحليل السوق ---
def perform_analysis(ticks, times, asset_id):
    global bot_config
    
    # تحويل التيكات لشموع (كل 60 تيك = 1 دقيقة)
    candle_closes = [ticks[i] for i in range(59, len(ticks), 60)]
    rsi_val = calculate_rsi(candle_closes, 14)
    
    current_price = ticks[-1]
    now = datetime.now()
    
    # تحديد أسعار البداية (5 دقائق و 1 دقيقة)
    start_of_5m = now.replace(minute=(now.minute // 5) * 5, second=0, microsecond=0)
    start_of_1m = now.replace(second=0, microsecond=0)
    
    price_at_5m = next((ticks[i] for i, t in enumerate(times) if datetime.fromtimestamp(int(t)) >= start_of_5m), ticks[0])
    price_at_1m = next((ticks[i] for i, t in enumerate(times) if datetime.fromtimestamp(int(t)) >= start_of_1m), ticks[-60] if len(ticks) > 60 else ticks[0])

    # الشروط المطلوبة: RSI + اتجاه 5د + اتجاه 1د
    is_call = (rsi_val > 50) and (current_price > price_at_5m) and (current_price > price_at_1m)
    is_put = (rsi_val < 50) and (current_price < price_at_5m) and (current_price < price_at_1m)

    next_entry = (now + timedelta(seconds=10)).strftime("%H:%M")

    if is_call:
        bot_config.update({
            "displayMsg": "SIGNAL FOUND", "isSignal": True, "direction": "CALL 🟢",
            "strength": round(rsi_val, 1), "pair_name": ASSETS[asset_id],
            "timestamp": time.time(), "entryTime": next_entry
        })
        add_log(f"SIGNAL: CALL (RSI:{rsi_val:.1f})")
    elif is_put:
        bot_config.update({
            "displayMsg": "SIGNAL FOUND", "isSignal": True, "direction": "PUT 🔴",
            "strength": round(100 - rsi_val, 1), "pair_name": ASSETS[asset_id],
            "timestamp": time.time(), "entryTime": next_entry
        })
        add_log(f"SIGNAL: PUT (RSI:{rsi_val:.1f})")
    else:
        bot_config.update({"displayMsg": "NO SIGNAL", "isSignal": False, "timestamp": time.time()})
        add_log(f"SCAN: RSI {rsi_val:.1f} - No Match")

# --- نظام جلب البيانات (معدل للعمل كل دقيقة) ---
def smart_ws_worker():
    while True:
        now = datetime.now()
        # الفحص الآن عند كل دقيقة (الثانية 50) ليعطيك إشارات أسرع
        if bot_config["isRunning"] and (now.second == 50):
            try:
                ws = websocket.create_connection("wss://blue.derivws.com/websockets/v3?app_id=16929", timeout=15)
                ws.send(json.dumps({"ticks_history": bot_config["pair_id"], "count": 1000, "end": "latest", "style": "ticks"}))
                res = json.loads(ws.recv())
                if "history" in res:
                    perform_analysis(res["history"]["prices"], res["history"]["times"], bot_config["pair_id"])
                ws.close()
                time.sleep(5) # منع التكرار في نفس الثانية
            except Exception as e:
                add_log(f"Error: {str(e)}")
        time.sleep(0.5)

# --- الواجهة (UI) ---
UI = """
<!DOCTYPE html>
<html>
<head>
    <title>KHOURY AI BOT</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        :root { --neon: #00f3ff; --green: #39ff14; --red: #ff4757; }
        body { background: #06070a; color: white; font-family: sans-serif; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; }
        #login { position: fixed; inset: 0; background: #020617; z-index: 2000; display: flex; flex-direction: column; justify-content: center; align-items: center; }
        .box { background: rgba(0,243,255,0.02); padding: 30px; border-radius: 20px; border: 1px solid var(--neon); text-align: center; width: 300px; }
        input, select { background: #000; border: 1px solid #333; color: var(--neon); padding: 12px; width: 90%; margin-bottom: 15px; border-radius: 8px; text-align: center; }
        .btn { width: 100%; padding: 12px; border-radius: 8px; border: 1px solid var(--neon); background: transparent; color: var(--neon); font-weight: bold; cursor: pointer; }
        #dash { display: none; width: 90%; max-width: 400px; text-align: center; }
        .clock { font-size: 40px; color: var(--neon); margin: 10px 0; text-shadow: 0 0 10px var(--neon); }
        .display-area { border: 2px solid var(--neon); padding: 25px; border-radius: 20px; margin: 20px 0; background: rgba(0,243,255,0.05); min-height: 180px; display: flex; align-items: center; justify-content: center; }
        .logs { background: #000; height: 80px; padding: 10px; font-size: 11px; overflow-y: auto; color: #666; border-radius: 10px; text-align: left; border: 1px solid #111; }
    </style>
</head>
<body>
    <div id="login">
        <div class="box">
            <h2 style="color: var(--neon)">KHOURY LOGIN</h2>
            <input type="text" id="u" placeholder="USER ID">
            <input type="password" id="p" placeholder="PASSWORD">
            <button class="btn" onclick="check()">LOGIN</button>
        </div>
    </div>
    <div id="dash">
        <h2 style="color: var(--neon)">M5/M1 RSI PRO</h2>
        <select id="asset">
            {% for id, name in assets.items() %}
            <option value="{{id}}">{{name}}</option>
            {% endfor %}
        </select>
        <div class="clock" id="clk">00:00:00</div>
        <div style="display:flex; gap:10px; margin-bottom:20px;">
            <button class="btn" style="color:var(--green); border-color:var(--green);" onclick="ctl('start')">START</button>
            <button class="btn" style="color:var(--red); border-color:var(--red);" onclick="ctl('stop')">STOP</button>
        </div>
        <div class="display-area" id="mainDisp"></div>
        <div class="logs" id="lBox"></div>
    </div>
    <script>
        function check() {
            if(document.getElementById('u').value==='KHOURYBOT' && document.getElementById('p').value==='123456') {
                document.getElementById('login').style.display='none';
                document.getElementById('dash').style.display='block';
                setInterval(upd, 1000);
            } else alert('Error');
        }
        async function ctl(a) { await fetch(`/api/cmd?action=${a}&pair=${document.getElementById('asset').value}`); }
        async function upd() {
            document.getElementById('clk').innerText = new Date().toTimeString().split(' ')[0];
            const r = await fetch('/api/status');
            const d = await r.json();
            const disp = document.getElementById('mainDisp');
            if(d.show) {
                if(d.isSignal) {
                    disp.innerHTML = `<div style="text-align:left; width:100%">
                        <b>PAIR:</b> ${d.pair}<br>
                        <b>SIGNAL:</b> ${d.signal}<br>
                        <b>STRENGTH:</b> ${d.strength}%<br>
                        <b>ENTRY:</b> ${d.entry}
                    </div>`;
                } else { disp.innerHTML = "NO SIGNAL MATCH"; }
            } else { 
                let s = new Date().getSeconds();
                disp.innerHTML = d.run ? `ANALYZING... (${60-s}s left)` : "OFFLINE"; 
            }
            document.getElementById('lBox').innerHTML = d.logs.join('<br>');
        }
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
    bot_config["pair_name"] = ASSETS.get(bot_config["pair_id"], "Unknown")
    return jsonify({"ok": True})

@app.route('/api/status')
def get_status():
    show = (time.time() - bot_config["timestamp"]) < 50 and bot_config["timestamp"] > 0
    return jsonify({
        "run": bot_config["isRunning"], "show": show, "isSignal": bot_config["isSignal"],
        "signal": bot_config["direction"], "strength": bot_config["strength"],
        "pair": bot_config["pair_name"], "entry": bot_config["entryTime"], "logs": bot_config["logs"]
    })

if __name__ == "__main__":
    threading.Thread(target=smart_ws_worker, daemon=True).start()
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
