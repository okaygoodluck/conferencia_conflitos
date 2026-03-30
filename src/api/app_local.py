# src/api/app_local.py
import os
from flask import Flask, jsonify

app = Flask(__name__)

@app.route('/saude', methods=['GET'])
def saude():
    return jsonify({"status": "operacional"})

if __name__ == "__main__":
    port = int(os.getenv("GDIS_PORT", 8765))
    app.run(port=port)
