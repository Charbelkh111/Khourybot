from flask import Flask, request, jsonify
from flask_cors import CORS
import pandas as pd
import pytesseract
from PIL import Image
import io
import base64

app = Flask(__name__)
CORS(app) 

# ⚠️ قم بتحديث هذه القائمة بالمعرفات المسموح بها
AUTHORIZED_USERS = ["64485064"]

# يجب تحديد مسار pytesseract.exe إذا لم يكن في الـ PATH على الخادم
# pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

def analyze_with_indicators(chart_data):
    try:
        df = pd.DataFrame(chart_data)
        df['close'] = pd.to_numeric(df['close'])
        
        df['SMA_5'] = df['close'].rolling(window=5).mean()
        df['SMA_10'] = df['close'].rolling(window=10).mean()

        if len(df) >= 10:
            last_sma5 = df['SMA_5'].iloc[-1]
            last_sma10 = df['SMA_10'].iloc[-1]
            prev_sma5 = df['SMA_5'].iloc[-2]
            prev_sma10 = df['SMA_10'].iloc[-2]

            if last_sma5 > last_sma10 and prev_sma5 <= prev_sma10:
                return "Up", 0.90
            
            elif last_sma5 < last_sma10 and prev_sma5 >= prev_sma10:
                return "Down", 0.90

        return "HOLD", 0.50

    except Exception as e:
        print(f"Error during analysis: {e}")
        return "ERROR", 0.0

@app.route('/analyze-chart', methods=['POST'])
def analyze_chart():
    data = request.json
    user_id = data.get('user_id')
    chart_data = data.get('chart_data')

    if user_id not in AUTHORIZED_USERS:
        return jsonify({"status": "access_denied", "message": "User not authorized"}), 403

    if not chart_data:
        return jsonify({"error": "No chart data provided"}), 400

    signal, confidence = analyze_with_indicators(chart_data)

    return jsonify({
        "signal": signal,
        "confidence": confidence
    })

@app.route('/analyze-balance', methods=['POST'])
def analyze_balance():
    data = request.json
    image_data = data.get('image')
    rect = data.get('rect')

    if not image_data or not rect:
        return jsonify({"error": "No image or rect data provided"}), 400

    try:
        base64_image_data = image_data.split(',')[1]
        image_bytes = base64.b64decode(base64_image_data)
        full_image = Image.open(io.BytesIO(image_bytes))

        cropped_image = full_image.crop((rect['x'], rect['y'], rect['x'] + rect['width'], rect['y'] + rect['height']))
        cropped_image = cropped_image.convert('L')
        
        text = pytesseract.image_to_string(cropped_image, config='--psm 6')
        cleaned_text = ''.join(c for c in text if c.isdigit() or c == '.')
        
        if not cleaned_text:
            return jsonify({"balance": None})
            
        balance = float(cleaned_text)

        return jsonify({"balance": balance})
    except Exception as e:
        print(f"Error during balance analysis: {e}")
        return jsonify({"balance": None}), 500

if __name__ == '__main__':
    app.run(port=10000)
