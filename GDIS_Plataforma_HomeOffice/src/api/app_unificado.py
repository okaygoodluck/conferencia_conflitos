import json
import os
import subprocess
import sys
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from urllib.parse import urlparse
import urllib.request
import urllib.error

# Configuração
PORT_HUB = 8765
PORT_CONFLITOS = 8766
PORT_CONFERIDOR = 8767

def _app_dir():
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def _is_server_alive(port):
    try:
        with urllib.request.urlopen(f"http://localhost:{port}/health", timeout=1) as resp:
            return resp.status == 200
    except:
        return False

def _start_backend(name, script_name, port):
    if _is_server_alive(port):
        print(f"Backend {name} já está rodando na porta {port}.")
        return

    script_path = os.path.join(os.path.dirname(__file__), script_name)
    print(f"Iniciando {name} ({script_name})...")
    
    # Windows: Abre nova janela de terminal
    # Flags: creationflags=subprocess.CREATE_NEW_CONSOLE (0x00000010)
    try:
        subprocess.Popen(
            [sys.executable, script_path],
            creationflags=0x00000010,
            cwd=_app_dir()
        )
    except Exception as e:
        print(f"Falha ao iniciar {name}: {e}")

class _ThreadedServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

class ProxyHandler(BaseHTTPRequestHandler):
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
        # Copia headers relevantes
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
            self.send_response(503)
            self.end_headers()
            self.wfile.write(f"Erro no Proxy: {e}".encode())

    def do_GET(self):
        u = urlparse(self.path)
        
        # UI e Assets
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

        # Roteamento Conflitos
        if u.path.startswith("/conflitos/"):
            sub_path = u.path[len("/conflitos"):]
            target = f"http://localhost:{PORT_CONFLITOS}{sub_path}"
            if u.query: target += f"?{u.query}"
            return self._proxy_request(target)

        # Roteamento Conferidor
        if u.path.startswith("/conferidor_manobras/"):
            sub_path = u.path[len("/conferidor_manobras"):]
            target = f"http://localhost:{PORT_CONFERIDOR}{sub_path}"
            if u.query: target += f"?{u.query}"
            return self._proxy_request(target)
            
        # Status do Hub (Internal)
        if u.path == "/hub/status":
            info = {
                "conflitos": "online" if _is_server_alive(PORT_CONFLITOS) else "offline",
                "conferidor_manobras": "online" if _is_server_alive(PORT_CONFERIDOR) else "offline"
            }
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(info).encode())
            return

        self.send_response(HTTPStatus.NOT_FOUND)
        self.end_headers()

    def do_POST(self):
        u = urlparse(self.path)
        
        # Roteamento Conflitos
        if u.path.startswith("/conflitos/"):
            sub_path = u.path[len("/conflitos"):]
            return self._proxy_request(f"http://localhost:{PORT_CONFLITOS}{sub_path}")

        # Roteamento Conferidor
        if u.path.startswith("/conferidor_manobras/"):
            sub_path = u.path[len("/conferidor_manobras"):]
            return self._proxy_request(f"http://localhost:{PORT_CONFERIDOR}{sub_path}")

        # Restart Commands
        if u.path == "/hub/restart_conflitos":
            _start_backend("Conflitos", "server_conflitos.py", PORT_CONFLITOS)
            self.send_response(200); self.end_headers(); self.wfile.write(b'{"status":"starting"}')
            return
        if u.path == "/hub/restart_conferidor":
            _start_backend("Conferidor", "server_conferidor_manobras.py", PORT_CONFERIDOR)
            self.send_response(200); self.end_headers(); self.wfile.write(b'{"status":"starting"}')
            return

        self.send_response(HTTPStatus.NOT_FOUND)
        self.end_headers()

def main():
    print("="*60)
    print("   HUB CENTRAL DE MANOBRAS GDIS (Porta 8765)")
    print("="*60)
    
    # Inicia backends
    _start_backend("Verificador de Conflitos", "server_conflitos.py", PORT_CONFLITOS)
    _start_backend("Conferidor de Manobras", "server_conferidor_manobras.py", PORT_CONFERIDOR)
    
    print(f"\nPlataforma unificada pronta em http://localhost:{PORT_HUB}")
    print("Mantenha esta janela aberta. Ela gerencia a comunicação e as outras janelas.")
    
    try:
        server = _ThreadedServer(("0.0.0.0", PORT_HUB), ProxyHandler)
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDesligando Hub...")
    except Exception as e:
        print(f"Erro no Hub: {e}")
        input("Pressione Enter para sair...")

if __name__ == "__main__":
    main()
