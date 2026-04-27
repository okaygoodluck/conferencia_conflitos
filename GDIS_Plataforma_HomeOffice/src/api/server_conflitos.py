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

from src.core import verificador_conflitos

# --- PROXY DE LOG ---
class LogProxy:
    def __init__(self, capture_stream):
        self.terminal = sys.__stdout__
        self.capture = capture_stream
    def write(self, data):
        if self.terminal: self.terminal.write(data)
        if self.capture: self.capture.write(data)
    def flush(self):
        if self.terminal: self.terminal.flush()
        if self.capture: self.capture.flush()

# --- ESTADO ---
STATE_LOCK = threading.Lock()
STATE = {} # job_id -> data

def _fmt_seconds(seconds):
    try: s = int(round(float(seconds)))
    except: s = 0
    if s < 0: s = 0
    h, m, ss = s // 3600, (s % 3600) // 60, s % 60
    return f"{h:02d}:{m:02d}:{ss:02d}" if h else f"{m:02d}:{ss:02d}"

def _log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")

# --- LOGICA ---
def _run_conflitos(job_id, base, di, df, user, passwd, situacoes, malhas, eq_manual=None, al_manual=None):
    capture = io.StringIO()
    with STATE_LOCK:
        STATE[job_id] = {
            "state": "running", "processed": 0, "total": 0, "elapsed": "00:00",
            "eta": "00:00", "conflitos": 0, "falhas": 0, "current": "", "cancel": False,
            "capture": capture
        }
    
    old_stdout = sys.stdout
    sys.stdout = LogProxy(capture)
    started_at = time.perf_counter()
    _log(f"Iniciando verificação: Job {job_id}")

    def cb(p):
        with STATE_LOCK:
            st = STATE.get(job_id)
            if not st: return
            if st.get("cancel"): raise RuntimeError("Cancelado pelo usuário.")
            
            st.update({
                "processed": int(p.get("processed") or 0),
                "total": int(p.get("total") or 0),
                "elapsed": _fmt_seconds(p.get("elapsed_seconds", 0.0)),
                "eta": _fmt_seconds(p.get("eta_seconds", 0.0)),
                "conflitos": int(p.get("conflitos") or 0),
                "falhas": int(p.get("falhas") or 0),
                "current": str(p.get("current") or ""),
            })

    try:
        r = verificador_conflitos.run_verificacao(base, di, df, user, passwd, progress_cb=cb, situacoes=situacoes, malhas=malhas, base_eq_manual=eq_manual, base_al_manual=al_manual)
        with STATE_LOCK:
            STATE[job_id].update({"state": "done", "result": {**r, "elapsed": _fmt_seconds(time.perf_counter() - started_at)}})
        _log(f"Concluído com sucesso: {job_id}")
    except Exception as e:
        with STATE_LOCK:
            if job_id in STATE:
                STATE[job_id].update({"state": "error", "error": str(e)})
        _log(f"ERRO: {e}")
    finally:
        sys.stdout = old_stdout

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
            return self._send_json(HTTPStatus.OK, {"status": "ok", "service": "conflitos"})

        if u.path == "/status":
            job_id = parse_qs(u.query).get("job_id", [""])[-1]
            with STATE_LOCK:
                st = STATE.get(job_id)
            if not st: return self._send_json(HTTPStatus.NOT_FOUND, {"error": "Job não encontrado"})
            capture_obj = st.get("capture")
            resp = {k: v for k, v in st.items() if k != "capture"}
            resp["log"] = capture_obj.getvalue() if capture_obj else ""
            return self._send_json(HTTPStatus.OK, resp)

        if u.path == "/result":
            job_id = parse_qs(u.query).get("job_id", [""])[-1]
            with STATE_LOCK:
                st = STATE.get(job_id)
            return self._send_json(HTTPStatus.OK, st.get("result", {}) if st else {})

        if u.path == "/export":
            job_id = parse_qs(u.query).get("job_id", [""])[-1]
            with STATE_LOCK:
                st = STATE.get(job_id)
            if not st: return self.send_response(HTTPStatus.NOT_FOUND)
            
            r = st.get("result", {})
            lines = ["manobra,situacoes,equipamentos_em_comum,alimentadores_em_comum"]
            for c in r.get("conflitos", []):
                lines.append(f"\"{c['manobra']}\",\"{'; '.join(c['situacoes'])}\",\"{'; '.join(c['equipamentos'])}\",\"{'; '.join(c['alimentadores'])}\"")
            
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/csv")
            self.send_header("Content-Disposition", f"attachment; filename=conflitos_{job_id}.csv")
            self.end_headers()
            self.wfile.write(("\n".join(lines) + "\n").encode("utf-8"))
            return

        self.send_response(HTTPStatus.NOT_FOUND)
        self.end_headers()

    def do_POST(self):
        try:
            u = urlparse(self.path)
            length = int(self.headers.get("Content-Length") or "0")
            print(f"[DEBUG] Recebendo POST em {u.path} (Length: {length})")
            # print(f"[DEBUG] Headers: {self.headers}")
            raw = self.rfile.read(length).decode("utf-8") if length > 0 else ""
            print(f"[DEBUG] Corpo recebido ({len(raw)} bytes)")
            
            body = {}
            if raw:
                if "application/x-www-form-urlencoded" in self.headers.get("Content-Type", ""):
                    parsed = parse_qs(raw)
                    body = {k: (",".join(v) if len(v) > 1 else v[0]) for k, v in parsed.items()}
                else:
                    try:
                        body = json.loads(raw) if raw else {}
                    except json.JSONDecodeError:
                        print(f"[ERROR] JSON malformado recebido: {raw[:100]}")
                        self._send_json(400, {"error": "Invalid JSON"})
                        return

            if u.path == "/start":
                job_id = str(uuid.uuid4())
                with STATE_LOCK: STATE[job_id] = {"state": "igniting"}
                
                sit = [s.strip() for s in (body.get("situacoes") or "").split(",") if s.strip()]
                mal = [m.strip() for m in (body.get("malhas") or "").split(",") if m.strip()]
                eq_man = [x.strip() for x in (body.get("equipamentos") or "").split(",") if x.strip()]
                al_man = [x.strip() for x in (body.get("alimentadores") or "").split(",") if x.strip()]
                
                threading.Thread(target=_run_conflitos, args=(job_id, body.get("manobra"), body.get("di"), body.get("df"), body.get("user"), body.get("pass"), sit, mal, eq_man, al_man), daemon=True).start()
                return self._send_json(HTTPStatus.OK, {"job_id": job_id})

            if u.path == "/stop":
                job_id = body.get("job_id")
                with STATE_LOCK:
                    st = STATE.get(job_id)
                    if st: st["cancel"] = True
                return self._send_json(HTTPStatus.OK, {"status": "stopping"})

            self.send_response(HTTPStatus.NOT_FOUND)
            self.end_headers()
        except Exception as e:
            print(f"[CRITICAL ERROR] Em do_POST: {e}")
            import traceback
            traceback.print_exc()
            self._send_json(500, {"error": str(e)})

    def do_OPTIONS(self):
        self.send_response(HTTPStatus.OK)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

def main():
    port = 8766
    print("="*60)
    print(f"   SERVIÇO DE VERIFICAÇÃO DE CONFLITOS (Porta {port})")
    print("="*60)
    try:
        httpd = _ThreadedServer(("0.0.0.0", port), Handler)
        httpd.serve_forever()
    except Exception as e:
        print(f"Erro: {e}")
        input("Pressione Enter para fechar...")

if __name__ == "__main__":
    main()
