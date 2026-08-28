import collections
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from urllib.parse import parse_qs, urlparse
import urllib.request
import urllib.error
import uuid
import webbrowser

# Garante flushing imediato de stdout/stderr para streaming de logs sem atraso
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(line_buffering=True)

# Configuração de Portas
PORT_HUB = 8765
PORT_CONFLITOS = 8766
PORT_CONFERIDOR = 8767

def _app_dir():
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Autenticação de Administrador
CONFIG_ADMIN_PATH = os.path.join(_app_dir(), "config_admin.json")
DEFAULT_ADMIN_PASSWORD = "cemig@2026"
ACTIVE_ADMIN_TOKENS = set()

def get_admin_password():
    if os.path.exists(CONFIG_ADMIN_PATH):
        try:
            with open(CONFIG_ADMIN_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("admin_password", DEFAULT_ADMIN_PASSWORD)
        except Exception:
            pass
    return DEFAULT_ADMIN_PASSWORD

def is_admin_authenticated(headers):
    token = headers.get("X-Admin-Token")
    if token and token in ACTIVE_ADMIN_TOKENS:
        return True
    password = headers.get("X-Admin-Password")
    if password and password == get_admin_password():
        return True
    return False

def _is_server_alive(port):
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/health")
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            return resp.status == 200
    except Exception:
        return False

class ProcessManager:
    """Gerenciador centralizado de sub-processos da plataforma GDIS (sem janelas extras)"""
    def __init__(self, app_dir):
        self.app_dir = app_dir
        self.lock = threading.RLock()
        self.processes = {
            "hub": {
                "name": "Hub Central (Porta 8765)",
                "script": os.path.join("src", "api", "app_unificado.py"),
                "port": PORT_HUB,
                "process": None,
                "logs": collections.deque(maxlen=2000),
                "log_counter": 0,
                "thread": None
            },
            "conflitos": {
                "name": "Verificador de Conflitos (Porta 8766)",
                "script": os.path.join("src", "api", "server_conflitos.py"),
                "port": PORT_CONFLITOS,
                "process": None,
                "logs": collections.deque(maxlen=2000),
                "log_counter": 0,
                "thread": None
            },
            "conferidor_manobras": {
                "name": "Conferidor de Manobras (Porta 8767)",
                "script": os.path.join("src", "api", "server_conferidor_manobras.py"),
                "port": PORT_CONFERIDOR,
                "process": None,
                "logs": collections.deque(maxlen=2000),
                "log_counter": 0,
                "thread": None
            }
        }
        self.add_log("hub", f"[HUB] Plataforma GDIS inicializada na porta {PORT_HUB}.")

    def add_log(self, service_key, text):
        with self.lock:
            if service_key in self.processes:
                svc = self.processes[service_key]
                svc["log_counter"] += 1
                entry = {
                    "id": svc["log_counter"],
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "text": text,
                    "service": service_key
                }
                svc["logs"].append(entry)

    def _read_output(self, service_key, proc):
        try:
            for line in iter(proc.stdout.readline, ''):
                if not line:
                    break
                line_clean = line.rstrip('\r\n')
                if line_clean:
                    self.add_log(service_key, line_clean)
        except Exception as e:
            self.add_log(service_key, f"[ERRO LEITURA LOG] {e}")
        finally:
            if proc.stdout:
                try: proc.stdout.close()
                except: pass
            with self.lock:
                if self.processes[service_key]["process"] == proc:
                    self.processes[service_key]["process"] = None
                self.add_log(service_key, f"[{self.processes[service_key]['name']}] Processo finalizado.")

    def start_service(self, service_key):
        with self.lock:
            if service_key not in self.processes or service_key == "hub":
                return False, "Serviço inválido ou de gerenciamento próprio."

            svc = self.processes[service_key]
            if svc["process"] is not None and svc["process"].poll() is None:
                return True, f"{svc['name']} já está em execução."

            script_path = os.path.join(self.app_dir, svc["script"])
            self.add_log(service_key, f"[START] Iniciando {svc['name']} em segundo plano...")

            try:
                env = os.environ.copy()
                env["PYTHONUNBUFFERED"] = "1"

                startupinfo = None
                if sys.platform == "win32":
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

                proc = subprocess.Popen(
                    [sys.executable, "-u", script_path],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    cwd=self.app_dir,
                    env=env,
                    startupinfo=startupinfo
                )
                svc["process"] = proc

                t = threading.Thread(target=self._read_output, args=(service_key, proc), daemon=True)
                svc["thread"] = t
                t.start()

                self.add_log(service_key, f"[OK] {svc['name']} ativo com PID {proc.pid}.")
                return True, f"{svc['name']} iniciado."
            except Exception as e:
                msg = f"Falha ao iniciar {svc['name']}: {e}"
                self.add_log(service_key, f"[ERROR] {msg}")
                return False, msg

    def stop_service(self, service_key):
        with self.lock:
            if service_key not in self.processes or service_key == "hub":
                return False, "Serviço inválido."

            svc = self.processes[service_key]
            proc = svc["process"]
            if proc is None or proc.poll() is not None:
                svc["process"] = None
                return True, f"{svc['name']} já está parado."

            self.add_log(service_key, f"[STOP] Parando {svc['name']} (PID {proc.pid})...")
            try:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                svc["process"] = None
                self.add_log(service_key, f"[STOPPED] {svc['name']} desligado com sucesso.")
                return True, f"{svc['name']} encerrado."
            except Exception as e:
                msg = f"Erro ao parar {svc['name']}: {e}"
                self.add_log(service_key, f"[ERROR] {msg}")
                return False, msg

    def restart_service(self, service_key):
        self.stop_service(service_key)
        time.sleep(0.5)
        return self.start_service(service_key)

    def start_all(self):
        r1, m1 = self.start_service("conflitos")
        r2, m2 = self.start_service("conferidor_manobras")
        return True, f"Iniciando serviços..."

    def stop_all(self):
        self.stop_service("conflitos")
        self.stop_service("conferidor_manobras")
        return True, "Todos os serviços parados."

    def restart_all(self):
        self.stop_all()
        time.sleep(0.5)
        return self.start_all()

    def get_status(self):
        snapshots = []
        with self.lock:
            for k, svc in self.processes.items():
                if k == "hub":
                    snapshots.append((k, svc["name"], svc["port"], True, os.getpid(), len(svc["logs"])))
                else:
                    proc = svc["process"]
                    is_proc_running = proc is not None and proc.poll() is None
                    pid = proc.pid if is_proc_running else None
                    snapshots.append((k, svc["name"], svc["port"], is_proc_running, pid, len(svc["logs"])))

        result = {}
        for k, name, port, is_proc_running, pid, log_count in snapshots:
            if k == "hub":
                is_alive = True
            else:
                is_alive = _is_server_alive(port) if is_proc_running else False

            result[k] = {
                "name": name,
                "port": port,
                "running": is_proc_running or is_alive,
                "pid": pid,
                "log_count": log_count
            }
        return result

    def get_logs(self, service_key, since_id=0):
        with self.lock:
            if service_key == "all":
                combined = []
                for k, svc in self.processes.items():
                    for entry in svc["logs"]:
                        if entry["id"] > since_id:
                            combined.append(entry)
                combined.sort(key=lambda x: x["id"])
                return combined
            
            if service_key in self.processes:
                return [e for e in self.processes[service_key]["logs"] if e["id"] > since_id]
            return []

    def clear_logs(self, service_key):
        with self.lock:
            if service_key == "all":
                for svc in self.processes.values():
                    svc["logs"].clear()
            elif service_key in self.processes:
                self.processes[service_key]["logs"].clear()
        return True

process_manager = ProcessManager(_app_dir())

class _ThreadedServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

class ProxyHandler(BaseHTTPRequestHandler):
    def _send_json(self, data, code=200):
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def _send_file(self, path, content_type):
        try:
            with open(path, "rb") as f:
                data = f.read()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.end_headers()
            self.wfile.write(data)
        except:
            self.send_response(HTTPStatus.NOT_FOUND)
            self.end_headers()

    def _proxy_request(self, target_url):
        length = int(self.headers.get("Content-Length") or "0")
        body = self.rfile.read(length) if length > 0 else None
        
        req = urllib.request.Request(target_url, data=body, method=self.command)
        for h in ["Content-Type", "Accept", "User-Agent"]:
            if h in self.headers:
                req.add_header(h, self.headers[h])
        
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                self.send_response(resp.status)
                for k, v in resp.getheaders():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(resp.read())
        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            self.end_headers()
            self.wfile.write(e.read())
        except Exception as e:
            print(f"[ERRO PROXY] Falha ao encaminhar requisição para {target_url}: {e}")
            self.send_response(503)
            self.end_headers()
            self.wfile.write(f"Erro no Proxy: {e}".encode())

    def do_GET(self):
        u = urlparse(self.path)
        qs = parse_qs(u.query)

        # UI e Assets
        if u.path == "/health":
            return self._send_json({"status": "ok", "service": "hub"})

        if u.path == "/":
            ui_path = os.path.join(os.path.dirname(__file__), "templates", "index.html")
            return self._send_file(ui_path, "text/html; charset=utf-8")
        
        if u.path.startswith("/assets/"):
            name = u.path.split("/")[-1]
            ext = name.split(".")[-1].lower()
            ct = "image/x-icon" if ext == "ico" else "image/png"
            path = os.path.join(_app_dir(), "assets", name)
            return self._send_file(path, ct)

        # Arquivos Estáticos (CSS/JS)
        if u.path.startswith("/static/"):
            rel_path = u.path[len("/static/"):]
            path = os.path.join(os.path.dirname(__file__), "static", rel_path.replace("/", os.sep))
            ext = path.split(".")[-1].lower()
            ct = "text/plain"
            if ext == "css": ct = "text/css"
            elif ext == "js": ct = "application/javascript"
            return self._send_file(path, ct)

        # API Terminal & Processos (Internal Hub)
        if u.path == "/hub/auth/check":
            auth = is_admin_authenticated(self.headers)
            return self._send_json({"authenticated": auth})

        if u.path == "/hub/status":
            return self._send_json(process_manager.get_status())

        if u.path == "/hub/terminal/logs":
            if not is_admin_authenticated(self.headers):
                return self._send_json({"error": "Unauthorized", "message": "Acesso restrito ao administrador"}, code=HTTPStatus.UNAUTHORIZED)
            service = qs.get("service", ["all"])[0]
            since_id = int(qs.get("since", [0])[0])
            logs = process_manager.get_logs(service, since_id)
            return self._send_json({"service": service, "logs": logs})

        # Roteamento Conflitos
        if u.path.startswith("/conflitos/"):
            sub_path = u.path[len("/conflitos"):]
            target = f"http://127.0.0.1:{PORT_CONFLITOS}{sub_path}"
            if u.query: target += f"?{u.query}"
            return self._proxy_request(target)

        # Roteamento Conferidor
        if u.path.startswith("/conferidor_manobras/"):
            sub_path = u.path[len("/conferidor_manobras"):]
            target = f"http://127.0.0.1:{PORT_CONFERIDOR}{sub_path}"
            if u.query: target += f"?{u.query}"
            return self._proxy_request(target)

        self.send_response(HTTPStatus.NOT_FOUND)
        self.end_headers()

    def do_POST(self):
        u = urlparse(self.path)

        # Autenticação de Administrador
        if u.path == "/hub/auth/login":
            length = int(self.headers.get("Content-Length") or "0")
            body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
            try:
                data = json.loads(body)
            except Exception:
                data = {}
            pwd = data.get("password", "")
            if pwd == get_admin_password():
                token = str(uuid.uuid4())
                ACTIVE_ADMIN_TOKENS.add(token)
                return self._send_json({"success": True, "token": token, "message": "Autenticado com sucesso"})
            else:
                return self._send_json({"success": False, "message": "Senha incorreta"}, code=HTTPStatus.UNAUTHORIZED)

        # Proteção de endpoints de controle de terminal
        if u.path.startswith("/hub/terminal/") or u.path.startswith("/hub/restart_"):
            if not is_admin_authenticated(self.headers):
                return self._send_json({"error": "Unauthorized", "message": "Acesso restrito ao administrador"}, code=HTTPStatus.UNAUTHORIZED)

        # APIs de Controle do Terminal
        if u.path == "/hub/terminal/action":
            length = int(self.headers.get("Content-Length") or "0")
            body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
            try:
                data = json.loads(body)
            except:
                data = {}

            action = data.get("action")
            service = data.get("service")

            if action == "start":
                ok, msg = process_manager.start_service(service)
            elif action == "stop":
                ok, msg = process_manager.stop_service(service)
            elif action == "restart":
                ok, msg = process_manager.restart_service(service)
            elif action == "start_all":
                ok, msg = process_manager.start_all()
            elif action == "stop_all":
                ok, msg = process_manager.stop_all()
            elif action == "restart_all":
                ok, msg = process_manager.restart_all()
            else:
                ok, msg = False, "Ação desconhecida"

            return self._send_json({"success": ok, "message": msg, "status": process_manager.get_status()})

        if u.path == "/hub/terminal/clear":
            length = int(self.headers.get("Content-Length") or "0")
            body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
            try:
                data = json.loads(body)
            except:
                data = {}

            service = data.get("service", "all")
            process_manager.clear_logs(service)
            return self._send_json({"success": True, "service": service})

        # Rotas Legacy de Restart
        if u.path == "/hub/restart_conflitos":
            process_manager.restart_service("conflitos")
            return self._send_json({"status": "starting"})

        if u.path == "/hub/restart_conferidor":
            process_manager.restart_service("conferidor_manobras")
            return self._send_json({"status": "starting"})

        # Roteamento Conflitos
        if u.path.startswith("/conflitos/"):
            sub_path = u.path[len("/conflitos"):]
            return self._proxy_request(f"http://127.0.0.1:{PORT_CONFLITOS}{sub_path}")

        # Roteamento Conferidor
        if u.path.startswith("/conferidor_manobras/"):
            sub_path = u.path[len("/conferidor_manobras"):]
            return self._proxy_request(f"http://127.0.0.1:{PORT_CONFERIDOR}{sub_path}")

        self.send_response(HTTPStatus.NOT_FOUND)
        self.end_headers()

def main():
    print("="*60)
    print("   HUB CENTRAL DE MANOBRAS GDIS (Porta 8765)")
    print("="*60)
    
    # Inicia os backends silenciosamente via ProcessManager
    process_manager.start_service("conflitos")
    process_manager.start_service("conferidor_manobras")
    
    print(f"\nPlataforma unificada pronta em http://localhost:{PORT_HUB}")
    print("Servidores iniciados em segundo plano. Terminais disponíveis na interface Web.")
    
    def _open_browser():
        url = f"http://127.0.0.1:{PORT_HUB}"
        print(f"\n[INFO] Tentando abrir o navegador em {url}...")
        try:
            if not webbrowser.open(url):
                raise Exception("webbrowser.open retornou False")
        except Exception as e:
            print(f"[AVISO] Falha ao abrir via Python ({e}). Tentando comando de sistema...")
            try:
                os.system(f'start "" "{url}"')
            except:
                print("[ERRO] Não foi possível abrir o navegador automaticamente.")
                print(f"       Por favor, acesse manualmente: {url}")

    threading.Timer(2.0, _open_browser).start()
    
    try:
        server = _ThreadedServer(("0.0.0.0", PORT_HUB), ProxyHandler)
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDesligando Hub...")
        process_manager.stop_all()
    except Exception as e:
        print(f"Erro no Hub: {e}")
        input("Pressione Enter para sair...")

if __name__ == "__main__":
    main()

