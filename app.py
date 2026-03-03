import os
import json
import time
import threading
from flask import Flask, jsonify, render_template_string, request
import websocket
from datetime import datetime, timedelta

app = Flask(__name__)

# إعدادات البوت
bot_config = {
    "isRunning": False,
    "direction": "في انتظار التحليل",
    "reason": "سيتم الفحص عند الثانية 50",
    "pair_id": "frxEURUSD",
    "timestamp": 0,
    "isSignal": False
}

ASSETS = {"frxEURUSD": "EUR/USD", "frxEURJPY": "EUR/JPY", "frxEURGBP": "EUR/GBP"}

# دالة حساب RSI مبسطة لضمان عدم التعليق
def get_rsi(prices, period=14):
    if len(prices) < period + 1: return 50
    up, down = 0, 0
    for i in range(len(prices)-period, len(prices)):
        diff = prices[i] - prices[i-1]
        if diff > 0: up += diff
        else: down -= diff
    if down == 0: return 100
    rs = up / down
    return 100 - (100 / (1 + rs))

def run_analysis():
    global bot_config
    try:
        # اتصال سريع لجلب البيانات
        ws = websocket.create_connection("wss://blue.derivws.com/websockets/v3?app_id=16929", timeout=10)
        ws.send(json.dumps({"ticks_history": bot_config["pair_id"], "count": 200, "end": "latest", "style": "ticks"}))
        res = json.loads(ws.recv())
        ws.close()

        prices = res["history"]["prices"]
        rsi_val = get_rsi(prices)
        current_price = prices[-1]
        open_price = prices[0] # سعر البداية للمقارنة

        # شروط الإشارة
        is_call = (rsi_val > 50) and (current_price > open_price)
        is_put = (rsi_val < 50) and (current_price < open_price)

        # تحديث الحالة
        bot_config.update({
            "isSignal": is_call or is_put,
            "direction": "شراء (CALL) 🟢" if is_call else ("بيع (PUT) 🔴" if is_put else "لا توجد إشارة"),
            "reason": "الاتجاه متوافق مع RSI" if (is_call or is_put) else f"RSI: {round(rsi_val,1)} (غير كافي)",
            "timestamp": time.time()
        })
    except:
        bot_config["reason"] = "خطأ في الاتصال بالسوق"

def worker():
    while True:
        now = datetime.now()
        # الفحص عند الثانية 50 من كل دقيقة
        if bot_config["isRunning"] and now.second == 50:
            run_analysis()
            time.sleep(5) # منع التكرار
        time.sleep(0.5)

UI = """
<!DOCTYPE html>
<html dir="rtl">
<head>
    <meta charset="UTF-8">
    <title>بوت خوري المطور</title>
    <style>
        body { background: #0b0e14; color: white; font-family: Arial; text-align: center; padding-top: 50px; }
        .card { border: 2px solid #00f3ff; display: inline-block; padding: 30px; border-radius: 20px; background: #161b22; box-shadow: 0 0 20px #00f3ff44; }
        .timer { font-size: 50px; color: #00f3ff; margin: 20px 0; }
        .btn { padding: 10px 30px; font-size: 18px; cursor: pointer; border-radius: 10px; border: none; margin: 5px; }
        .start { background: #00ff88; color: black; }
        .stop { background: #ff4444; color: white; }
        #result { margin-top: 20px; font-size: 20px; border-top: 1px solid #333; padding-top: 15px; }
    </style>
</head>
<body>
    <div class="card">
        <h2>تحليل RSI + Trend</h2>
        <div class="timer" id="timer">00</div>
        <button class="btn start" onclick="ctl('start')">تشغيل البوت</button>
        <button class="btn stop" onclick="ctl('stop')">إيقاف</button>
        <div id="result">اضغط تشغيل للبدء</div>
    </div>
    <script>
        async function ctl(a) { await fetch(`/api/cmd?action=${a}`); }
        async function update() {
            const r = await fetch('/api/status');
            const d = await r.json();
            
            // تحديث العداد
            let s = new Date().getSeconds();
            let w = 50 - s; if(w < 0) w += 60;
            document.getElementById('timer').innerText = w;

            if (d.active) {
                document.getElementById('result').innerHTML = `<b style="color:#00f3ff">${d.dir}</b><br><small>${d.reason}</small>`;
            } else if(d.running) {
                document.getElementById('result').innerHTML = "جاري مراقبة السوق...";
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
    return jsonify({"ok": True})

@app.route('/api/status')
def get_status():
    return jsonify({
        "running": bot_config["isRunning"],
        "active": (time.time() - bot_config["timestamp"]) < 30 and bot_config["timestamp"] > 0,
        "dir": bot_config["direction"],
        "reason": bot_config["reason"]
    })

if __name__ == "__main__":
    threading.Thread(target=worker, daemon=True).start()
    app.run(host='0.0.0.0', port=5000)
