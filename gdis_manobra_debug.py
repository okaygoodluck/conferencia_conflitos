import os
import re
import getpass

from playwright.sync_api import sync_playwright


URL_LOGIN = "http://gdis-pm/gdispm/"

SEL_LOGIN_USER = "input[id='formLogin:userid']"
SEL_LOGIN_PASS = "input[id='formLogin:password']"
SEL_LOGIN_BTN = "input[id='formLogin:botao']"

MANOBRA_BASE = "238227523"


def wait_ajax_idle(page, timeout=30000):
    try:
        page.wait_for_function(
            """() => {
                const modal = document.getElementById('statusModal');
                if (!modal) return true;
                const s = window.getComputedStyle(modal);
                return !s || s.display === 'none';
            }""",
            timeout=timeout,
        )
    except:
        pass


def goto_manobra(page):
    page.click("text=Consultas", force=True, timeout=20000)
    page.wait_for_timeout(200)
    page.click("text=Manobra", force=True, timeout=20000)
    wait_ajax_idle(page, timeout=30000)
    page.wait_for_selector("input[id='formPesquisa:numeroManobra']", timeout=25000, state="visible")


def ensure_consultar_manobras_panel(page):
    try:
        page.wait_for_function(
            """() => {
                const body = document.getElementById('formPesquisa:consultaManobras2_body');
                if (!body) return true;
                const s = window.getComputedStyle(body);
                return s && s.display !== 'none';
            }""",
            timeout=15000,
        )
    except:
        pass
    is_open = page.evaluate(
        """() => {
            const body = document.getElementById('formPesquisa:consultaManobras2_body');
            if (!body) return true;
            const s = window.getComputedStyle(body);
            return !!(s && s.display !== 'none');
        }"""
    )
    if not is_open:
        try:
            page.click("div[id='formPesquisa:consultaManobras2_header']", timeout=5000)
        except:
            pass
        wait_ajax_idle(page, timeout=30000)
        try:
            page.wait_for_function(
                """() => {
                    const body = document.getElementById('formPesquisa:consultaManobras2_body');
                    if (!body) return true;
                    const s = window.getComputedStyle(body);
                    return s && s.display !== 'none';
                }""",
                timeout=15000,
            )
        except:
            pass


def pesquisar_numero(page, numero):
    ensure_consultar_manobras_panel(page)
    page.fill("input[id='formPesquisa:numeroManobra']", numero)
    try:
        page.select_option("select[id='formPesquisa:situacao']", value="")
    except:
        pass
    page.click("input[id='formPesquisa:j_id109']")
    wait_ajax_idle(page, timeout=30000)
    page.wait_for_selector("table[id='formManobra:resulPesManobra']", timeout=25000)
    try:
        page.wait_for_function(
            """(num) => {
                const t = document.getElementById('formManobra:resulPesManobra');
                if (!t) return false;
                const txt = (t.textContent || '');
                return txt.includes(String(num));
            }""",
            numero,
            timeout=25000,
        )
    except:
        pass


def abrir_detalhe(page, numero):
    page.locator("table[id='formManobra:resulPesManobra'] a", has_text=numero).first.click(force=True)
    wait_ajax_idle(page, timeout=30000)
    page.wait_for_selector("input[id='j_id51:bttVoltar']", timeout=25000, state="visible")
    page.wait_for_selector("div[id*='etapasManobraSimplePanelId']", timeout=25000, state="attached")


def expandir_itens(page):
    page.evaluate(
        """() => {
            const root = document.querySelector("div[id*='etapasManobraSimplePanelId']");
            if (!root) return;
            const headers = Array.from(root.querySelectorAll("div[id$='itensManobraSimplePanelId_header']"));
            for (const h of headers) {
                const bodyId = h.id.replace('_header', '_body');
                const body = document.getElementById(bodyId);
                if (!body) continue;
                let hidden = false;
                try { hidden = (window.getComputedStyle(body).display === 'none'); } catch(e) {}
                if (hidden) {
                    try { h.click(); } catch(e) {}
                }
            }
        }"""
    )
    wait_ajax_idle(page, timeout=30000)


def dump_itens_tables(page, verbose=False):
    data = page.evaluate(
        """() => {
            const root = document.querySelector("div[id*='etapasManobraSimplePanelId']");
            const scope = root || document;
            const norm = (s) => (s || '').toLowerCase().replace(/\\s+/g, ' ').trim();
            const clean = (s) => (s || '').replace(/\\s+/g, ' ').trim();

            const tables = Array.from(scope.querySelectorAll("table[id$=':itensCadastrados']"));
            const out = [];

            for (const tabela of tables) {
                const ths = Array.from(tabela.querySelectorAll('thead tr:first-child th'));
                const headers = ths.map(th => clean(th.textContent || ''));
                const headersNorm = headers.map(norm);
                const idxEqpto = headersNorm.findIndex(h => h.includes('eqpto') || h.includes('trafo'));
                const idxAlim = headersNorm.findIndex(h => h.includes('alimen') || h.includes('subes'));

                const rows = Array.from(tabela.querySelectorAll('tbody > tr'));
                const lines = [];
                for (let i = 0; i < rows.length; i++) {
                    const tds = rows[i].querySelectorAll('td');
                    const eq = (idxEqpto >= 0 && tds.length > idxEqpto) ? clean(tds[idxEqpto].textContent || '') : '';
                    const al = (idxAlim >= 0 && tds.length > idxAlim) ? clean(tds[idxAlim].textContent || '') : '';
                    lines.push({ i: i + 1, eq, al });
                }

                out.push({
                    id: tabela.id || '',
                    headers,
                    idxEqpto,
                    idxAlim,
                    rowsCount: rows.length,
                    lines,
                });
            }

            return out;
        }"""
    )

    all_eq = set()
    all_al = set()

    if verbose:
        print(f"Tabelas itens encontradas: {len(data)}")
    for t in data:
        if verbose:
            print(f"Tabela: {t['id']}")
            print(f"  Headers: {' | '.join(t['headers'])}")
            print(f"  idxEqpto={t['idxEqpto']} idxAlim={t['idxAlim']} rows={t['rowsCount']}")
        for ln in t["lines"]:
            eq = (ln.get("eq") or "").strip()
            al = (ln.get("al") or "").strip()
            if eq and eq != "-" and eq != " - ":
                all_eq.add(eq)
            if al and al != "-" and al != " - ":
                all_al.add(al)
            if verbose and (eq or al):
                print(f"    linha {ln['i']}: Eqpto/Trafo='{eq or '-'}' | Alimen/Subes='{al or '-'}'")

    return sorted(all_eq), sorted(all_al)


def extract_from_eventos(page):
    txt = page.evaluate(
        """() => {
            const nodes = Array.from(document.querySelectorAll("[id*='eventosList']"));
            return nodes.map(n => (n.textContent || '').trim()).filter(Boolean).join("\\n");
        }"""
    ) or ""

    eq = set()
    al = set()

    for m in re.finditer(r"\b\d{5,7}\s*-\s*\d+\s*-\s*\d+\b", txt):
        eq.add(re.sub(r"\s*-\s*", " - ", m.group(0).strip()))

    for m in re.finditer(r"Subesta(?:ç|c)ão\s+([A-Z]{3,6}\d{0,3})", txt, flags=re.IGNORECASE):
        al.add(m.group(1).upper())

    for m in re.finditer(r"Alimentador\s+([A-Z]{3,6}\d{0,3})", txt, flags=re.IGNORECASE):
        al.add(m.group(1).upper())

    return sorted(eq), sorted(al)


def main():
    numero = (os.getenv("GDIS_MANOBRA") or MANOBRA_BASE).strip()
    headless = (os.getenv("GDIS_HEADLESS") or "").strip().lower() in {"1", "true", "yes", "y"}
    verbose = (os.getenv("GDIS_VERBOSE") or "").strip().lower() in {"1", "true", "yes", "y"}

    usuario = (os.getenv("GDIS_USUARIO") or "").strip() or input("Usuário: ").strip()
    senha = (os.getenv("GDIS_SENHA") or "").strip() or getpass.getpass("Senha: ")
    if not usuario or not senha:
        print("Credenciais ausentes.")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            headless=headless,
        )
        page = browser.new_page()

        page.goto(URL_LOGIN)
        page.wait_for_load_state("domcontentloaded")

        if page.locator(SEL_LOGIN_USER).count() > 0:
            page.fill(SEL_LOGIN_USER, usuario)
            page.fill(SEL_LOGIN_PASS, senha)
            page.click(SEL_LOGIN_BTN)
            page.wait_for_selector(SEL_LOGIN_USER, state="detached", timeout=30000)

        goto_manobra(page)
        pesquisar_numero(page, numero)

        link = page.locator("table[id='formManobra:resulPesManobra'] a", has_text=numero).first
        try:
            link.wait_for(timeout=20000, state="attached")
        except:
            print(f"MANOBRA {numero}")
            print("  Equipamentos: -")
            print("  Alimentadores/Subestações: -")
            input("Enter para fechar o navegador...")
            browser.close()
            return

        abrir_detalhe(page, numero)
        expandir_itens(page)

        eq_tabela, al_tabela = dump_itens_tables(page, verbose=verbose)
        eq_evt, al_evt = extract_from_eventos(page)

        eq_final = sorted(set(eq_tabela) | set(eq_evt))
        al_final = sorted(set(al_tabela) | set(al_evt))

        print(f"MANOBRA {numero}")
        print(f"  Equipamentos: {'; '.join(eq_final) if eq_final else '-'}")
        print(f"  Alimentadores/Subestações: {'; '.join(al_final) if al_final else '-'}")

        input("Enter para fechar o navegador...")
        browser.close()


if __name__ == "__main__":
    main()
