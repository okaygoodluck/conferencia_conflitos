import json
import os
import threading
import time
import uuid
import ctypes
import sys
import io
import importlib
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from urllib.parse import parse_qs, urlparse

from src.core import verificador_conflitos
from src.core import verificador_regras_solicitacao

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

# --- LOGICA DE NEGÓCIO (WRAPPERS) ---

def _run_conflitos(job_id, base, di, df, user, passwd, situacoes, malhas, eq_manual=None, al_manual=None):
    capture = io.StringIO()
    _set_state("conflitos", job_id, {
        "state": "running", "processed": 0, "total": 0, "elapsed": "00:00",
        "eta": "00:00", "conflitos": 0, "falhas": 0, "current": "", "cancel": False,
        "last_update_at": time.time(),
        "capture": capture
    })
    
    old_stdout = sys.stdout
    sys.stdout = capture
    started_at = time.perf_counter()
    
    print(f"=== INICIANDO VERIFICAÇÃO DE CONFLITOS (Job: {job_id}) ===")
    if base: print(f"Manobra Base: {base}")
    if eq_manual: print(f"Equipamentos Manuais: {', '.join(eq_manual)}")
    if al_manual: print(f"Alimentadores Manuais: {', '.join(al_manual)}")
    print(f"Período: {di} a {df}")
    print(f"Usuário: {user} | Situações: {', '.join(situacoes)}")
    print(f"Malhas: {', '.join(m for m in malhas if m) or 'Todas'}")
    print("-" * 60)

    def cb(p):
        st = _get_state("conflitos", job_id)
        if st.get("cancel"): raise RuntimeError("Cancelado pelo usuário.")
        _set_state("conflitos", job_id, {
            "processed": int(p.get("processed") or 0),
            "total": int(p.get("total") or 0),
            "elapsed": _fmt_seconds(p.get("elapsed_seconds", 0.0)),
            "eta": _fmt_seconds(p.get("eta_seconds", 0.0)),
            "rate_per_min": float(p.get("rate_per_min") or 0.0),
            "last_seconds": float(p.get("last_seconds") or 0.0),
            "conflitos": int(p.get("conflitos") or 0),
            "falhas": int(p.get("falhas") or 0),
            "current": str(p.get("current") or ""),
            "last_update_at": time.time(),
        })
        print(f"[{time.strftime('%H:%M:%S')}] Progresso: {p['processed']}/{p['total']} | Conflitos: {p['conflitos']} | ETA: {_fmt_seconds(p['eta_seconds'])} | Analisando: {p['current']}")

    try:
        importlib.reload(verificador_conflitos)
        r = verificador_conflitos.run_verificacao(base, di, df, user, passwd, progress_cb=cb, situacoes=situacoes, malhas=malhas, base_eq_manual=eq_manual, base_al_manual=al_manual)
        _set_state("conflitos", job_id, {"state": "done", "result": {**r, "elapsed": _fmt_seconds(time.perf_counter() - started_at)}})
        _log_activity(f"CONFLITOS CONCLUÍDO: Job {job_id} | Usuário: {user} | Tempo: {_fmt_seconds(time.perf_counter() - started_at)}")
    except Exception as e:
        _set_state("conflitos", job_id, {"state": "error", "error": str(e)})
        _log_activity(f"ERRO CONFLITOS: Job {job_id} | Usuário: {user} | Erro: {e}")
    finally:
        sys.stdout = old_stdout

def _run_regras(job_id, manobra, user, passwd):
    capture = io.StringIO()
    _set_state("regras", job_id, {"state": "running", "capture": capture})
    old_stdout = sys.stdout
    sys.stdout = capture
    try:
        importlib.reload(verificador_regras_solicitacao)
        verificador_regras_solicitacao.main(manobra_param=manobra, usuario_param=user, senha_param=passwd, headless=True)
        _set_state("regras", job_id, {"state": "done"})
        _log_activity(f"REGRAS CONCLUÍDO: Job {job_id} | Usuário: {user} | Manobra: {manobra}")
    except Exception as e:
        _set_state("regras", job_id, {"state": "error", "error": str(e)})
        _log_activity(f"ERRO REGRAS: Job {job_id} | Usuário: {user} | Erro: {e}")
    finally:
        sys.stdout = old_stdout

# --- SERVIDOR HTTP ---

class _ThreadedServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

class Handler(BaseHTTPRequestHandler):
    def _send_json(self, code, obj):
        payload = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(payload)

    def _send_file(self, path, content_type):
        try:
            with open(path, "rb") as f:
                data = f.read()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.end_headers()
            self.wfile.write(data)
        except:
            self.send_response(HTTPStatus.NOT_FOUND)
            self.end_headers()

    def do_GET(self):
        u = urlparse(self.path)
        # UI Principal
        if u.path == "/":
            ui_path = os.path.join(_app_dir(), "temp", "index_unificado.html")
            return self._send_file(ui_path, "text/html; charset=utf-8")
        
        # Ativos
        if u.path == "/favicon.ico" or u.path.startswith("/assets/"):
            name = u.path.split("/")[-1]
            ext = name.split(".")[-1].lower()
            ct = "image/x-icon" if ext == "ico" else "image/png"
            path = os.path.join(_app_dir(), "assets", name)
            return self._send_file(path, ct)

        # API Conflitos
        if u.path == "/conflitos/status":
            job_id = parse_qs(u.query).get("job_id", [""])[-1]
            st = _get_state("conflitos", job_id)
            if not st: return self._send_json(HTTPStatus.NOT_FOUND, {"error": "Job não encontrado"})
            capture_obj = st.get("capture")
            resp = {k: v for k, v in st.items() if k != "capture"}
            resp["log"] = capture_obj.getvalue() if capture_obj else ""
            return self._send_json(HTTPStatus.OK, resp)

        if u.path == "/conflitos/result":
            job_id = parse_qs(u.query).get("job_id", [""])[-1]
            st = _get_state("conflitos", job_id)
            return self._send_json(HTTPStatus.OK, st.get("result", {}))

        if u.path == "/conflitos/export":
            job_id = parse_qs(u.query).get("job_id", [""])[-1]
            st = _get_state("conflitos", job_id)
            r = st.get("result", {})
            lines = ["manobra,situacoes,equipamentos_em_comum,alimentadores_em_comum"]
            for c in r.get("conflitos", []):
                lines.append(f"\"{c['manobra']}\",\"{'; '.join(c['situacoes'])}\",\"{'; '.join(c['equipamentos'])}\",\"{'; '.join(c['alimentadores'])}\"")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/csv")
            self.end_headers()
            self.wfile.write(("\n".join(lines) + "\n").encode("utf-8"))
            return

        # API Regras
        if u.path == "/regras/status":
            job_id = parse_qs(u.query).get("job_id", [""])[-1]
            st = _get_state("regras", job_id)
            if not st: return self._send_json(HTTPStatus.NOT_FOUND, {"error": "Job não encontrado"})
            capture_obj = st.get("capture")
            resp = {"state": st.get("state"), "log": capture_obj.getvalue() if capture_obj else "", "error": st.get("error", "")}
            return self._send_json(HTTPStatus.OK, resp)

        self.send_response(HTTPStatus.NOT_FOUND)
        self.end_headers()

    def do_POST(self):
        u = urlparse(self.path)
        length = int(self.headers.get("Content-Length") or "0")
        body = {}
        if length > 0:
            raw = self.rfile.read(length).decode("utf-8")
            if "application/x-www-form-urlencoded" in self.headers.get("Content-Type", ""):
                parsed = parse_qs(raw)
                body = {k: (",".join(v) if len(v) > 1 else v[0]) for k, v in parsed.items()}
            else:
                body = json.loads(raw)

        if u.path == "/conflitos/start":
            job_id = str(uuid.uuid4())
            _set_state("conflitos", job_id, {"state": "igniting"})
            sit = (body.get("situacoes") or "").split(",")
            mal = (body.get("malhas") or "").split(",")
            eq_man = [x.strip() for x in (body.get("equipamentos") or "").split(",") if x.strip()]
            al_man = [x.strip() for x in (body.get("alimentadores") or "").split(",") if x.strip()]
            _log_activity(f"CONFLITOS INICIADO: Job {job_id} | Usuário: {body.get('user')} | Base: {body.get('manobra')} | Período: {body.get('di')} - {body.get('df')}")
            threading.Thread(target=_run_conflitos, args=(job_id, body.get("manobra"), body.get("di"), body.get("df"), body.get("user"), body.get("pass"), sit, mal, eq_man, al_man), daemon=True).start()
            return self._send_json(HTTPStatus.OK, {"job_id": job_id})

        if u.path == "/regras/start":
            job_id = str(uuid.uuid4())
            _set_state("regras", job_id, {"state": "igniting"})
            _log_activity(f"REGRAS INICIADO: Job {job_id} | Usuário: {body.get('usuario')} | Manobra: {body.get('manobra')}")
            threading.Thread(target=_run_regras, args=(job_id, body.get("manobra"), body.get("usuario"), body.get("senha")), daemon=True).start()
            return self._send_json(HTTPStatus.OK, {"job_id": job_id})

        self.send_response(HTTPStatus.NOT_FOUND)
        self.end_headers()

    def log_message(self, format, *args): pass

def main():
    host, port = "0.0.0.0", 8765
    
    # Verifica se a porta está em uso antes de ocultar a janela
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if s.connect_ex((host, port)) == 0:
            print(f"\n[ERRO] A porta {port} já está em uso!")
            print("Certifique-se de fechar outras instâncias do Verificador antes de iniciar a Plataforma.")
            input("\nPressione Enter para sair...")
            sys.exit(1)

    print("\n" + "="*60)
    print("      PLATAFORMA INTEGRADA GDIS - SERVIDOR ATIVO")
    print("="*60)
    print(f"URL Local: http://127.0.0.1:{port}/")
    print(f"URL Rede:  http://[IP_DO_SERVIDOR]:{port}/")
    print("Pressione Ctrl+C para encerrar o servidor com segurança.")
    print("="*60 + "\n")

    try:
        _ThreadedServer((host, port), Handler).serve_forever()
    except Exception as e:
        if os.name == 'nt':
            whnd = ctypes.windll.kernel32.GetConsoleWindow()
            if whnd != 0: ctypes.windll.user32.ShowWindow(whnd, 5) # Show
        print(f"Erro fatal no servidor: {e}")
        input("Pressione Enter para fechar...")

if __name__ == "__main__":
    main()
