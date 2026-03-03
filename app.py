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
    "reason": "",
    "strength": 0,
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
    
    candle_closes = [ticks[i] for i in range(59, len(ticks), 60)]
    rsi_val = calculate_rsi(candle_closes, 14)
    current_price = ticks[-1]
    now = datetime.now()
    
    start_of_5m = now.replace(minute=(now.minute // 5) * 5, second=0, microsecond=0)
    start_of_1m = now.replace(second=0, microsecond=0)
    
    price_at_5m = next((ticks[i] for i, t in enumerate(times) if datetime.fromtimestamp(int(t)) >= start_of_5m), ticks[0])
    price_at_1m = next((ticks[i] for i, t in enumerate(times) if datetime.fromtimestamp(int(t)) >= start_of_1m), ticks[-60] if len(ticks) > 60 else ticks[0])

    # تحديد الأسباب في حال عدم وجود إشارة
    reason = ""
    is_call = False
    is_put = False

    if rsi_val > 50:
        if current_price > price_at_5m:
            if current_price > price_at_1m:
                is_call = True
            else: reason = "M1 Trend is Down"
        else: reason = "M5 Trend is Down"
    elif rsi_val < 50:
        if current_price < price_at_5m:
            if current_price < price_at_1m:
                is_put = True
            else: reason = "M1 Trend is Up"
        else: reason = "M5 Trend is Up"
    else: reason = "RSI Neutral (50)"

    next_entry = (now + timedelta(seconds=10)).strftime("%H:%M")

    if is_call:
        bot_config.update({
            "isSignal": True, "direction": "CALL 🟢", "strength": round(rsi_val, 1),
            "pair_name": ASSETS[asset_id], "timestamp": time.time(), "entryTime": next_entry, "reason": "All Conditions Met"
        })
        add_log(f"SIGNAL: CALL (RSI:{rsi_val:.1f})")
    elif is_put:
        bot_config.update({
            "isSignal": True, "direction": "PUT 🔴", "strength": round(100 - rsi_val, 1),
            "pair_name": ASSETS[asset_id], "timestamp": time.time(), "entryTime": next_entry, "reason": "All Conditions Met"
        })
        add_log(f"SIGNAL: PUT (RSI:{rsi_val:.1f})")
    else:
        bot_config.update({
            "isSignal": False, "direction": "NO SIGNAL", "reason": reason,
            "timestamp": time.time(), "pair_name": ASSETS[asset_id]
        })
        add_log(f"NO SIGNAL: {reason}")

def smart_ws_worker():
    while True:
        now = datetime.now()
        if bot_config["isRunning"] and (now.second == 50):
            try:
                ws = websocket.create_connection("wss://blue.derivws.com/websockets/v3?app_id=16929", timeout=15)
                ws.send(json.dumps({"ticks_history": bot_config["pair_id"], "count": 1000, "end": "latest", "style": "ticks"}))
                res = json.loads(ws.recv())
                if "history" in res:
                    perform_analysis(res["history"]["prices"], res["history"]["times"], bot_config["pair_id"])
                ws.close()
                time.sleep(2)
            except Exception as e:
                add_log(f"Error: {str(e)}")
        time.sleep(0.5)

UI = """
<!DOCTYPE html>
<html>
<head>
    <title>KHOURY PRO BOT</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        :root { --neon: #00f3ff; --green: #39ff14; --red: #ff4757; }
        body { background: #06070a; color: white; font-family: sans-serif; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; }
        #login { position: fixed; inset: 0; background: #020617; z-index: 2000; display: flex; flex-direction: column; justify-content: center; align-items: center; }
        .box { background: rgba(0,243,255,0.02); padding: 30px; border-radius: 20px; border: 1px solid var(--neon); text-align: center; width: 300px; }
        input, select { background: #000; border: 1px solid #333; color: var(--neon); padding: 12px; width: 90%; margin-bottom: 15px; border-radius: 8px; text-align: center; }
        .btn { width: 100%; padding: 12px; border-radius: 8px; border: 1px solid var(--neon); background: transparent; color: var(--neon); font-weight: bold; cursor: pointer; }
        #dash { display: none; width: 90%; max-width: 400px; text-align: center; }
        .clock { font-size: 40px; color: var(--neon); margin: 10px 0; }
        .display-area { border: 2px solid var(--neon); padding: 25px; border-radius: 20px; margin: 20px 0; background: rgba(0,243,255,0.05); min-height: 180px; }
        .logs { background: #000; height: 80px; padding: 10px; font-size: 11px; overflow-y: auto; color: #666; border-radius: 10px; text-align: left; }
    </style>
</head>
<body>
    <div id="login">
        <div class="box">
            <h2 style="color: var(--neon)">KHOURY AI</h2>
            <input type="text" id="u" placeholder="USER ID">
            <input type="password" id="p" placeholder="PASSWORD">
            <button class="btn" onclick="check()">LOGIN</button>
        </div>
    </div>
    <div id="dash">
        <h2 style="color: var(--neon)">M1 ANALYSIS</h2>
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
                    disp.innerHTML = `<div style="text-align:left; color:var(--green)">
                        <b>[SIGNAL FOUND]</b><br>
                        PAIR: ${d.pair}<br>
                        DIR: ${d.signal}<br>
                        ENTRY: ${d.entry}
                    </div>`;
                } else {
                    disp.innerHTML = `<div style="text-align:left; color:var(--red)">
                        <b>[NO SIGNAL]</b><br>
                        PAIR: ${d.pair}<br>
                        REASON: ${d.reason}
                    </div>`;
                }
            } else { 
                let s = new Date().getSeconds();
                disp.innerHTML = d.run ? `<div style="color:#444">WAITING FOR SEC 50...<br>(${50 > s ? 50-s : 110-s}s left)</div>` : "SYSTEM OFFLINE"; 
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
    # تعديل: الرسالة تظهر فقط لمدة 30 ثانية بعد التحليل
    show = (time.time() - bot_config["timestamp"]) < 30 and bot_config["timestamp"] > 0
    return jsonify({
        "run": bot_config["isRunning"], "show": show, "isSignal": bot_config["isSignal"],
        "signal": bot_config["direction"], "reason": bot_config["reason"],
        "pair": bot_config["pair_name"], "entry": bot_config["entryTime"], "logs": bot_config["logs"]
    })

if __name__ == "__main__":
    threading.Thread(target=smart_ws_worker, daemon=True).start()
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
