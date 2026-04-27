import os
import sys
import getpass
import time
import urllib.request
from http.cookiejar import CookieJar

# Adiciona o diretório atual ao sys.path para encontrar o pacote 'src'
sys.path.append(os.getcwd())

from src.integration.gdis_http_extrator import _login, coletar_solicitacoes, extrair_uma_solicitacao

def test_coleta_isolada():
    print("====================================================")
    print("      TESTE ISOLADO: COLETA DE SOLICITAÇÕES         ")
    print("====================================================")
    
    usuario = (os.getenv("GDIS_USUARIO") or "").strip() or input("Usuário: ").strip()
    senha = (os.getenv("GDIS_SENHA") or "").strip() or getpass.getpass("Senha: ")

    jar = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    try:
        print(f"\n[{time.strftime('%H:%M:%S')}] Fazendo login...")
        jsessionid, vs = _login(opener, usuario, senha)
        print(f"Login OK! JSESSIONID: {jsessionid}")
        
        # Parâmetros de Teste
        situacao = "EA" # Autorizadas/Aprovadas
        d_ini = input("Data Início (dd/mm/aaaa) [Padrão: 20/04/2026]: ").strip() or "20/04/2026"
        d_fim = input("Data Fim    (dd/mm/aaaa) [Padrão: 23/04/2026]: ").strip() or "23/04/2026"
        
        print(f"\n[{time.strftime('%H:%M:%S')}] Iniciando coleta de solicitações ({situacao}) entre {d_ini} e {d_fim}...")
        solicitacoes, vs = coletar_solicitacoes(opener, jsessionid, vs, situacao, d_ini, d_fim)
        
        print(f"\n✅ RESULTADO DA COLETA:")
        print(f"Total de solicitações encontradas: {len(solicitacoes)}")
        if solicitacoes:
            print(f"Lista: {', '.join(solicitacoes[:10])}{' ...' if len(solicitacoes) > 10 else ''}")
            
            quer_extrair = input("\nDeseja testar a extração detalhada da primeira solicitação? (s/n): ").lower()
            if quer_extrair == 's':
                numero = solicitacoes[0]
                print(f"\n[{time.strftime('%H:%M:%S')}] Extraindo detalhes da Solicitação {numero}...")
                eq, al, vs, ini, fim = extrair_uma_solicitacao(opener, jsessionid, vs, numero)
                
                print(f"--- DADOS EXTRAÍDOS ---")
                print(f"Período: {ini} a {fim}")
                print(f"Equipamentos: {', '.join(eq) if eq else 'Nenhum'}")
                print(f"Alimentadores: {', '.join(al) if al else 'Nenhum'}")
        
    except Exception as e:
        print(f"\n❌ ERRO DURANTE O TESTE: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_coleta_isolada()
