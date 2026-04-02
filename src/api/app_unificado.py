import http.server
import socketserver
import os
import json
import urllib.parse
import sys
import ctypes
import traceback
import signal
from datetime import datetime

from src.core import verificador_conflitos
from src.core import verificador_regras_solicitacao
import ssl
from src.api import gerar_certificado

# --- CONFIGURAÇÃO E ESTADO ---
ORIGINAL_STDOUT = sys.stdout

def _app_dir():
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

LOG_FILE = os.path.join(_app_dir(), "data", "atividades.log")

def _log_activity(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] {message}"
    
    # Print para o console (STDOUT original)
    if ORIGINAL_STDOUT:
        ORIGINAL_STDOUT.write(log_entry + "\n")
        ORIGINAL_STDOUT.flush()
    
    # Salva no arquivo de log (persistent)
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_entry + "\n")
    except Exception as e:
        if ORIGINAL_STDOUT:
            ORIGINAL_STDOUT.write(f"!!! Erro ao gravar log: {e}\n")

class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        # Override para usar nosso sistema de log unificado
        _log_activity(f"REQ: {self.address_string()} - {format % args}")

    def do_GET(self):
        # Serve arquivos da pasta temp (onde está o index_unificado.html)
        if self.path == '/' or self.path == '':
            self.path = '/temp/index_unificado.html'
        
        # Redireciona assets se necessário (caso o HTML aponte para caminhos relativos)
        return http.server.SimpleHTTPRequestHandler.do_GET(self)

    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        
        try:
            data = json.loads(post_data)
            action = data.get('action')
            user_id = data.get('user', 'Desconhecido')
            
            _log_activity(f"AÇÃO: {action} | USUÁRIO: {user_id}")

            if action == 'verificar_conflitos':
                # Captura parâmetros da análise manual
                equipamentos = data.get('equipamentos', '')
                alimentadores = data.get('alimentadores', '')
                
                # Se houver dados manuais, logar o tipo de busca
                if equipamentos or alimentadores:
                    _log_activity(f"DADOS: Busca por Equipamentos/Alimentadores")
                
                result = verificador_conflitos.run_verificacao(data)
                self._send_response(result)
                _log_activity(f"SUCESSO: Conflitos Analisados para {user_id}")

            elif action == 'verificar_regras':
                # A lógica das regras já está embutida no verificador_regras_solicitacao
                # que agora utiliza a estrutura de 'data' do app integrado
                result = verificador_regras_solicitacao.run_verificacao(data)
                self._send_response(result)
                _log_activity(f"SUCESSO: Regras Validadas para {user_id}")

            else:
                _log_activity(f"ERRO: Ação inválida '{action}'")
                self._send_response({"error": "Ação inválida"}, status=400)

        except Exception as e:
            err_msg = f"FALHA CRÍTICA: {str(e)}\n{traceback.format_exc()}"
            _log_activity(err_msg)
            self._send_response({"error": str(e)}, status=500)

    def _send_response(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))

class _ThreadedServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True

def main():
    host, port = "0.0.0.0", 8765
    base_dir = _app_dir()
    data_dir = os.path.join(base_dir, "data")
    os.makedirs(data_dir, exist_ok=True)
    
    cert_path = os.path.join(data_dir, "server.crt")
    key_path = os.path.join(data_dir, "server.key")
    
    # Gera certificado se não existir
    try:
        gerar_certificado.gerar_autoassinado(cert_path, key_path)
    except Exception as e:
        print(f"[ERRO] Falha ao gerar certificado SSL: {e}")
    
    # Verifica se a porta está em uso
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if s.connect_ex((host, port)) == 0:
            print(f"\n[ERRO] A porta {port} ja esta sendo usada por outro processo!")
            print("Finalizando execução...")
            pause_on_error()
            return

    print("\n" + "="*60)
    print("      PLATAFORMA INTEGRADA GDIS - SERVIDOR ATIVO")
    print("="*60)
    print(f"URL Local: https://127.0.0.1:{port}/")
    print(f"URL Rede:  https://[IP_DO_SERVIDOR]:{port}/")
    print("Pressione Ctrl+C para encerrar o servidor com segurança.")
    print("\n[AVISO] Por usar certificado autoassinado, o navegador exibirá")
    print("um alerta de segurança. Clique em 'Avançado' e 'Prosseguir'.")
    print("="*60 + "\n")

    try:
        httpd = _ThreadedServer((host, port), Handler)
        
        # Configura o SSL Context
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certfile=cert_path, keyfile=key_path)
        
        httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
        httpd.serve_forever()
    except Exception as e:
        if os.name == 'nt':
            whnd = ctypes.windll.kernel32.GetConsoleWindow()
            if whnd != 0:
                ctypes.windll.user32.ShowWindow(whnd, 1) # Garante que mostre erro no console
        print(f"Erro no servidor: {e}")
        pause_on_error()

def pause_on_error():
    if os.name == 'nt':
        print("\nPressione qualquer tecla para fechar...")
        os.system("pause >nul")

if __name__ == "__main__":
    _log_activity("--- INICIANDO SERVIDOR GDIS ---")
    
    # Configura sinal de saída
    def signal_handler(sig, frame):
        _log_activity("SERVIDOR ENCERRADO PELO USUÁRIO (Ctrl+C)")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    main()
