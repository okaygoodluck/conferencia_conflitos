import json
import os
import threading
import time
import uuid
import sys
import io
import traceback
from datetime import datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from urllib.parse import parse_qs, urlparse

# Garante flushing imediato de stdout/stderr para streaming de logs sem atraso
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(line_buffering=True)

# Adiciona o root ao path para encontrar as ferramentas
root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if root_dir not in sys.path:
    sys.path.append(root_dir)

from src.core import conferidor_manobras

# --- ESTADO ---
STATE_LOCK = threading.Lock()
STATE = {} # job_id -> data
CACHE = {"equipamentos": None} # Cache global para a base de dados

# Tempo de retenção de jobs concluídos em memória (30 minutos)
JOB_TTL_SECONDS = 30 * 60

def _log(msg, log_func=print):
    log_func(f"[{time.strftime('%H:%M:%S')}] {msg}")

def _cleanup_expired_jobs():
    """Remove jobs expirados do STATE para evitar vazamento de memória."""
    now = datetime.now()
    with STATE_LOCK:
        expired = []
        for jid, st in STATE.items():
            if st.get("state") in ("done", "error") and "finished_at" in st:
                fin = st["finished_at"]
                if isinstance(fin, str):
                    try: fin = datetime.fromisoformat(fin)
                    except: fin = None
                if isinstance(fin, datetime) and (now - fin).total_seconds() > JOB_TTL_SECONDS:
                    expired.append(jid)
        for jid in expired:
            STATE.pop(jid, None)
    if expired:
        _log(f"[INFO] Limpeza de {len(expired)} job(s) expirado(s).")

def _run_conferidor(job_id, manobras_lista, user, passwd):
    capture = io.StringIO()
    with STATE_LOCK:
        STATE[job_id] = {
            "state": "running", 
            "capture": capture,
            "manobras": manobras_lista,
            "total": len(manobras_lista)
        }

    def thread_log(*args, **kwargs):
        print(*args, file=capture, **kwargs)
        capture.flush()

    try:
        import importlib
        importlib.reload(conferidor_manobras)
        # Passa o cache se disponível para evitar recarregar o CSV de 40MB
        with STATE_LOCK:
            eq_cache = CACHE["equipamentos"]

        conferidor_manobras.main(
            manobra_param=manobras_lista,
            usuario_param=user,
            senha_param=passwd,
            headless=True,
            log_func=thread_log,
            dados_equipamentos_cache=eq_cache
        )
        with STATE_LOCK:
            STATE[job_id]["state"] = "done"
            STATE[job_id]["finished_at"] = datetime.now()
    except Exception as e:
        tb = traceback.format_exc()
        with STATE_LOCK:
            STATE[job_id].update({"state": "error", "error": str(e), "finished_at": datetime.now()})
        _log(f"ERRO: {e}\n--- TRACEBACK COMPLETO ---\n{tb}", log_func=thread_log)

    # Agendamento de limpeza após conclusão
    threading.Timer(JOB_TTL_SECONDS, _cleanup_expired_jobs).start()

class _ThreadedServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

class Handler(BaseHTTPRequestHandler):
    def _send_json(self, code, obj):
        payload = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
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
        if u.path != "/health":
            _log(f"GET {u.path}")

        if u.path == "/health":
            return self._send_json(HTTPStatus.OK, {"status": "ok", "service": "conferidor_manobras"})

        if u.path == "/status":
            job_id = parse_qs(u.query).get("job_id", [""])[-1]
            with STATE_LOCK:
                st = STATE.get(job_id)
            if not st:
                return self._send_json(HTTPStatus.NOT_FOUND, {"error": "Job não encontrado"})
            capture_obj = st.get("capture")
            resp = {
                "state": st.get("state"),
                "log": capture_obj.getvalue() if capture_obj else "",
                "error": st.get("error", ""),
                "manobras": st.get("manobras", []),
                "total": st.get("total", 0)
            }
            return self._send_json(HTTPStatus.OK, resp)

        self.send_response(HTTPStatus.NOT_FOUND)
        self.end_headers()

    def do_POST(self):
        u = urlparse(self.path)
        _log(f"POST {u.path}")
        length = int(self.headers.get("Content-Length") or "0")
        body = json.loads(self.rfile.read(length).decode("utf-8")) if length > 0 else {}

        if u.path == "/start":
            # A-02: Validação de entrada obrigatória (suporta 1 ou múltiplas manobras em texto)
            manobra_raw = str(body.get("manobra") or "").strip()
            usuario = (body.get("usuario") or "").strip()
            senha = (body.get("senha") or "").strip()

            manobras_lista = list(dict.fromkeys(re.findall(r'\b\d{6,10}\b', manobra_raw)))

            if not manobras_lista:
                return self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Nenhum número de manobra válido informado."})
            if not usuario or not senha:
                return self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Credenciais de usuário são obrigatórias."})

            job_id = str(uuid.uuid4())
            with STATE_LOCK:
                STATE[job_id] = {"state": "igniting", "manobras": manobras_lista, "total": len(manobras_lista)}
            threading.Thread(target=_run_conferidor, args=(job_id, manobras_lista, usuario, senha), daemon=True).start()
            return self._send_json(HTTPStatus.OK, {"job_id": job_id, "total": len(manobras_lista)})

        self.send_response(HTTPStatus.NOT_FOUND)
        self.end_headers()

    def do_OPTIONS(self):
        self.send_response(HTTPStatus.OK)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

def _async_load_cache():
    _log("[INFO] Iniciando carregamento da base de equipamentos em segundo plano...")
    try:
        data = conferidor_manobras._carregar_dados_equipamentos()
        with STATE_LOCK:
            CACHE["equipamentos"] = data
        _log(f"[OK] Base de equipamentos carregada! ({len(data)} itens)")
    except Exception as e:
        _log(f"[ERRO] Falha ao carregar cache: {e}")

def main():
    port = 8767
    print("="*60)
    print(f"   SERVIÇO CONFERIDOR DE MANOBRAS (Porta {port})")
    print("="*60)

    # Inicia o carregamento pesado em background para liberar a porta 8767 imediatamente
    threading.Thread(target=_async_load_cache, daemon=True).start()

    try:
        httpd = _ThreadedServer(("0.0.0.0", port), Handler)
        print(f"\n[START] Servidor aberto em http://127.0.0.1:{port}")
        print("[INFO] A porta já está ativa. O Hub Central já deve reconhecer o serviço.")
        httpd.serve_forever()
    except Exception as e:
        print(f"Erro fatal ao iniciar servidor: {e}")
        input("Pressione Enter para fechar...")

if __name__ == "__main__":
    main()
