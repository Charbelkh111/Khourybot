import os
import json
import time
import threading
from flask import Flask, jsonify, render_template_string, request
import websocket
from datetime import datetime, timedelta

app = Flask(__name__)

# --- إعدادات البوت والذاكرة المؤقتة ---
bot_config = {
    "isRunning": False,
    "direction": "WAITING",
    "reason": "Scanning Market...",
    "pair_name": "EUR/JPY",
    "pair_id": "frxEURJPY",
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

# --- محرك التحليل الاحترافي ---
def perform_analysis(ticks, asset_id):
    global bot_config
    try:
        # 1. تحويل 1000 تيك إلى إغلاقات شموع (كل 60 تيك = 1 دقيقة)
        # هذا الجزء يحاكي حركة الشموع الحقيقية لحساب RSI بدقة
        candle_closes = [ticks[i] for i in range(59, len(ticks), 60)]
        
        # حساب RSI (14)
        period = 14
        rsi_val = 50 # قيمة افتراضية
        if len(candle_closes) > period:
            deltas = [candle_closes[i+1] - candle_closes[i] for i in range(len(candle_closes)-1)]
            up = sum([d for d in deltas[-period:] if d > 0]) / period
            down = sum([-d for d in deltas[-period:] if d < 0]) / period
            if down == 0: rsi_val = 100
            else: rsi_val = 100 - (100 / (1 + (up/down)))

        current_price = ticks[-1]
        
        # 2. تحليل اتجاه آخر 60 تيك (M1 Trend)
        price_start_60 = ticks[-60] if len(ticks) >= 60 else ticks[0]
        trend_m1_up = current_price > price_start_60
        
        # 3. تحليل اتجاه آخر 300 تيك (M5 Trend)
        price_start_300 = ticks[-300] if len(ticks) >= 300 else ticks[0]
        trend_m5_up = current_price > price_start_300

        # --- شروط دخول الصفقة ---
        is_call = (rsi_val > 50) and trend_m1_up and trend_m5_up
        is_put = (rsi_val < 50) and (not trend_m1_up) and (not trend_m5_up)

        # صياغة السبب للعرض على الشاشة
        reason = f"RSI:{round(rsi_val,1)} | M1:{'UP' if trend_m1_up else 'DN'} | M5:{'UP' if trend_m5_up else 'DN'}"

        bot_config.update({
            "isSignal": is_call or is_put,
            "direction": "CALL 🟢 (BUY)" if is_call else ("PUT 🔴 (SELL)" if is_put else "NO SIGNAL"),
            "reason": reason,
            "timestamp": time.time(),
            "entryTime": (datetime.now() + timedelta(seconds=10)).strftime("%H:%M"),
            "pair_name": ASSETS.get(asset_id, "Unknown")
        })
        add_log(f"Analysis @50s: {bot_config['direction']}")

    except Exception as e:
        add_log(f"Analysis Error: {str(e)}")

# --- عامل الاتصال بالسوق (WebSocket) ---
def smart_ws_worker():
    while True:
        now = datetime.now()
        # الفحص يبدأ عند الثانية 50 تماماً
        if bot_config["isRunning"] and now.second == 50:
            try:
                # الاتصال بـ Deriv API لجلب 1000 تيك
                ws = websocket.create_connection("wss://blue.derivws.com/websockets/v3?app_id=16929", timeout=12)
                ws.send(json.dumps({
                    "ticks_history": bot_config["pair_id"], 
                    "count": 1000, 
                    "end": "latest", 
                    "style": "ticks"
                }))
                res = json.loads(ws.recv())
                if "history" in res:
                    perform_analysis(res["history"]["prices"], bot_config["pair_id"])
                ws.close()
                time.sleep(5) # تجنب التكرار في نفس الدقيقة
            except Exception as e:
                add_log("Market Connection Failed")
        time.sleep(0.5)

# --- واجهة المستخدم النيون (HTML/JS) ---
UI = """
<!DOCTYPE html>
<html>
<head>
    <title>KHOURY M5 RSI BOT</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        :root { --neon: #00f3ff; --red: #ff4757; --bg: #06070a; }
        body { background: var(--bg); color: white; font-family: 'Segoe UI', sans-serif; text-align: center; margin: 0; padding: 20px; }
        .container { max-width: 400px; margin: auto; }
        .clock { font-size: 55px; color: var(--neon); margin: 25px 0; text-shadow: 0 0 20px var(--neon); font-weight: bold; }
        .display-area { border: 2px solid var(--neon); padding: 30px; border-radius: 20px; margin: 25px 0; background: rgba(0,243,255,0.03); min-height: 180px; box-shadow: inset 0 0 15px rgba(0,243,255,0.1); }
        .btn { padding: 15px; border-radius: 12px; border: 1px solid var(--neon); background: none; color: var(--neon); font-weight: bold; cursor: pointer; width: 48%; transition: 0.3s; }
        .btn-start { background: var(--neon); color: black; box-shadow: 0 0 20px var(--neon); }
        .btn-stop { border-color: var(--red); color: var(--red); }
        select { background: #000; border: 1px solid #333; color: var(--neon); padding: 12px; width: 100%; border-radius: 10px; margin-bottom: 25px; text-align: center; font-size: 16px; outline: none; }
        .log-box { font-size: 11px; color: #444; text-align: left; margin-top: 20px; font-family: monospace; }
        hr { border: 0; border-top: 1px solid #222; margin: 15px 0; }
    </style>
</head>
<body>
    <div class="container">
        <h2 style="color:var(--neon); letter-spacing: 2px;">RSI ALGORITHM</h2>
        
        <select id="pair">
            {% for id, name in assets.items() %}
            <option value="{{id}}">{{name}}</option>
            {% endfor %}
        </select>

        <div class="clock" id="clk">00:00:00</div>

        <div style="display:flex; justify-content: space-between;">
            <button class="btn btn-start" onclick="ctl('start')">START BOT</button>
            <button class="btn btn-stop" onclick="ctl('stop')">STOP BOT</button>
        </div>

        <div class="display-area" id="mainDisp">
            <p style="color:#555; margin-top: 60px;">STANDING BY...</p>
        </div>

        <div class="log-box" id="lBox"></div>
    </div>

    <script>
        async function ctl(a) { 
            const p = document.getElementById('pair').value;
            await fetch(`/api/cmd?action=${a}&pair=${p}`); 
        }

        async function update() {
            // تحديث الساعة المحلية
            document.getElementById('clk').innerText = new Date().toTimeString().split(' ')[0];
            
            const r = await fetch('/api/status');
            const d = await r.json();
            const disp = document.getElementById('mainDisp');
            
            if (d.show) {
                disp.innerHTML = `
                    <div style="text-align:left animation: fadeIn 0.5s">
                        <h2 style="color:${d.isSignal ? 'var(--neon)' : 'var(--red)'}; margin:0">${d.dir}</h2>
                        <p style="font-size:13px; color:#aaa; margin:10px 0;">${d.reason}</p>
                        <hr>
                        <b style="font-size:18px">NEXT ENTRY: ${d.entry}</b>
                    </div>`;
            } else {
                let s = new Date().getSeconds();
                let wait = 50 - s; if(wait < 0) wait += 60;
                disp.innerHTML = `<p style="color:#444; margin-top:60px;">SCANNING IN ${wait}s...<br><small>WAITING FOR SEC 50</small></p>`;
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
    # الرسالة تظهر لمدة 30 ثانية وتختفي تلقائياً
    show = (time.time() - bot_config["timestamp"]) < 30 and bot_config["timestamp"] > 0
    return jsonify({
        "show": show,
        "isSignal": bot_config["isSignal"],
        "dir": bot_config["direction"],
        "reason": bot_config["reason"],
        "entry": bot_config["entryTime"],
        "logs": bot_config["logs"]
    })

if __name__ == "__main__":
    # تشغيل محرك البحث في خلفية السيرفر
    threading.Thread(target=smart_ws_worker, daemon=True).start()
    # تشغيل تطبيق ويب Flask
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
