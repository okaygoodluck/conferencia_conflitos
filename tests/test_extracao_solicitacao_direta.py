import os
import sys
import getpass
import time
import urllib.request
from http.cookiejar import CookieJar

# Adiciona o diretório atual ao sys.path para encontrar o pacote 'src'
sys.path.append(os.getcwd())

from src.integration.gdis_http_extrator import _login, extrair_uma_solicitacao

def test_extracao_direta():
    print("====================================================")
    print("      TESTE ISOLADO: EXTRAÇÃO DE SOLICITAÇÃO        ")
    print("====================================================")
    
    usuario = (os.getenv("GDIS_USUARIO") or "").strip() or input("Usuário: ").strip()
    senha = (os.getenv("GDIS_SENHA") or "").strip() or getpass.getpass("Senha: ")

    jar = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    try:
        print(f"\n[{time.strftime('%H:%M:%S')}] Fazendo login...")
        jsessionid, vs = _login(opener, usuario, senha)
        print(f"Login OK!")
        
        numero = input("\nDigite o número da Solicitação que deseja testar: ").strip()
        if not numero:
             print("Número não informado.")
             return

        print(f"\n[{time.strftime('%H:%M:%S')}] Iniciando extração detalhada da Solicitação {numero}...")
        eq, al, vs, ini, fim = extrair_uma_solicitacao(opener, jsessionid, vs, numero, usuario=usuario, senha=senha)
        
        print(f"\n✅ RESULTADO DA EXTRAÇÃO:")
        print(f"Período Extraído: {ini} a {fim}")
        print(f"Equipamentos ({len(eq)}): {', '.join(eq) if eq else 'Nenhum'}")
        print(f"Alimentadores ({len(al)}): {', '.join(al) if al else 'Nenhum'}")
        
        if not eq and not ini:
            print("\n⚠️ AVISO: Não foram encontrados dados. Verifique os logs de debug no terminal.")
        else:
            print("\n🚀 Sucesso! Os dados foram capturados corretamente.")
            
    except Exception as e:
        print(f"\n❌ ERRO DURANTE O TESTE: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_extracao_direta()
