import http.server
import socketserver
import os
import json
import urllib.parse
import sys
import ctypes
import traceback
import signal
import time
from datetime import datetime

from src.core import verificador_conflitos
from src.core import verificador_regras_solicitacao
import ssl
from src.api import gerar_certificado

# --- CONFIGURAÇÃO E ESTADO ---
ORIGINAL_STDOUT = sys.stdout
STATE_LOCK = threading.Lock()
STATE = {
    "conflitos": {}, # job_id -> data
    "regras": {}     # job_id -> data
}

def _app_dir():
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def _set_state(tipo, job_id, patch):
    with STATE_LOCK:
        s = STATE[tipo].get(job_id) or {}
        s.update(patch)
        STATE[tipo][job_id] = s

def _get_state(tipo, job_id):
    with STATE_LOCK:
        return dict(STATE[tipo].get(job_id) or {})

def _fmt_seconds(seconds):
    try: s = int(round(float(seconds)))
    except: s = 0
    if s < 0: s = 0
    h, m, ss = s // 3600, (s % 3600) // 60, s % 60
    return f"{h:02d}:{m:02d}:{ss:02d}" if h else f"{m:02d}:{ss:02d}"

def _log_activity(msg):
    log_line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    
    # Escreve no console real do servidor (mesmo se sys.stdout estiver redirecionado)
    try:
        ORIGINAL_STDOUT.write(log_line + "\n")
        ORIGINAL_STDOUT.flush()
    except:
        print(log_line) # Fallback

    try:
        log_path = os.path.join(_app_dir(), "data", "atividades.log")
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(log_line + "\n")
    except:
        pass

# ... (restante do arquivo mantido, apenas corrigi imports e lógica de SSL abaixo) ...
