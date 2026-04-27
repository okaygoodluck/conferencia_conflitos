import os
import re
import getpass
from playwright.sync_api import sync_playwright

URL_LOGIN = "http://gdis-pm/gdispm/"

def main():
    print("=====================================================")
    print("  EXPLORADOR DE SOLICITAÇÕES (Fase de Descoberta)    ")
    print("=====================================================")
    print("Este script vai entrar na Manobra, achar a Solicitação,")
    print("abrir a Solicitação e extrair todos os textos e tabelas.")
    print("-----------------------------------------------------")

    manobra_num = input("Digite o número da Manobra Base: ").strip()
    if not manobra_num:
        print("Número inválido.")
        return

    usuario = (os.getenv("GDIS_USUARIO") or "").strip() or input("Usuário: ").strip()
    senha = (os.getenv("GDIS_SENHA") or "").strip() or getpass.getpass("Senha: ")

    print("\n[1] Iniciando navegador (visível para acompanhamento)...")
    with sync_playwright() as p:
        caminhos = [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        ]
        executavel = next((c for c in caminhos if os.path.exists(c)), None)
        
        browser = p.chromium.launch(executable_path=executavel, headless=False)
        context = browser.new_context(viewport={'width': 1280, 'height': 800})
        page = context.new_page()

        print("    Fazendo login...")
        page.goto(URL_LOGIN)
        if page.locator("input[id='formLogin:userid']").count() > 0:
            page.fill("input[id='formLogin:userid']", usuario)
            page.fill("input[id='formLogin:password']", senha)
            page.click("input[id='formLogin:botao']")
            page.wait_for_selector("input[id='formLogin:userid']", state="detached")

        print("\n[2] Navegando para Consultas -> Manobra...")
        page.click("text=Consultas")
        page.click("text=Manobra")
        page.wait_for_selector("input[id='formPesquisa:numeroManobra']", timeout=20000)

        print(f"    Pesquisando Manobra {manobra_num}...")
        page.fill("input[id='formPesquisa:numeroManobra']", manobra_num)
        
        # Limpa os campos de data para não atrapalhar
        page.evaluate("""() => {
            const dIni = document.getElementById('formPesquisa:dataInicioInputDate');
            const dFim = document.getElementById('formPesquisa:dataTerminioInputDate') || document.getElementById('formPesquisa:dataTerminoInputDate');
            if (dIni) dIni.value = '';
            if (dFim) dFim.value = '';
        }""")

        page.click("input[id='formPesquisa:j_id109']") # Botão pesquisar
        page.wait_for_selector("table[id*='resulPesManobra']", timeout=15000)
        page.wait_for_timeout(1000)

        print("    Buscando número da Solicitação...")
        # Primeiro tenta achar na tabela de resultados de pesquisa de Manobra
        solicitacao_num = page.evaluate(f"""(manobra) => {{
            const tabela = document.querySelector("table[id*='resulPesManobra']");
            if (!tabela) return null;
            const thead = tabela.querySelector('thead');
            if (!thead) return null;
            const headers = Array.from(thead.querySelectorAll('th')).map(th => (th.innerText || '').toLowerCase());
            const idxM = headers.findIndex(h => h.includes('manobra'));
            const idxS = headers.findIndex(h => h.includes('solicita') || h.includes('vinc'));
            if (idxM < 0 || idxS < 0) return null;
            const rows = Array.from(tabela.querySelectorAll('tbody tr'));
            for (const r of rows) {{
                const tds = r.querySelectorAll('td');
                if (tds.length > Math.max(idxM, idxS)) {{
                    const mVal = (tds[idxM].innerText || '').replace(/\\D/g, '');
                    if (mVal === String(manobra)) {{
                        const sVal = (tds[idxS].innerText || '').replace(/\\D/g, '');
                        if (sVal) return sVal;
                    }}
                }}
            }}
            return null;
        }}""", manobra_num)

        if not solicitacao_num:
            print("    [ERRO] Não achei o número da Solicitação na tabela. Verifique no navegador se ele apareceu.")
            solicitacao_num = input("    Digite o número da Solicitação manualmente para continuarmos: ").strip()
            if not solicitacao_num:
                return
        else:
            print(f"    ✅ Solicitação vinculada encontrada: {solicitacao_num}")

        print("\n[3] Navegando para Consultas -> Solicitação...")
        page.click("text=Consultas", force=True)
        page.wait_for_timeout(1000)
        try:
            page.click("text=/^\\s*Solicita[cç][aã]o\\s*$/i", timeout=5000)
        except:
            try:
                page.click("text=/Solicita[cç][aã]o de Manobra/i", timeout=5000)
            except:
                print("    [AVISO] Não consegui clicar no menu de Solicitação.")
                input("    Abra a tela de pesquisa de Solicitação manualmente e pressione Enter...")

        page.wait_for_timeout(3000)
        
        print(f"\n[4] Abrindo a Solicitação {solicitacao_num}...")
        # Preenche o input genérico que contenha "solicitacao" e "numero"
        page.evaluate(f"""(num) => {{
            const inputs = Array.from(document.querySelectorAll('input[type="text"]'));
            const target = inputs.find(i => ((i.id || '') + (i.name || '')).toLowerCase().includes('solicitacao'));
            if (target) target.value = num;
        }}""", solicitacao_num)

        page.evaluate("""() => {
            const btns = Array.from(document.querySelectorAll('input[type="button"], input[type="submit"], button'));
            const btn = btns.find(b => (b.value || b.innerText || '').toLowerCase().includes('pesquisar'));
            if (btn) btn.click();
        }""")
        page.wait_for_timeout(4000)

        page.evaluate(f"""(num) => {{
            const links = Array.from(document.querySelectorAll('a'));
            const link = links.find(l => (l.innerText || '').includes(num));
            if (link) link.click();
        }}""", solicitacao_num)
        page.wait_for_timeout(4000)

        print("\n[5] Extraindo dados da tela da Solicitação...")
        # Expande todos os painéis
        page.evaluate("""() => {
            document.querySelectorAll('.rich-stglpanel-header').forEach(h => {
                const body = document.getElementById(h.id.replace('_header', '_body'));
                if (body && (body.style.display === 'none' || body.style.display === '')) { h.click(); }
            });
        }""")
        
        # Espera 6 segundos para dar tempo do AJAX do JSF carregar as tabelas dentro dos painéis
        print("    Aguardando o carregamento dos painéis (Serviços, Locais, etc)...")
        page.wait_for_timeout(6000)

        texto_puro = page.evaluate("() => document.body.innerText")
        
        # Extrai todas as tabelas e formata as colunas com ' | ' para fácil visualização
        tabelas_texto = page.evaluate("""() => {
            let output = "";
            const tables = document.querySelectorAll('table');
            tables.forEach((t, i) => {
                const rows = Array.from(t.querySelectorAll('tr'));
                if (rows.length < 2) return; // Ignora tabelas de layout do JSF
                
                output += "=========================================\\n";
                output += "TABELA ENCONTRADA (ID: " + (t.id || 'sem-id') + ")\\n";
                output += "=========================================\\n";
                
                rows.forEach(r => {
                    const cells = Array.from(r.querySelectorAll('th, td')).map(c => c.innerText.trim().replace(/\\s+/g, ' '));
                    if (cells.join('').length > 0) {
                        output += cells.join(' | ') + "\\n";
                    }
                });
                output += "\\n";
            });
            return output;
        }""")
        
        filename = f"dump_solicitacao_{solicitacao_num}.txt"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(f"=== MANOBRA: {manobra_num} | SOLICITACAO: {solicitacao_num} ===\n\n")
            f.write("--- DUMP DAS TABELAS (Serviços, Locais, Eventos, etc) ---\n")
            f.write(tabelas_texto)
            f.write("\n\n--- DUMP TEXTO GERAL DA TELA ---\n")
            f.write(texto_puro)
            
        print(f"\n✅ [SUCESSO] Todos os textos da tela foram salvos no arquivo: {filename}")
        input("Pode fechar o navegador. Aperte Enter para encerrar...")

if __name__ == "__main__":
    main()