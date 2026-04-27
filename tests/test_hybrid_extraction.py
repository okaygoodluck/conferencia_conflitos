import os
import sys
import time
import urllib.request
from http.cookiejar import CookieJar

# Adiciona o diretório atual ao sys.path para encontrar o pacote 'src'
sys.path.append(os.getcwd())

from src.integration.gdis_http_extrator import _login, extrair_uma_solicitacao

def run_automated_test(numero):
    print("====================================================")
    print("      TESTE AUTOMATIZADO: EXTRAÇÃO HÍBRIDA          ")
    print("====================================================")
    
    usuario = os.getenv("GDIS_USUARIO")
    senha = os.getenv("GDIS_SENHA")
    
    if not usuario or not senha:
        print("❌ ERRO: Variáveis GDIS_USUARIO ou GDIS_SENHA não definidas.")
        return

    jar = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    try:
        print(f"[{time.strftime('%H:%M:%S')}] Fazendo login...")
        jsessionid, vs = _login(opener, usuario, senha)
        print(f"Login OK!")
        
        print(f"\n[{time.strftime('%H:%M:%S')}] Testando Solicitação: {numero}")
        eq, al, vs, ini, fim = extrair_uma_solicitacao(opener, jsessionid, vs, numero, use_browser_fallback=True)
        
        print(f"\n✅ RESULTADO DA EXTRAÇÃO:")
        print(f"Período Extraído: {ini} a {fim}")
        print(f"Equipamentos ({len(eq)}): {', '.join(eq) if eq else 'Nenhum'}")
        
        if not eq and not ini:
            print("\n❌ FALHA: Nenhum dado capturado nem pelo HTTP nem pelo Browser.")
            sys.exit(1)
        else:
            print("\n🚀 SUCESSO ABSOLUTO! A extração híbrida funcionou.")
            
    except Exception as e:
        print(f"\n❌ ERRO DURANTE O TESTE: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    num_test = "1620642" # Aquela que falhava
    if len(sys.argv) > 1:
        num_test = sys.argv[1]
    run_automated_test(num_test)
