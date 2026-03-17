import os
import getpass
import re

from playwright.sync_api import sync_playwright

"""
gdis_login.py

Credenciais:
- Nunca ficam hardcoded no arquivo.
- O script lê de variáveis de ambiente:
  - GDIS_USUARIO
  - GDIS_SENHA
- Se não estiverem definidas, solicita no prompt (terminal).

Configuração (opcional):
- GDIS_HEADLESS=1/0
- GDIS_BLOCK_RESOURCES=1/0  (bloqueia imagens/fonts/mídia para acelerar)
- GDIS_KEEP_OPEN=1/0        (se 1, aguarda Enter para fechar o navegador)
"""


URL_LOGIN = "http://gdis-pm/gdispm/"

# Seletores do formulário de login (JSF).
SEL_LOGIN_USER = "input[id='formLogin:userid']"
SEL_LOGIN_PASS = "input[id='formLogin:password']"
SEL_LOGIN_BTN = "input[id='formLogin:botao']"

# Datas da pesquisa na tela "Manobra"
# - Se você definir GDIS_DATA, ele usa a mesma data como início e fim
# - Se você definir GDIS_DATA_INICIO / GDIS_DATA_FIM, ele usa o intervalo
DATA_INICIO = "18/03/2026"
DATA_FIM = "18/03/2026"

def _run_http_extraction():
    import gdis_http_extrator

    gdis_http_extrator.DATA_INICIO = DATA_INICIO
    gdis_http_extrator.DATA_FIM = DATA_FIM
    gdis_http_extrator.main()

def _wait_ajax_idle(page, timeout=30000):
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

def _ensure_consultar_manobras_panel(page):
    try:
        is_open = page.evaluate(
            """() => {
                const body = document.getElementById('formPesquisa:consultaManobras2_body');
                if (!body) return true;
                const s = window.getComputedStyle(body);
                return !!(s && s.display !== 'none');
            }"""
        )
    except:
        is_open = True
    if not is_open:
        try:
            page.click("div[id='formPesquisa:consultaManobras2_header']", timeout=5000)
        except:
            pass
        _wait_ajax_idle(page, timeout=30000)
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

def _wait_results_contain_numero(page, numero, timeout=25000):
    try:
        page.wait_for_function(
            """(num) => {
                const t = document.getElementById('formManobra:resulPesManobra') ||
                          document.querySelector("table[id$='resulPesManobra']") ||
                          document.querySelector("table[id*='resulPesManobra']");
                if (!t) return false;
                const txt = (t.textContent || '');
                return txt.includes(String(num));
            }""",
            numero,
            timeout=timeout,
        )
    except:
        pass

def _extract_numbers_from_table(page):
    return page.evaluate(
        """() => {
            const tabela =
                document.getElementById('formManobra:resulPesManobra') ||
                document.querySelector("table[id$='resulPesManobra']") ||
                document.querySelector("table[id*='resulPesManobra']");
            if (!tabela) return [];

            const norm = (s) => (s || '').toLowerCase().replace(/\\s+/g, ' ').trim();
            const headerCells = Array.from(tabela.querySelectorAll('thead tr:first-child th'));
            const headers = headerCells.map(th => norm(th.innerText || th.textContent || ''));

            let idx = headers.findIndex(h => h.includes('manobra') && (h.includes('nº') || h.includes('no') || h.includes('n°')));
            if (idx < 0) idx = headers.findIndex(h => h.includes('manobra'));
            if (idx < 0) idx = 0;

            const onlyDigits = (s) => (s || '').replace(/\\D/g, '');
            const rows = Array.from(tabela.querySelectorAll('tbody > tr'));
            const out = [];
            for (const row of rows) {
                const tds = row.querySelectorAll('td');
                if (tds.length <= idx) continue;
                const digits = onlyDigits(tds[idx].innerText || tds[idx].textContent || '');
                if (digits.length === 9) out.push(digits);
            }
            return out;
        }"""
    )


def _snapshot_table(page):
    return page.evaluate(
        """() => {
            const tabela =
                document.getElementById('formManobra:resulPesManobra') ||
                document.querySelector("table[id$='resulPesManobra']") ||
                document.querySelector("table[id*='resulPesManobra']");
            if (!tabela) return '';
            const onlyDigits = (s) => (s || '').replace(/\\D/g, '');
            const rows = Array.from(tabela.querySelectorAll('tbody > tr'));
            const ids = rows.map(r => {
                const tds = r.querySelectorAll('td');
                for (const td of tds) {
                    const d = onlyDigits(td.innerText || td.textContent || '');
                    if (d.length === 9) return d;
                }
                return '';
            }).filter(v => v);
            if (!ids.length) return '';
            const head = ids.slice(0, 3);
            const tail = ids.slice(-3);
            return String(ids.length) + '|' + head.join('|') + '|...|' + tail.join('|');
        }"""
    )


def _open_detail_from_results(page, numero):
    page.locator("table[id='formManobra:resulPesManobra'] a", has_text=numero).first.click(force=True)
    _wait_ajax_idle(page, timeout=30000)
    page.wait_for_selector("input[id='j_id51:bttVoltar']", timeout=25000, state="visible")
    page.wait_for_selector("div[id*='etapasManobraSimplePanelId']", timeout=25000, state="attached")
    try:
        page.evaluate(
            """() => {
                try { delete window.__gdis_lastCount; } catch(e) {}
                try { delete window.__gdis_sameCount; } catch(e) {}
            }"""
        )
    except:
        pass
    try:
        page.wait_for_selector(
            "table[id$=':itensCadastrados']",
            timeout=25000,
            state="attached",
        )
    except:
        pass


def _expand_itens_panels(page):
    headers = page.evaluate(
        """() => {
            const root = document.querySelector("div[id*='etapasManobraSimplePanelId']");
            if (!root) return [];
            return Array.from(root.querySelectorAll("div[id$='itensManobraSimplePanelId_header']")).map(h => h.id).filter(Boolean);
        }"""
    ) or []

    for hid in headers:
        try:
            is_open = page.evaluate(
                """(headerId) => {
                    const header = document.getElementById(headerId);
                    if (!header) return true;
                    const bodyId = headerId.replace('_header', '_body');
                    const body = document.getElementById(bodyId);
                    if (!body) return true;
                    const s = window.getComputedStyle(body);
                    return !!(s && s.display !== 'none');
                }""",
                hid,
            )
        except:
            is_open = True

        if not is_open:
            try:
                page.click(f"div[id='{hid}']", timeout=5000)
            except:
                pass
            _wait_ajax_idle(page, timeout=30000)


def _wait_extraction_stable(page, timeout_ms=25000):
    try:
        page.wait_for_function(
            """() => {
                const root = document.querySelector("div[id*='etapasManobraSimplePanelId']");
                const scope = root || document;
                const tables = Array.from(scope.querySelectorAll("table[id$=':itensCadastrados']"));
                if (!tables.length) return false;

                const clean = (s) => (s || '').replace(/\\s+/g, ' ').trim();
                let count = 0;
                for (const t of tables) {
                    const ths = Array.from(t.querySelectorAll('thead tr:first-child th'));
                    const headers = ths.map(th => (th.textContent || '').toLowerCase());
                    const idxEq = headers.findIndex(h => h.includes('eqpto') || h.includes('trafo'));
                    const idxAl = headers.findIndex(h => h.includes('alimen') || h.includes('subes'));
                    const rows = Array.from(t.querySelectorAll('tbody > tr'));
                    for (const r of rows) {
                        const tds = r.querySelectorAll('td');
                        if (idxEq >= 0 && tds.length > idxEq) {
                            const v = clean(tds[idxEq].textContent || '');
                            if (v && v !== '-' && v !== ' - ') count += 1;
                        }
                        if (idxAl >= 0 && tds.length > idxAl) {
                            const v = clean(tds[idxAl].textContent || '');
                            if (v && v !== '-' && v !== ' - ') count += 1;
                        }
                    }
                }

                window.__gdis_lastCount = window.__gdis_lastCount ?? -1;
                window.__gdis_sameCount = window.__gdis_sameCount ?? 0;
                if (count === window.__gdis_lastCount) window.__gdis_sameCount += 1;
                else window.__gdis_sameCount = 0;
                window.__gdis_lastCount = count;

                return window.__gdis_sameCount >= 2;
            }""",
            timeout=timeout_ms,
        )
    except:
        pass


def _extract_equipamentos(page):
    return page.evaluate(
        """() => {
            const root = document.querySelector("div[id*='etapasManobraSimplePanelId']");
            const scope = root || document;

            const norm = (s) => (s || '').toLowerCase().replace(/\\s+/g, ' ').trim();
            const clean = (s) => (s || '').replace(/\\s+/g, ' ').trim();

            const tables = Array.from(scope.querySelectorAll("table[id$=':itensCadastrados']"));
            const eqptos = new Set();
            const alim = new Set();

            for (const tabela of tables) {
                const ths = Array.from(tabela.querySelectorAll('thead tr:first-child th'));
                const headers = ths.map(th => norm(th.textContent || ''));

                let idxEqpto = headers.findIndex(h => h.includes('eqpto') || h.includes('trafo'));
                let idxAlim = headers.findIndex(h => h.includes('alimen') || h.includes('subes'));
                if (idxEqpto < 0 && idxAlim < 0) continue;

                const rows = Array.from(tabela.querySelectorAll('tbody > tr'));
                for (const row of rows) {
                    const tds = row.querySelectorAll('td');
                    if (idxEqpto >= 0 && tds.length > idxEqpto) {
                        const v = clean(tds[idxEqpto].textContent || '');
                        if (v && v !== '-' && v !== ' - ') eqptos.add(v);
                    }
                    if (idxAlim >= 0 && tds.length > idxAlim) {
                        const v = clean(tds[idxAlim].textContent || '');
                        if (v && v !== '-' && v !== ' - ') alim.add(v);
                    }
                }
            }

            return { eqpto_trafos: Array.from(eqptos), alimen_subes: Array.from(alim) };
        }"""
    )

def _extract_from_eventos(page):
    eventos_txt = page.evaluate(
        """() => {
            const nodes = Array.from(document.querySelectorAll("[id*='eventosList']"));
            const txt = nodes.map(n => (n.textContent || '').trim()).filter(Boolean).join("\\n");
            return txt;
        }"""
    ) or ""

    equipamentos = set()
    alim_subes = set()

    for m in re.finditer(r"\b\d{3,7}\s*-\s*\d+\s*-\s*\d+\b", eventos_txt):
        equipamentos.add(re.sub(r"\s*-\s*", " - ", m.group(0).strip()))

    for m in re.finditer(r"\b\d{2}\s*-\s*\d{5,7}\b", eventos_txt):
        equipamentos.add(re.sub(r"\s*-\s*", " - ", m.group(0).strip()))

    for m in re.finditer(r"\bTrafo\s+(\d{5,7}\s*-\s*\d+\s*-\s*\d+)\b", eventos_txt, flags=re.IGNORECASE):
        equipamentos.add(re.sub(r"\s*-\s*", " - ", m.group(1).strip()))

    for m in re.finditer(r"Subesta(?:ç|c)ão\s+([A-Z]{3,6}\d{0,3})", eventos_txt, flags=re.IGNORECASE):
        alim_subes.add(m.group(1).upper())

    for m in re.finditer(r"Alimentador\s+([A-Z]{3,6}\d{0,3})", eventos_txt, flags=re.IGNORECASE):
        alim_subes.add(m.group(1).upper())

    return sorted(equipamentos), sorted(alim_subes)


def _back_to_search(page):
    page.click("input[id='j_id51:bttVoltar']", timeout=20000)
    _wait_ajax_idle(page, timeout=30000)
    page.wait_for_selector("input[id='formPesquisa:numeroManobra']", timeout=25000)



def main():
    use_ui = (os.getenv("GDIS_USE_UI") or "").strip().lower() in {"1", "true", "yes", "y"}
    if not use_ui:
        _run_http_extraction()
        return

    usuario = (os.getenv("GDIS_USUARIO") or "").strip() or input("Usuário: ").strip()
    senha = (os.getenv("GDIS_SENHA") or "").strip() or getpass.getpass("Senha: ")

    headless = (os.getenv("GDIS_HEADLESS") or "").strip().lower() in {"1", "true", "yes", "y"}

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", headless=headless)
        page = browser.new_page()

        # Abre o login.
        page.goto(URL_LOGIN)
        page.wait_for_load_state("domcontentloaded")

        # Se o campo de usuário não existir, provavelmente já existe sessão logada.
        if page.locator(SEL_LOGIN_USER).count() <= 0:
            print("Login já está ativo (formulário não encontrado).")
        else:
            # Preenche credenciais e dispara login.
            page.fill(SEL_LOGIN_USER, usuario)
            page.fill(SEL_LOGIN_PASS, senha)
            page.click(SEL_LOGIN_BTN)
            page.wait_for_selector(SEL_LOGIN_USER, state="detached", timeout=30000)
            print("Login realizado.")

        # Pós-login: navegar no menu Consultas -> Manobra
        try:
            page.click("text=Consultas", force=True, timeout=20000)
            page.wait_for_timeout(200)
            page.click("text=Manobra", force=True, timeout=20000)
            _wait_ajax_idle(page, timeout=30000)

            # Confirma que abriu a tela correta aguardando o campo "Número da Manobra"
            page.wait_for_selector(
                "input[id='formPesquisa:numeroManobra']",
                timeout=25000,
                state="visible",
            )
            print("Tela Manobra carregada.")
            _ensure_consultar_manobras_panel(page)

            # Preenche período (data início e data fim)
            page.wait_for_timeout(500)
            if DATA_INICIO:
                page.fill("input[id='formPesquisa:dataInicioInputDate']", DATA_INICIO)
            page.wait_for_timeout(500)
            if DATA_FIM:
                page.fill("input[id='formPesquisa:dataTerminioInputDate']", DATA_FIM)

            # Situação: ELABORADA (value="EB") -> Pesquisar
            page.wait_for_timeout(500)
            _ensure_consultar_manobras_panel(page)
            page.select_option("select[id='formPesquisa:situacao']", value="EB")
            page.click("input[id='formPesquisa:j_id109']")
            page.wait_for_timeout(500)
            _wait_ajax_idle(page, timeout=30000)

            # Contagem de manobras (ELABORADA):
            # - Lê a coluna "Nº da Manobra" na tabela de resultados
            # - Descobre quantas páginas existem no paginador
            # - Vai para a próxima página e repete até acabar
            page.wait_for_selector("table[id='formManobra:resulPesManobra']", timeout=25000)

            numeros_elaborada = set()
            pagina_atual = 1
            max_paginas = 500
            while pagina_atual <= max_paginas:
                ids = _extract_numbers_from_table(page)
                for i in ids:
                    numeros_elaborada.add(i)
                print(f"ELABORADA - página {pagina_atual}: {len(ids)}")

                snapshot_antes = _snapshot_table(page)

                clicou_proxima = page.evaluate(
                    """(prox) => {
                        const scroller = document.getElementById('formManobra:resulPesManobraScroll_table');
                        if (!scroller) return false;

                        const want = String(prox);
                        const candidates = Array.from(scroller.querySelectorAll('td,span,a,button'));

                        const clickAny = (el) => {
                            if (!el) return false;
                            const c = (el.className || '').toLowerCase();
                            if (c.includes('dsbld') || c.includes('disabled')) return false;
                            try { el.scrollIntoView({ block: 'center', inline: 'center' }); } catch(e) {}
                            try { el.click(); return true; } catch(e) {}
                            try {
                                const opts = { bubbles: true, cancelable: true, view: window };
                                el.dispatchEvent(new MouseEvent('click', opts));
                                return true;
                            } catch(e) {}
                            return false;
                        };

                        const byNum = candidates.find(el => ((el.textContent || '').trim() === want));
                        if (clickAny(byNum)) return true;

                        const byFastForward = candidates.find(el => {
                            const t = ((el.textContent || '')).trim();
                            if (t === '»') return true;
                            const oc = (el.getAttribute && el.getAttribute('onclick')) ? String(el.getAttribute('onclick')) : '';
                            return oc.includes('fastforward') && t.includes('»') && !t.includes('»»');
                        });
                        if (clickAny(byFastForward)) return true;

                        const byNext = candidates.find(el => {
                            const t = ((el.textContent || '')).trim();
                            return t === '>' || t === '>>';
                        });
                        if (clickAny(byNext)) return true;

                        return false;
                    }""",
                    pagina_atual + 1,
                )

                if not clicou_proxima:
                    break

                try:
                    page.wait_for_function(
                        """(prev) => {
                            const tabela =
                                document.getElementById('formManobra:resulPesManobra') ||
                                document.querySelector("table[id$='resulPesManobra']") ||
                                document.querySelector("table[id*='resulPesManobra']");
                            if (!tabela) return false;
                            const onlyDigits = (s) => (s || '').replace(/\\D/g, '');
                            const rows = Array.from(tabela.querySelectorAll('tbody > tr'));
                            const ids = rows.map(r => {
                                const tds = r.querySelectorAll('td');
                                for (const td of tds) {
                                    const d = onlyDigits(td.innerText || td.textContent || '');
                                    if (d.length === 9) return d;
                                }
                                return '';
                            }).filter(v => v);
                            if (!ids.length) return false;
                            const head = ids.slice(0, 3);
                            const tail = ids.slice(-3);
                            const now = String(ids.length) + '|' + head.join('|') + '|...|' + tail.join('|');
                            return now && now !== prev;
                        }""",
                        snapshot_antes,
                        timeout=15000,
                    )
                except:
                    page.wait_for_timeout(800)
                _wait_ajax_idle(page, timeout=30000)

                pagina_ativa = page.evaluate(
                    """() => {
                        const scroller = document.getElementById('formManobra:resulPesManobraScroll_table');
                        if (!scroller) return null;
                        const act = scroller.querySelector('.rich-datascr-act');
                        if (!act) return null;
                        const n = parseInt((act.textContent || '').trim(), 10);
                        return Number.isFinite(n) ? n : null;
                    }"""
                )
                if pagina_ativa:
                    pagina_atual = int(pagina_ativa)
                else:
                    pagina_atual += 1

            numeros_elaborada = sorted(numeros_elaborada)
            print(f"ELABORADA - manobras coletadas: {len(numeros_elaborada)}")

            # Situação: ENVIADA PARA O CONDIS (value="EN") -> Pesquisar
            page.wait_for_timeout(500)
            page.select_option("select[id='formPesquisa:situacao']", value="EN")
            page.click("input[id='formPesquisa:j_id109']")
            page.wait_for_timeout(500)
            _wait_ajax_idle(page, timeout=30000)

            # Antes de contar "ENVIADA PARA O CONDIS", espera o grid refletir a situação EN.
            # Sem isso, às vezes a contagem lê o resultado anterior (ELABORADA) porque o RichFaces ainda está atualizando via AJAX.
            try:
                page.wait_for_function(
                    """() => {
                        const tabela = document.getElementById('formManobra:resulPesManobra');
                        if (!tabela) return false;
                        const rows = Array.from(tabela.querySelectorAll('tbody > tr'));
                        if (!rows.length) return false;
                        const txt = (rows[0].innerText || rows[0].textContent || '').toLowerCase();
                        return txt.includes('enviada para o condis');
                    }""",
                    timeout=25000,
                )
            except:
                pass

            # Contagem de manobras (ENVIADA PARA O CONDIS):
            # - Lê a coluna "Nº da Manobra" na tabela de resultados
            # - Descobre quantas páginas existem no paginador
            # - Vai para a próxima página e repete até acabar
            page.wait_for_selector("table[id='formManobra:resulPesManobra']", timeout=25000)

            numeros_enviada = set()
            pagina_atual = 1
            max_paginas = 500
            while pagina_atual <= max_paginas:
                ids = _extract_numbers_from_table(page)
                for i in ids:
                    numeros_enviada.add(i)
                print(f"ENVIADA - página {pagina_atual}: {len(ids)}")

                snapshot_antes = _snapshot_table(page)

                clicou_proxima = page.evaluate(
                    """(prox) => {
                        const scroller = document.getElementById('formManobra:resulPesManobraScroll_table');
                        if (!scroller) return false;

                        const want = String(prox);
                        const candidates = Array.from(scroller.querySelectorAll('td,span,a,button'));

                        const clickAny = (el) => {
                            if (!el) return false;
                            const c = (el.className || '').toLowerCase();
                            if (c.includes('dsbld') || c.includes('disabled')) return false;
                            try { el.scrollIntoView({ block: 'center', inline: 'center' }); } catch(e) {}
                            try { el.click(); return true; } catch(e) {}
                            try {
                                const opts = { bubbles: true, cancelable: true, view: window };
                                el.dispatchEvent(new MouseEvent('click', opts));
                                return true;
                            } catch(e) {}
                            return false;
                        };

                        const byNum = candidates.find(el => ((el.textContent || '').trim() === want));
                        if (clickAny(byNum)) return true;

                        const byFastForward = candidates.find(el => {
                            const t = ((el.textContent || '')).trim();
                            if (t === '»') return true;
                            const oc = (el.getAttribute && el.getAttribute('onclick')) ? String(el.getAttribute('onclick')) : '';
                            return oc.includes('fastforward') && t.includes('»') && !t.includes('»»');
                        });
                        if (clickAny(byFastForward)) return true;

                        const byNext = candidates.find(el => {
                            const t = ((el.textContent || '')).trim();
                            return t === '>' || t === '>>';
                        });
                        if (clickAny(byNext)) return true;

                        return false;
                    }""",
                    pagina_atual + 1,
                )

                if not clicou_proxima:
                    break

                try:
                    page.wait_for_function(
                        """(prev) => {
                            const tabela =
                                document.getElementById('formManobra:resulPesManobra') ||
                                document.querySelector("table[id$='resulPesManobra']") ||
                                document.querySelector("table[id*='resulPesManobra']");
                            if (!tabela) return false;
                            const onlyDigits = (s) => (s || '').replace(/\\D/g, '');
                            const rows = Array.from(tabela.querySelectorAll('tbody > tr'));
                            const ids = rows.map(r => {
                                const tds = r.querySelectorAll('td');
                                for (const td of tds) {
                                    const d = onlyDigits(td.innerText || td.textContent || '');
                                    if (d.length === 9) return d;
                                }
                                return '';
                            }).filter(v => v);
                            if (!ids.length) return false;
                            const head = ids.slice(0, 3);
                            const tail = ids.slice(-3);
                            const now = String(ids.length) + '|' + head.join('|') + '|...|' + tail.join('|');
                            return now && now !== prev;
                        }""",
                        snapshot_antes,
                        timeout=15000,
                    )
                except:
                    page.wait_for_timeout(800)
                _wait_ajax_idle(page, timeout=30000)

                pagina_ativa = page.evaluate(
                    """() => {
                        const scroller = document.getElementById('formManobra:resulPesManobraScroll_table');
                        if (!scroller) return null;
                        const act = scroller.querySelector('.rich-datascr-act');
                        if (!act) return null;
                        const n = parseInt((act.textContent || '').trim(), 10);
                        return Number.isFinite(n) ? n : null;
                    }"""
                )
                if pagina_ativa:
                    pagina_atual = int(pagina_ativa)
                else:
                    pagina_atual += 1

            numeros_enviada = sorted(numeros_enviada)
            print(f"ENVIADA - manobras coletadas: {len(numeros_enviada)}")

            todos = sorted(set(numeros_elaborada) | set(numeros_enviada))
            print(f"TOTAL - manobras únicas: {len(todos)}")

            for i, numero in enumerate(todos, start=1):
                try:
                    _ensure_consultar_manobras_panel(page)
                    try:
                        page.fill("input[id='formPesquisa:dataInicioInputDate']", "")
                    except:
                        pass
                    try:
                        page.fill("input[id='formPesquisa:dataTerminioInputDate']", "")
                    except:
                        pass
                    page.fill("input[id='formPesquisa:numeroManobra']", numero)
                    try:
                        page.select_option("select[id='formPesquisa:situacao']", value="")
                    except:
                        pass
                    page.click("input[id='formPesquisa:j_id109']")
                    page.wait_for_selector("table[id='formManobra:resulPesManobra']", timeout=25000)
                    _wait_ajax_idle(page, timeout=30000)
                    _wait_results_contain_numero(page, numero, timeout=25000)

                    try:
                        page.wait_for_selector(
                            f"table[id='formManobra:resulPesManobra'] a:has-text('{numero}')",
                            timeout=15000,
                        )
                    except:
                        print(f"MANOBRA {numero}")
                        print("  Equipamentos: -")
                        print("  Alimentadores/Subestações: -")
                        continue

                    _open_detail_from_results(page, numero)

                    eqptos = []
                    alim = []
                    for attempt in range(3):
                        _expand_itens_panels(page)
                        _wait_ajax_idle(page, timeout=30000)
                        _wait_extraction_stable(page, timeout_ms=30000)
                        try:
                            page.wait_for_function(
                                """() => {
                                    const root = document.querySelector("div[id*='etapasManobraSimplePanelId']");
                                    const scope = root || document;
                                    const tables = Array.from(scope.querySelectorAll("table[id$=':itensCadastrados']"));
                                    if (!tables.length) return false;
                                    return tables.some(t => (t.querySelectorAll('tbody > tr').length > 0));
                                }""",
                                timeout=15000,
                            )
                        except:
                            pass

                        equipamentos = _extract_equipamentos(page)
                        eqptos = equipamentos.get("eqpto_trafos") or []
                        alim = equipamentos.get("alimen_subes") or []
                        if eqptos:
                            break
                        if attempt >= 2:
                            break

                    if not eqptos and not alim:
                        eqptos_ev, alim_ev = _extract_from_eventos(page)
                        for v in eqptos_ev:
                            eqptos.append(v)
                        for v in alim_ev:
                            alim.append(v)

                    eqptos = sorted(set(eqptos))
                    alim = sorted(set(alim))

                    print(f"MANOBRA {numero}")
                    print(f"  Equipamentos: {'; '.join(eqptos) if eqptos else '-'}")
                    print(f"  Alimentadores/Subestações: {'; '.join(alim) if alim else '-'}")
                except:
                    print("  Falha ao abrir detalhe ou extrair equipamentos.")
                finally:
                    try:
                        _back_to_search(page)
                    except:
                        try:
                            page.goto(URL_LOGIN)
                        except:
                            pass
        except:
            print("Não consegui abrir Consultas -> Manobra.")

        input("Enter para fechar o navegador...")
        browser.close()


if __name__ == "__main__":
    main()

