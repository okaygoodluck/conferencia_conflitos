# src/api/app_regras_local.py
import os
import sys
from flask import Flask, request, jsonify
from src.core.verificador_regras_solicitacao import VerificadorRegrasSolicitacao

app = Flask(__name__)

@app.route('/verificar', methods=['POST'])
def verificar():
    data = request.json
    sol_id = data.get('solicitacao')
    v = VerificadorRegrasSolicitacao()
    # v.iniciar()...
    return jsonify({"status": "recebido", "solicitacao": sol_id})

if __name__ == "__main__":
    port = int(os.getenv("REGRAS_PORT", 8766))
    app.run(port=port)
