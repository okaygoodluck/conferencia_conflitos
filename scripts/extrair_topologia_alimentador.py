"""
Script Utilitário: Extração e Inspeção de Topologia Dinâmica GDIS
Obtém o JSON bruto retornado pelo serviço getRedeAlimentador (GDIS Apoio)
para análise de conectividade, nós, trechos e modelagem de grafo elétrico.
"""

import argparse
import getpass
import json
import os
import re
import sys
import time

from playwright.sync_api import sync_playwright

# Garante acesso aos módulos do projeto
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

URL_LOGIN_PM = "http://gdis-pm/gdispm/"
URL_LOGIN_APOIO = "http://gdis-apoio/gdisweb/login.jsf"
URL_REDE_SERVICE = os.environ.get(
    "GDIS_REDE_URL",
    "http://gdis-apoio:80/gdis-do-web/services/getRedeAlimentador"
)

def formatar_alimentador(alim: str) -> list:
    """Gera variações de formato comuns para o alimentador (ex: PTHD217, PTHD 217, PTHD-217)"""
    cod = str(alim).strip().upper()
    candidatos = [cod]
    m = re.match(r'^([A-Z]{3,4})[\s\-_/]*(\d{1,4})$', cod)
    if m:
        subes = m.group(1)
        num_str = m.group(2)
        num_int = int(num_str)
        candidatos.extend([
            f"{subes} {num_str}",
            f"{subes}{num_str}",
            f"{subes}-{num_str}",
            f"{subes} {num_int:02d}",
            f"{subes}{num_int:02d}",
            f"{subes} {num_int:03d}",
            f"{subes}{num_int:03d}",
            f"{subes} {num_int}",
            f"{subes}{num_int}"
        ])
    elif ' ' in cod:
        candidatos.append(cod.replace(' ', ''))
    
    # Deduplica preservando ordem
    vistos = set()
    return [c for c in candidatos if not (c in vistos or vistos.add(c))]

def extrair_topologia(alim: str, usuario: str = "", senha: str = "", headless: bool = False):
    if not alim:
        print("❌ Código do alimentador não informado.")
        return

    usuario = usuario or os.getenv("GDIS_USUARIO") or input("Usuário GDIS: ").strip()
    senha = senha or os.getenv("GDIS_SENHA") or getpass.getpass("Senha GDIS: ")

    candidatos_alim = formatar_alimentador(alim)
    print(f"\n🔍 Alimentador alvo: '{alim}' (formatos a testar: {candidatos_alim})")
    print(f"🚀 Iniciando navegador (headless={headless})...")

    with sync_playwright() as p:
        browser_args = [
            "--disable-dev-shm-usage", 
            "--no-sandbox", 
            "--disable-gpu", 
            "--mute-audio"
        ]
        try:
            browser = p.chromium.launch(channel="msedge", headless=headless, args=browser_args)
        except Exception:  # noqa: BLE001  # noqa: BLE001
            browser = p.chromium.launch(headless=headless, args=browser_args)

        context = browser.new_context(viewport={'width': 1280, 'height': 800})
        page = context.new_page()

        try:
            # 1. Login no GDIS PM
            print("🔑 [1/3] Efetuando login no GDIS PM...")
            page.goto(URL_LOGIN_PM, timeout=30000)
            if page.locator("input[id='formLogin:userid']").count() > 0:
                page.fill("input[id='formLogin:userid']", usuario)
                page.fill("input[id='formLogin:password']", senha)
                page.click("input[id='formLogin:botao']")
                page.wait_for_selector("input[id='formLogin:userid']", state="detached", timeout=15000)
                print("   ✅ Login GDIS PM realizado com sucesso.")

            # 2. Login no GDIS Apoio (necessário para sessão do getRedeAlimentador)
            print("🔑 [2/3] Autenticando sessão no GDIS Apoio...")
            page_apoio = context.new_page()
            try:
                page_apoio.goto(URL_LOGIN_APOIO, timeout=20000)
                if page_apoio.locator("input[id='form_login:login_username']").count() > 0:
                    page_apoio.fill("input[id='form_login:login_username']", usuario)
                    page_apoio.fill("input[id='form_login:login_pwd']", senha)
                    page_apoio.click("input[id='form_login:login_ok']")
                    page_apoio.wait_for_load_state("domcontentloaded", timeout=10000)
                    print("   ✅ Sessão GDIS Apoio ativa.")
            except Exception as e_ap:  # noqa: BLE001
                print(f"   ⚠️ Aviso ao autenticar no GDIS Apoio: {e_ap}")
            finally:
                page_apoio.close()

            # Captura sessionId dos cookies
            jsessionid = None
            cookie_header_parts = []
            for cookie in context.cookies():
                c_name = cookie.get("name", "")
                c_val = cookie.get("value", "")
                c_domain = str(cookie.get("domain", "")).lower()
                cookie_header_parts.append(f"{c_name}={c_val}")
                if "JSESSIONID" in c_name.upper() and ("apoio" in c_domain or not jsessionid):
                    jsessionid = c_val

            # 3. Consulta ao serviço getRedeAlimentador
            print("📡 [3/3] Consultando API getRedeAlimentador...")
            dados_json = None

            for cand in candidatos_alim:
                payload = {
                    "alim": cand,
                    "ambiente": "operacao",
                    "userName": usuario,
                    "salt": str(int(time.time() * 1000))
                }
                params = {"sessionId": jsessionid} if jsessionid else {}
                headers = {"User-Agent": "Jakarta Commons-HttpClient/3.1"}

                print(f"   ➔ Testando formato: '{cand}'...")
                try:
                    resp = context.request.post(
                        URL_REDE_SERVICE,
                        params=params,
                        headers=headers,
                        form=payload,
                        timeout=30000
                    )
                    if resp.status == 200:
                        txt_resp = resp.text()
                        if "cookiecheck" not in txt_resp:
                            cand_data = resp.json()
                            if isinstance(cand_data, dict) and cand_data.get("nos"):
                                dados_json = cand_data
                                print(f"   ✅ Sucesso no formato '{cand}'!")
                                break
                    elif resp.status == 204:
                        print(f"   ℹ️ Alimentador '{cand}' sem rede cadastrada (HTTP 204).")
                    else:
                        print(f"   ⚠️ HTTP {resp.status} para '{cand}'.")
                except Exception as e_req:  # noqa: BLE001
                    print(f"   ❌ Erro na requisição para '{cand}': {e_req}")

            if not dados_json:
                print("\n❌ Não foi possível obter a topologia para este alimentador.")
                return

            # 4. Salva o JSON bruto em temp/
            os.makedirs(os.path.join(base_dir, "temp"), exist_ok=True)
            arquivo_saida = os.path.join(base_dir, "temp", f"topologia_{alim.replace(' ', '_')}.json")
            with open(arquivo_saida, "w", encoding="utf-8") as f_out:
                json.dump(dados_json, f_out, ensure_ascii=False, indent=2)

            print("\n" + "="*80)
            print("🎉 TOPOLOGIA EXTRAÍDA COM SUCESSO!")
            print(f"📁 Arquivo salvo em: {arquivo_saida}")
            print("="*80)

            # 5. Análise estrutural rápida das chaves e campos
            print("\n📊 DIAGNÓSTICO ESTRUTURAL DO JSON:")
            print(f"   • Chaves de primeiro nível: {list(dados_json.keys())}")
            
            nos = dados_json.get("nos", [])
            print(f"   • Total de nós/elementos na lista 'nos': {len(nos)}")

            # Procura outras coleções no JSON (ex: trechos, ligações, ramos)
            for k, v in dados_json.items():
                if k != "nos" and isinstance(v, list):
                    print(f"   • Coleção identificada: '{k}' com {len(v)} itens")
                elif k != "nos" and isinstance(v, dict):
                    print(f"   • Objeto identificado: '{k}' com chaves {list(v.keys())}")

            if nos:
                primeiro_no = nos[0]
                print("\n🏷️  CAMPOS DISPONÍVEIS EM CADA NÓ (Exemplo com nó 1):")
                chaves_ordenadas = sorted(primeiro_no.keys())
                for i in range(0, len(chaves_ordenadas), 4):
                    print("     " + ", ".join(f"'{k}'" for k in chaves_ordenadas[i:i+4]))

                # Varredura de possíveis campos de conectividade topológica
                chaves_conectividade = [
                    k for k in primeiro_no if any(
                        p in k.lower() for p in [
                            "no", "pai", "de", "para", "conect", "montante", "jusante", 
                            "adj", "ramo", "trecho", "barra", "vizinho", "origem", "destino"
                        ]
                    )
                ]
                print(f"\n🔗 Possíveis campos de conectividade identificados: {chaves_conectividade}")

                # Exemplo dos 2 primeiros nós completos para inspeção direta
                print("\n🔍 AMOSTRA DOS PRIMEIROS 2 NÓS:")
                for idx, n in enumerate(nos[:2]):
                    print(f"--- Nó {idx+1} ({n.get('numeq', 'S/N')} - {n.get('r_tipoeq', n.get('tipono', ''))}) ---")
                    for k, val in sorted(n.items()):
                        if val not in [None, "", "-"]:
                            print(f"     {k}: {val}")

        finally:
            context.close()
            browser.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extrai a topologia bruta de um alimentador do GDIS Apoio.")
    parser.add_argument("alimentador", nargs="?", default="", help="Código do alimentador (ex: PTHD217, PRRU009)")
    parser.add_argument("--usuario", default="", help="Usuário de rede GDIS")
    parser.add_argument("--senha", default="", help="Senha de rede GDIS")
    parser.add_argument("--headless", action="store_true", help="Executa o browser em segundo plano (sem janela)")
    args = parser.parse_args()

    alim_alvo = args.alimentador or input("Digite o alimentador para extrair a topologia (ex: PTHD217): ").strip()
    extrair_topologia(alim_alvo, args.usuario, args.senha, args.headless)
