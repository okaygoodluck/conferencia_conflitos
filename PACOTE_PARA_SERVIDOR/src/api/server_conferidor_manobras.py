import json
import os
import threading
import time
import uuid
import sys
import io
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from urllib.parse import parse_qs, urlparse

# Adiciona o root ao path para encontrar as ferramentas
root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if root_dir not in sys.path:
    sys.path.append(root_dir)

from src.core import conferidor_manobras

# --- ESTADO ---
STATE_LOCK = threading.Lock()
STATE = {} # job_id -> data
CACHE = {"equipamentos": None} # Cache global para a base de dados

def _log(msg, log_func=print):
    log_func(f"[{time.strftime('%H:%M:%S')}] {msg}")

def _run_conferidor(job_id, manobra, user, passwd):
    capture = io.StringIO()
    with STATE_LOCK:
        STATE[job_id] = {"state": "running", "capture": capture}
    
    def thread_log(*args, **kwargs):
        # Helper para imprimir apenas no buffer do job (Dashboard)
        # Removido sys.__stdout__ para evitar congelamento por bloqueio de terminal no Windows
        print(*args, file=capture, **kwargs)
        capture.flush()

    try:
        # Passa o cache se disponível para evitar recarregar o CSV de 40MB
        with STATE_LOCK: eq_cache = CACHE["equipamentos"]
        
        conferidor_manobras.main(
            manobra_param=manobra, 
            usuario_param=user, 
            senha_param=passwd, 
            headless=True, 
            log_func=thread_log,
            dados_equipamentos_cache=eq_cache
        )
        with STATE_LOCK: STATE[job_id]["state"] = "done"
    except Exception as e:
        with STATE_LOCK: STATE[job_id].update({"state": "error", "error": str(e)})
        _log(f"ERRO: {e}", log_func=thread_log)
    finally:
        pass

class _ThreadedServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

class Handler(BaseHTTPRequestHandler):
    def _send_json(self, code, obj):
        payload = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):
        # Silencia logs de requisições HTTP para não poluir o terminal
        return

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/health":
            return self._send_json(HTTPStatus.OK, {"status": "ok", "service": "conferidor_manobras"})

        if u.path == "/status":
            job_id = parse_qs(u.query).get("job_id", [""])[-1]
            with STATE_LOCK: st = STATE.get(job_id)
            if not st: return self._send_json(HTTPStatus.NOT_FOUND, {"error": "Job não encontrado"})
            capture_obj = st.get("capture")
            resp = {"state": st.get("state"), "log": capture_obj.getvalue() if capture_obj else "", "error": st.get("error", "")}
            return self._send_json(HTTPStatus.OK, resp)

        self.send_response(HTTPStatus.NOT_FOUND)
        self.end_headers()

    def do_POST(self):
        u = urlparse(self.path)
        length = int(self.headers.get("Content-Length") or "0")
        body = json.loads(self.rfile.read(length).decode("utf-8")) if length > 0 else {}

        if u.path == "/start":
            job_id = str(uuid.uuid4())
            with STATE_LOCK: STATE[job_id] = {"state": "igniting"}
            threading.Thread(target=_run_conferidor, args=(job_id, body.get("manobra"), body.get("usuario"), body.get("senha")), daemon=True).start()
            return self._send_json(HTTPStatus.OK, {"job_id": job_id})

        self.send_response(HTTPStatus.NOT_FOUND)
        self.end_headers()

    def do_OPTIONS(self):
        self.send_response(HTTPStatus.OK)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

def main():
    port = 8767
    print("="*60)
    print(f"   SERVIÇO CONFERIDOR DE MANOBRAS (Porta {port})")
    print("="*60)
    
    # Pré-carrega a base de equipamentos para o Cache (evita carregar em cada requisição)
    print("\n⏳ Pré-carregando base de equipamentos no Cache...")
    try:
        CACHE["equipamentos"] = conferidor_manobras._carregar_dados_equipamentos()
        print(f"✅ Base carregada! ({len(CACHE['equipamentos'])} equipamentos na memória)")
    except Exception as e:
        print(f"⚠️ Erro ao carregar cache inicial: {e}")

    try:
        httpd = _ThreadedServer(("0.0.0.0", port), Handler)
        print(f"\n🚀 Servidor pronto e aguardando conexões na porta {port}...")
        httpd.serve_forever()
    except Exception as e:
        print(f"Erro: {e}")
        input("Pressione Enter para fechar...")

if __name__ == "__main__":
    main()
