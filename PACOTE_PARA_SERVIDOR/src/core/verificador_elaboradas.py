import os
import time
import getpass
import tempfile
import re
import html as html_lib
import urllib.parse
import sys
from concurrent.futures import ProcessPoolExecutor
from playwright.sync_api import sync_playwright

URL_SISTEMA = "http://gdis-pm/gdispm/"

def _get_input(prompt, env_var=None, is_password=False):
    """Retorna entrada da env var, ou do teclado se interativo. Se não interativo e sem env var, falha."""
    if env_var:
        val = (os.getenv(env_var) or "").strip()
        if val:
            return val
    
    if not sys.stdin.isatty():
        msg = f"\nERRO: Entrada necessária para '{prompt}' mas o ambiente não é interativo."
        if env_var:
            msg += f" Por favor, configure a variável de ambiente '{env_var}'."
        print(msg, file=sys.stderr)
        sys.exit(1)
    
    if is_password:
        return getpass.getpass(prompt)
    return input(prompt).strip()
URL_MANOBRA_GERAL = URL_SISTEMA + "pages/manobra/manobraGeral.jsf"

MINHA_MANOBRA_ID = (os.getenv("GDIS_MINHA_MANOBRA_ID", "239065370") or "").strip()
DATA_INICIO = (os.getenv("GDIS_DATA_INICIO", "18/03/2026") or "").strip()
DATA_FIM = (os.getenv("GDIS_DATA_FIM", "18/03/2026") or "").strip()

SELETOR_LOGIN_USER = "input[id='formLogin:userid']"
SELETOR_LOGIN_PASS = "input[id='formLogin:password']"
SELETOR_LOGIN_BTN = "input[id='formLogin:botao']"

SELETOR_MENU_CONSULTAS = "text=Consultas"
SELETOR_MENU_MANOBRA = "text=Manobra"

SELETOR_CAMPO_NUMERO = "input[id='formPesquisa:numeroManobra']"
SELETOR_CAMPO_DATA_INI = "input[id='formPesquisa:dataInicioInputDate']"
SELETOR_CAMPO_DATA_FIM = "input[id='formPesquisa:dataTerminioInputDate']"
SELETOR_CAMPO_DATA_FIM_ALT = "input[id='formPesquisa:dataTerminoInputDate']"
SELETOR_COMBO_SITUACAO = "select[id='formPesquisa:situacao']"
SELETOR_BTN_PESQUISAR = "input[id='formPesquisa:j_id109']"
SELETOR_BTN_PESQUISAR_ALT = "input[id='formPesquisa:botaoPesquisar']"

SELETOR_TABELA_RESULTADOS = "table[id='formManobra:resulPesManobra']"
SELETORES_TABELA_RESULTADOS = [SELETOR_TABELA_RESULTADOS, "table[id$='resulPesManobra']", "table[id*='resulPesManobra']"]


def _chunk_list(values, chunk_count):
    if chunk_count <= 1:
        return [list(values)]
    values = list(values)
    n = len(values)
    if n == 0:
        return [[]]
    chunk_size = max(1, (n + chunk_count - 1) // chunk_count)
    return [values[i : i + chunk_size] for i in range(0, n, chunk_size)]


def _worker_verificar(ids, usuario, senha, storage_state_path, meus_alims, meus_equips, meus_equips_locais):
    meus_alims = set(meus_alims or [])
    meus_equips = set(meus_equips or [])
    meus_equips_locais = set(meus_equips_locais or [])

    app = VerificadorElaboradas()
    conflitos = []
    tentadas = 0
    verificadas = 0
    try:
        app.iniciar(storage_state_path=storage_state_path)
        ok = app.login(usuario, senha)
        if not ok:
            return {"conflitos": conflitos, "tentadas": tentadas, "verificadas": verificadas}

        app.ir_para_busca_manobra()
        app.preparar_busca_por_numero()

        for num in ids:
            tentadas += 1
            criterios = None
            fast_env = (os.getenv("GDIS_FAST_ENDPOINT", "1") or "").strip().lower()
            usar_fast = fast_env not in {"0", "false", "no", "n"}
            if usar_fast:
                try:
                    itens = app.extrair_itens_manobra_por_numero_fast(num, filtro_alimentadores=meus_alims)
                    if itens is not None:
                        alims, equips, equips_locais = app.montar_criterios(itens)
                        criterios = {
                            "alimentadores": sorted(alims),
                            "equipamentos": sorted(equips),
                            "equipamentos_locais": sorted(equips_locais),
                        }
                except:
                    criterios = None

            if criterios is None:
                if not app.abrir_manobra_por_numero(num):
                    continue
                try:
                    criterios = app.extrair_criterios_manobra_aberta(filtro_alimentadores=meus_alims)
                finally:
                    app.voltar_para_busca()
            verificadas += 1

            alims = set((criterios or {}).get("alimentadores") or [])
            if not (meus_alims & alims):
                continue

            equips = set((criterios or {}).get("equipamentos") or [])
            equips_locais = set((criterios or {}).get("equipamentos_locais") or [])
            inter_eq = meus_equips & equips
            inter_eq_loc = meus_equips_locais & equips_locais
            if not inter_eq and not inter_eq_loc:
                continue

            conflitos.append(
                {
                    "manobra": num,
                    "alimentadores": sorted(meus_alims & alims),
                    "equipamentos": sorted(inter_eq),
                    "equipamentos_locais": sorted(inter_eq_loc),
                }
            )
    finally:
        try:
            app.fechar()
        except:
            pass
    return {"conflitos": conflitos, "tentadas": tentadas, "verificadas": verificadas}


class VerificadorElaboradas:
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self._busca_modo_numero = False

    def iniciar(self, storage_state_path=None):
        self.playwright = sync_playwright().start()

        caminhos = [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        ]
        headless_env = (os.getenv("GDIS_HEADLESS", "1") or "").strip().lower()
        headless = headless_env not in {"0", "false", "no", "n"}
        executavel = next((c for c in caminhos if os.path.exists(c)), None)
        if executavel:
            self.browser = self.playwright.chromium.launch(executable_path=executavel, headless=headless)
        else:
            self.browser = self.playwright.chromium.launch(headless=headless)

        if storage_state_path:
            self.context = self.browser.new_context(storage_state=storage_state_path)
        else:
            self.context = self.browser.new_context()
        block_env = (os.getenv("GDIS_BLOCK_RESOURCES", "1") or "").strip().lower()
        block_resources = block_env not in {"0", "false", "no", "n"}
        if block_resources:
            self.context.route(
                "**/*",
                lambda route, request: route.abort()
                if request.resource_type in {"image", "font", "media"}
                else route.continue_(),
            )
        self.page = self.context.new_page()
        self.page.set_default_timeout(15000)
        self.page.set_default_navigation_timeout(30000)

    def fechar(self):
        try:
            if self.browser:
                self.browser.close()
        finally:
            if self.playwright:
                self.playwright.stop()

    def _fill_primeiro_disponivel(self, seletores, valor):
        for sel in seletores:
            try:
                loc = self.page.locator(sel)
                if loc.count() <= 0:
                    continue
                try:
                    if not loc.first.is_visible():
                        continue
                    if not loc.first.is_enabled():
                        continue
                except:
                    pass
                loc.first.fill(valor)
                return True
            except:
                continue
        return False

    def _click_primeiro_disponivel(self, seletores):
        for sel in seletores:
            try:
                loc = self.page.locator(sel)
                if loc.count() <= 0:
                    continue
                try:
                    if not loc.first.is_visible():
                        continue
                    if not loc.first.is_enabled():
                        continue
                except:
                    pass
                loc.first.click()
                return True
            except:
                continue
        return False

    def login(self, usuario, senha):
        self.page.goto(URL_SISTEMA)
        self.page.wait_for_load_state("networkidle")

        if self.page.locator(SELETOR_LOGIN_USER).count() <= 0:
            return True

        if not usuario:
            usuario = _get_input("GDIS usuário: ", "GDIS_USUARIO")

        if not senha:
            senha = _get_input("GDIS senha: ", "GDIS_SENHA", is_password=True)

        if not usuario or not senha:
            return False

        self.page.fill(SELETOR_LOGIN_USER, usuario)
        self.page.fill(SELETOR_LOGIN_PASS, senha)
        self.page.click(SELETOR_LOGIN_BTN)
        self.page.wait_for_load_state("networkidle")
        return True

    def ir_para_busca_manobra(self):
        try:
            loc = self.page.locator(SELETOR_CAMPO_NUMERO)
            if loc.count() > 0:
                try:
                    if loc.first.is_visible():
                        return
                except:
                    try:
                        self.page.wait_for_selector(SELETOR_CAMPO_NUMERO, timeout=1500, state="visible")
                        return
                    except:
                        pass
        except:
            pass

        for u in [URL_MANOBRA_GERAL, URL_SISTEMA + "index.jsf", URL_SISTEMA]:
            try:
                self.page.goto(u)
                try:
                    self.page.wait_for_load_state("domcontentloaded")
                except:
                    pass
                try:
                    self.page.wait_for_load_state("networkidle")
                except:
                    pass
                try:
                    self.page.wait_for_selector(SELETOR_CAMPO_NUMERO, timeout=8000, state="visible")
                    return
                except:
                    pass
            except:
                pass

        ultimo_erro = None
        for _ in range(3):
            try:
                menus_consultas = [SELETOR_MENU_CONSULTAS, "text=/^\\s*Consultas\\s*$/i", "text=/Consultas/i"]
                if not self._click_primeiro_disponivel(menus_consultas):
                    self.page.click(SELETOR_MENU_CONSULTAS, force=True, timeout=12000)
                self.page.wait_for_timeout(200)
                menus_manobra = [SELETOR_MENU_MANOBRA, "text=/^\\s*Manobra\\s*$/i", "text=/Manobra/i"]
                if not self._click_primeiro_disponivel(menus_manobra):
                    self.page.click(SELETOR_MENU_MANOBRA, force=True, timeout=12000)
                self.page.wait_for_selector(SELETOR_CAMPO_NUMERO, timeout=20000)
                self.page.wait_for_timeout(150)
                return
            except Exception as e:
                ultimo_erro = e
                try:
                    self.page.goto(URL_SISTEMA)
                    try:
                        self.page.wait_for_load_state("domcontentloaded")
                    except:
                        pass
                    self.page.wait_for_timeout(300)
                except:
                    pass

        if ultimo_erro:
            raise ultimo_erro

    def preparar_busca_por_numero(self):
        if self._busca_modo_numero:
            return
        try:
            self._garantir_painel_consulta_expandidos()
        except:
            pass
        self._fill_primeiro_disponivel([SELETOR_CAMPO_DATA_INI], "")
        self._fill_primeiro_disponivel([SELETOR_CAMPO_DATA_FIM, SELETOR_CAMPO_DATA_FIM_ALT], "")
        try:
            self.page.select_option(SELETOR_COMBO_SITUACAO, index=0)
        except:
            try:
                self.page.evaluate(
                    """(sel) => {
                        const s = document.querySelector(sel);
                        if (!s) return;
                        s.selectedIndex = 0;
                        s.dispatchEvent(new Event('change'));
                    }""",
                    SELETOR_COMBO_SITUACAO,
                )
            except:
                pass
        self._busca_modo_numero = True

    def voltar_para_busca(self):
        for _ in range(2):
            try:
                self.page.go_back()
                self.page.wait_for_selector(SELETOR_CAMPO_NUMERO, timeout=8000, state="visible")
                return True
            except:
                pass
        try:
            self.ir_para_busca_manobra()
            self.page.wait_for_selector(SELETOR_CAMPO_NUMERO, timeout=15000, state="visible")
            return True
        except:
            return False

    def limpar_filtros(self):
        try:
            self._garantir_painel_consulta_expandidos()
        except:
            pass
        self._fill_primeiro_disponivel([SELETOR_CAMPO_NUMERO], "")
        self._fill_primeiro_disponivel([SELETOR_CAMPO_DATA_INI], "")
        self._fill_primeiro_disponivel([SELETOR_CAMPO_DATA_FIM, SELETOR_CAMPO_DATA_FIM_ALT], "")
        try:
            self.page.select_option(SELETOR_COMBO_SITUACAO, index=0)
        except:
            try:
                self.page.evaluate(
                    """(sel) => {
                        const s = document.querySelector(sel);
                        if (!s) return;
                        s.selectedIndex = 0;
                        s.dispatchEvent(new Event('change'));
                    }""",
                    SELETOR_COMBO_SITUACAO,
                )
            except:
                pass

    def _garantir_painel_consulta_expandidos(self):
        try:
            self.page.evaluate(
                """() => {
                    const headers = Array.from(document.querySelectorAll('.rich-stglpanel-header'));
                    const pick = headers.find(h => (h.textContent || '').toLowerCase().includes('consultar manobras'));
                    if (!pick) return false;
                    const body = document.getElementById(pick.id.replace('_header', '_body'));
                    if (!body) return false;
                    const hidden = (body.style.display === 'none' || body.style.display === '');
                    if (hidden) pick.click();
                    return true;
                }"""
            )
        except:
            pass

    def _snapshot_filtros(self):
        try:
            return self.page.evaluate(
                """(args) => {
                    const selIni = args.selIni;
                    const selFim = args.selFim;
                    const selFimAlt = args.selFimAlt;
                    const selSit = args.selSit;
                    const ini = document.querySelector(selIni);
                    const fim = document.querySelector(selFim) || document.querySelector(selFimAlt);
                    const sit = document.querySelector(selSit);
                    const sitTxt = sit && sit.options && sit.selectedIndex >= 0 ? (sit.options[sit.selectedIndex].text || '') : '';
                    return {
                        url: location.href,
                        data_inicio: ini ? (ini.value || '') : '',
                        data_fim: fim ? (fim.value || '') : '',
                        situacao: (sitTxt || '').trim()
                    };
                }""",
                {
                    "selIni": SELETOR_CAMPO_DATA_INI,
                    "selFim": SELETOR_CAMPO_DATA_FIM,
                    "selFimAlt": SELETOR_CAMPO_DATA_FIM_ALT,
                    "selSit": SELETOR_COMBO_SITUACAO,
                },
            )
        except:
            return {"url": "", "data_inicio": "", "data_fim": "", "situacao": ""}

    def selecionar_situacao(self, situacao):
        situacao = (situacao or "").strip()
        if not situacao:
            try:
                self.page.select_option(SELETOR_COMBO_SITUACAO, index=0)
                try:
                    self.page.wait_for_timeout(150)
                except:
                    pass
                return True
            except:
                pass
            try:
                ok = self.page.evaluate(
                    """(sel) => {
                        const s = document.querySelector(sel);
                        if (!s) return false;
                        s.selectedIndex = 0;
                        s.dispatchEvent(new Event('change'));
                        return true;
                    }""",
                    SELETOR_COMBO_SITUACAO,
                )
                try:
                    self.page.wait_for_timeout(150)
                except:
                    pass
                return bool(ok)
            except:
                return False

        try:
            self.page.select_option(SELETOR_COMBO_SITUACAO, label=situacao)
            try:
                self.page.wait_for_timeout(150)
            except:
                pass
            return True
        except:
            pass

        try:
            ok = self.page.evaluate(
                """(args) => {
                    const sel = args.sel;
                    const txt = (args.txt || '');
                    const s = document.querySelector(sel);
                    if (!s) return false;
                    const norm = (v) => (v || '')
                        .normalize('NFD')
                        .replace(/[\\u0300-\\u036f]/g, '')
                        .toLowerCase()
                        .replace(/\\s+/g, ' ')
                        .trim();
                    const target = norm(txt);
                    const opt = Array.from(s.options).find(o => norm(o.text).includes(target));
                    if (!opt) return false;
                    s.value = opt.value;
                    s.dispatchEvent(new Event('change'));
                    return true;
                }""",
                {"sel": SELETOR_COMBO_SITUACAO, "txt": situacao},
            )
            try:
                self.page.wait_for_timeout(150)
            except:
                pass
            return bool(ok)
        except:
            return False

    def selecionar_situacao_elaborada(self):
        return self.selecionar_situacao("ELABORADA")

    def listar_situacoes_disponiveis(self):
        self.ir_para_busca_manobra()
        try:
            self._garantir_painel_consulta_expandidos()
        except:
            pass
        try:
            itens = self.page.evaluate(
                """(sel) => {
                    const s = document.querySelector(sel);
                    if (!s || !s.options) return [];
                    return Array.from(s.options)
                        .map(o => (o.textContent || o.innerText || '').trim())
                        .filter(v => v);
                }""",
                SELETOR_COMBO_SITUACAO,
            )
            if not isinstance(itens, list):
                return []
            seen = set()
            out = []
            for x in itens:
                t = str(x).strip()
                if not t or t in seen:
                    continue
                seen.add(t)
                out.append(t)
            return out
        except:
            return []

    def pesquisar(self, expected_num=None):
        if expected_num:
            self._click_primeiro_disponivel([SELETOR_BTN_PESQUISAR, SELETOR_BTN_PESQUISAR_ALT])
            try:
                self.page.wait_for_function(
                    """(args) => {
                        const sels = Array.isArray(args.sels) ? args.sels : [args.sels];
                        const num = args.num;
                        let tabela = null;
                        for (const s of sels) {
                            const t = document.querySelector(s);
                            if (t) { tabela = t; break; }
                        }
                        if (!tabela) return false;

                        const onlyDigits = (s) => (s || '').replace(/\\D/g, '');
                        const rows = Array.from(tabela.querySelectorAll('tbody > tr'));
                        if (!rows.length) return false;

                        for (const r of rows) {
                            const tds = r.querySelectorAll('td');
                            for (const td of tds) {
                                const d = onlyDigits(td.innerText);
                                if (d === num) return true;
                            }
                        }
                        return false;
                    }""",
                    {"sels": SELETORES_TABELA_RESULTADOS, "num": str(expected_num)},
                    timeout=6000,
                )
            except:
                try:
                    self.page.wait_for_function(
                        """(sels) => {
                            const a = Array.isArray(sels) ? sels : [sels];
                            return a.some(s => document.querySelector(s));
                        }""",
                        SELETORES_TABELA_RESULTADOS,
                        timeout=6000,
                    )
                except:
                    pass
            self.page.wait_for_timeout(80)
            return

        prev = {"sels": SELETORES_TABELA_RESULTADOS, "prevKey": None, "prevCount": None}
        try:
            snap = self.page.evaluate(
                """(sels) => {
                    const a = Array.isArray(sels) ? sels : [sels];
                    let tabela = null;
                    for (const s of a) {
                        const t = document.querySelector(s);
                        if (t) { tabela = t; break; }
                    }
                    if (!tabela) return { key: null, count: null };
                    const onlyDigits = (s) => (s || '').replace(/\\D/g, '');
                    const rows = Array.from(tabela.querySelectorAll('tbody > tr'));
                    const sample = rows.slice(0, Math.min(5, rows.length));
                    const key = sample.map(r => {
                        const tds = r.querySelectorAll('td');
                        for (const td of tds) {
                            const d = onlyDigits(td.innerText);
                            if (d.length === 9) return d;
                        }
                        return '';
                    }).filter(v => v).join('|') || null;
                    return { key, count: rows.length };
                }""",
                SELETORES_TABELA_RESULTADOS,
            )
            prev["prevKey"] = (snap or {}).get("key")
            prev["prevCount"] = (snap or {}).get("count")
        except:
            pass

        self._click_primeiro_disponivel([SELETOR_BTN_PESQUISAR, SELETOR_BTN_PESQUISAR_ALT])
        try:
            self.page.wait_for_function(
                """(args) => {
                    const sels = Array.isArray(args.sels) ? args.sels : [args.sels];
                    const prevKey = args.prevKey;
                    const prevCount = args.prevCount;

                    let tabela = null;
                    for (const s of sels) {
                        const t = document.querySelector(s);
                        if (t) { tabela = t; break; }
                    }
                    if (!tabela) return false;
                    const onlyDigits = (s) => (s || '').replace(/\\D/g, '');
                    const rows = Array.from(tabela.querySelectorAll('tbody > tr'));
                    const sample = rows.slice(0, Math.min(5, rows.length));
                    const nowKey = sample.map(r => {
                        const tds = r.querySelectorAll('td');
                        for (const td of tds) {
                            const d = onlyDigits(td.innerText);
                            if (d.length === 9) return d;
                        }
                        return '';
                    }).filter(v => v).join('|') || null;

                    if (prevCount !== null && rows.length !== prevCount) return true;
                    if (prevKey !== null && nowKey !== prevKey) return true;
                    if (prevKey === null && rows.length > 0) return true;
                    return false;
                }""",
                prev,
                timeout=12000,
            )
        except:
            try:
                self.page.wait_for_function(
                    """(sels) => {
                        const a = Array.isArray(sels) ? sels : [sels];
                        return a.some(s => document.querySelector(s));
                    }""",
                    SELETORES_TABELA_RESULTADOS,
                    timeout=12000,
                )
            except:
                pass

        self.page.wait_for_timeout(120)

    def _paginador_click_proxima(self):
        try:
            return self.page.evaluate(
                """(selTables) => {
                    try {
                        const selectors = Array.isArray(selTables) ? selTables : [selTables];
                        const txt = (el) => (el && el.textContent ? el.textContent.trim() : '');
                        const cls = (el) => (el && el.className ? String(el.className).toLowerCase() : '');
                        const isDisabled = (el) => {
                            if (!el) return true;
                            const c = cls(el);
                            if (c.includes('dsb') || c.includes('disabled') || c.includes('inactive')) return true;
                            try {
                                const aria = el.getAttribute && el.getAttribute('aria-disabled');
                                if (aria && String(aria).toLowerCase() === 'true') return true;
                            } catch(e) {}
                            try {
                                if (el.hasAttribute && el.hasAttribute('disabled')) return true;
                            } catch(e) {}
                            return false;
                        };
                        const getClickable = (el) => {
                            if (!el) return null;
                            if (isDisabled(el)) return null;
                            const tag = (el.tagName || '').toUpperCase();
                            if (tag === 'A' || tag === 'BUTTON') return el;
                            const a = el.querySelector && el.querySelector('a');
                            if (a && !isDisabled(a)) return a;
                            const ca = el.closest && el.closest('a');
                            if (ca && !isDisabled(ca)) return ca;
                            return el;
                        };
                        const tryClick = (root) => {
                            const all = Array.from(root.querySelectorAll('a,td,span,button,img'));
                            const nums = all.filter(el => /^\\d+$/.test(txt(el)));

                            let current = null;
                            const ariaCurrent = all.find(el => (el.getAttribute && el.getAttribute('aria-current') === 'page') && /^\\d+$/.test(txt(el)));
                            if (ariaCurrent) current = parseInt(txt(ariaCurrent), 10);

                            if (current === null) {
                                for (const el of nums) {
                                    const c = cls(el);
                                    if (c.includes('act') || c.includes('active')) {
                                        current = parseInt(txt(el), 10);
                                        break;
                                    }
                                }
                            }
                            if (current === null) {
                                for (const el of nums) {
                                    const fw = window.getComputedStyle(el).fontWeight;
                                    const fwNum = parseInt(fw, 10);
                                    if (fw === 'bold' || (!Number.isNaN(fwNum) && fwNum >= 700)) {
                                        current = parseInt(txt(el), 10);
                                        break;
                                    }
                                }
                            }

                            let target = null;
                            if (current !== null) {
                                const nextNum = String(current + 1);
                                target = nums.find(el => txt(el) === nextNum && !isDisabled(el)) || null;
                            }

                            if (!target) {
                                const relNext = all.find(el => (el.getAttribute && (el.getAttribute('rel') || '').toLowerCase() === 'next') && !isDisabled(el));
                                target = relNext || null;
                            }

                            if (!target) {
                                const byClass = Array.from(root.querySelectorAll('*')).filter(el => {
                                    const c = cls(el);
                                    if (!c) return false;
                                    if (!(c.includes('next') || c.includes('nxt') || c.includes('forward'))) return false;
                                    if (!(c.includes('datascr') || c.includes('ds'))) return false;
                                    return !isDisabled(el);
                                });
                                target = byClass[0] || null;
                            }

                            if (!target) {
                                const byText = all.filter(el => {
                                    const t = txt(el);
                                    const tl = t.toLowerCase();
                                    if (t !== '>' && t !== '»' && t !== '>>' && tl !== 'proximo' && tl !== 'próximo') return false;
                                    return !isDisabled(el);
                                });
                                target = byText[0] || null;
                            }

                            if (!target) {
                                const byImg = Array.from(root.querySelectorAll('img')).filter(img => {
                                    if (isDisabled(img)) return false;
                                    const a = img.closest('a');
                                    const host = a || img;
                                    if (!host) return false;
                                    const t = ((img.getAttribute('alt') || '') + ' ' + (img.getAttribute('title') || '') + ' ' + (host.getAttribute('title') || '')).toLowerCase();
                                    return t.includes('prox') || t.includes('próx') || t.includes('proximo') || t.includes('próximo') || t.includes('next') || t.includes('forward');
                                });
                                target = byImg[0] ? (byImg[0].closest('a') || byImg[0]) : null;
                            }

                            if (!target) return { clicked: false, reason: 'no_next', current };
                            const clickEl = getClickable(target);
                            if (!clickEl) return { clicked: false, reason: 'disabled', current };

                            try { clickEl.scrollIntoView({ block: 'center', inline: 'center' }); } catch(e) {}
                            try { clickEl.focus(); } catch(e) {}
                            const opts = { bubbles: true, cancelable: true, view: window };
                            try { clickEl.dispatchEvent(new MouseEvent('mousedown', opts)); } catch(e) {}
                            try { clickEl.dispatchEvent(new MouseEvent('mouseup', opts)); } catch(e) {}
                            try { clickEl.dispatchEvent(new MouseEvent('click', opts)); } catch(e) { clickEl.click(); }
                            return { clicked: true, current };
                        };

                        let tabela = null;
                        for (const s of selectors) {
                            const t = document.querySelector(s);
                            if (t) { tabela = t; break; }
                        }

                        const roots = [];
                        const addRoot = (r) => {
                            if (!r) return;
                            if (roots.includes(r)) return;
                            roots.push(r);
                        };

                        if (tabela) {
                            addRoot(tabela.closest("[id*='resulPesManobraScroll']"));
                            addRoot(tabela.closest("[id$='resulPesManobraScroll']"));
                            addRoot(tabela.closest("[class*='datascr']"));
                            addRoot(tabela.closest("[class*='rich-datascr']"));
                            addRoot(tabela.closest("form"));
                            addRoot(tabela.parentElement);
                            addRoot(tabela.parentElement && tabela.parentElement.parentElement);
                        }

                        addRoot(document.getElementById('formManobra:resulPesManobraScroll_table'));
                        addRoot(document.getElementById('formManobra:resulPesManobraScroll'));
                        addRoot(document.querySelector("[id$='resulPesManobraScroll_table']"));
                        addRoot(document.querySelector("[id$='resulPesManobraScroll']"));
                        addRoot(document.querySelector("[id*='resulPesManobraScroll_table']"));
                        addRoot(document.querySelector("[id*='resulPesManobraScroll']"));
                        addRoot(document.querySelector("[class*='datascr']"));
                        addRoot(document.querySelector("[class*='rich-datascr']"));
                        addRoot(document);

                        let last = { clicked: false, reason: 'no_roots' };
                        for (const r of roots) {
                            if (!r || !r.querySelectorAll) continue;
                            const res = tryClick(r);
                            if (res && res.clicked) {
                                return { clicked: true, reason: 'clicked', current: res.current };
                            }
                            last = res || last;
                        }
                        return last || { clicked: false, reason: 'unknown' };
                    } catch (e) {
                        return { clicked: false, reason: 'error', error: String(e) };
                    }
                }""",
                SELETORES_TABELA_RESULTADOS,
            )
        except Exception as e:
            return {"clicked": False, "reason": "error", "error": str(e)}

    def _ler_ids_pagina(self):
        return self.page.evaluate(
            """(sel) => {
                const sels = Array.isArray(sel) ? sel : [sel];
                let tabela = null;
                for (const s of sels) {
                    const t = document.querySelector(s);
                    if (t) { tabela = t; break; }
                }
                if (!tabela) return [];

                const onlyDigits = (s) => (s || '').replace(/\\D/g, '');
                const rows = Array.from(tabela.querySelectorAll('tbody > tr'));
                if (!rows.length) return [];

                const headerCells = Array.from(tabela.querySelectorAll('thead tr:first-child th'));
                const headers = headerCells.map(th => (th.innerText || '').trim().toLowerCase());
                const sample = rows.slice(0, Math.min(20, rows.length));

                let maxCols = 0;
                for (const r of sample) {
                    const c = r.querySelectorAll('td').length;
                    if (c > maxCols) maxCols = c;
                }
                if (!maxCols) return [];

                let bestIdx = 0;
                let bestScore = -1;
                for (let i = 0; i < maxCols; i++) {
                    let score = 0;
                    for (const r of sample) {
                        const cols = r.querySelectorAll('td');
                        if (cols.length <= i) continue;
                        const digits = onlyDigits(cols[i].innerText);
                        if (digits.length === 9) score += 1;
                    }
                    const h = i < headers.length ? headers[i] : '';
                    if (h.includes('manobra')) score += 3;
                    if (score > bestScore) {
                        bestScore = score;
                        bestIdx = i;
                    }
                }

                const ids = rows.map(r => {
                    const cols = r.querySelectorAll('td');
                    if (cols.length <= bestIdx) return null;
                    const digits = onlyDigits(cols[bestIdx].innerText);
                    return digits.length === 9 ? digits : null;
                }).filter(v => v);

                return ids;
            }""",
            SELETORES_TABELA_RESULTADOS,
        )

    def _snapshot_pagina(self):
        ids = self._ler_ids_pagina()
        if not ids:
            return None
        head = ids[:5]
        tail = ids[-5:] if len(ids) > 5 else []
        return f"{len(ids)}|" + "|".join(head + ["..."] + tail)

    def coletar_elaboradas(self, data_ini, data_fim, minha_manobra_id):
        self.ir_para_busca_manobra()
        try:
            self._garantir_painel_consulta_expandidos()
        except:
            pass
        situacoes_env = (os.getenv("GDIS_SITUACOES", "") or "").strip()
        if situacoes_env:
            situacoes = [s.strip() for s in situacoes_env.split(",") if s.strip()]
        else:
            situacao_env = (os.getenv("GDIS_SITUACAO", "") or "").strip()
            if situacao_env:
                situacoes = [situacao_env]
            else:
                situacoes = ["ELABORADA", "ENVIADA PARA O CONDIS"]

        todos = []
        vistos = set()
        total_bruto = 0
        total_sobreposicao = 0

        for situacao in situacoes:
            situacao = (situacao or "").strip()
            titulo_situacao = situacao if situacao else "(todas)"
            print(f"  Situação: {titulo_situacao}")
            self.limpar_filtros()
            self._busca_modo_numero = False

            if data_ini:
                self._fill_primeiro_disponivel([SELETOR_CAMPO_DATA_INI], data_ini)
            if data_fim:
                self._fill_primeiro_disponivel([SELETOR_CAMPO_DATA_FIM, SELETOR_CAMPO_DATA_FIM_ALT], data_fim)
            ok_sit = self.selecionar_situacao(situacao)
            snap_pos = self._snapshot_filtros()
            situacao_atual = (snap_pos or {}).get("situacao") or ""
            if situacao and (not ok_sit or not situacao_atual):
                print(f"  Não consegui selecionar situação='{situacao}'. Atual='{situacao_atual}'")
            elif situacao:
                print(f"  Situação aplicada: {situacao_atual}")

            self.pesquisar()

            pagina = 1
            novos_situacao = 0
            total_ids_situacao = 0
            sobreposicao_situacao = 0
            while True:
                print(f"  Lendo página {pagina}...")
                ids = self._ler_ids_pagina()
                if pagina == 1 and not ids:
                    self.page.wait_for_timeout(500)
                    ids = self._ler_ids_pagina()
                    if not ids:
                        snap = self._snapshot_filtros()
                        print(
                            f"  Diagnóstico filtros: inicio='{snap.get('data_inicio')}', fim='{snap.get('data_fim')}', situacao='{snap.get('situacao')}'"
                        )
                total_ids_situacao += len(ids or [])
                for m in ids:
                    if minha_manobra_id and m == minha_manobra_id:
                        continue
                    if m in vistos:
                        sobreposicao_situacao += 1
                        continue
                    vistos.add(m)
                    todos.append(m)
                    novos_situacao += 1

                antes = self._snapshot_pagina()
                paginou = self._paginador_click_proxima()
                if not paginou or not isinstance(paginou, dict) or not paginou.get("clicked"):
                    if isinstance(paginou, dict):
                        reason = (paginou or {}).get("reason")
                        if reason:
                            print(f"  Paginador: {reason}")
                    break

                if antes:
                    try:
                        self.page.wait_for_function(
                            """(args) => {
                                const prev = args[0];
                                const sels = Array.isArray(args[1]) ? args[1] : [args[1]];
                                let tabela = null;
                                for (const s of sels) {
                                    const t = document.querySelector(s);
                                    if (t) { tabela = t; break; }
                                }
                                if (!tabela) return false;
                                const onlyDigits = (s) => (s || '').replace(/\\D/g, '');
                                const rows = Array.from(tabela.querySelectorAll('tbody > tr'));
                                if (!rows.length) return false;
                                const sample = rows.slice(0, Math.min(5, rows.length));
                                const now = sample.map(r => {
                                    const cols = r.querySelectorAll('td');
                                    for (const td of cols) {
                                        const d = onlyDigits(td.innerText);
                                        if (d.length === 9) return d;
                                    }
                                    return '';
                                }).filter(v => v).join('|');
                                return now && now !== prev;
                            }""",
                            [antes, SELETORES_TABELA_RESULTADOS],
                            timeout=10000,
                        )
                    except:
                        mudou = False
                        for _ in range(12):
                            self.page.wait_for_timeout(350)
                            depois = self._snapshot_pagina()
                            if depois and depois != antes:
                                mudou = True
                                break
                        if not mudou:
                            break
                else:
                    self.page.wait_for_timeout(1500)

                pagina += 1
            total_bruto += total_ids_situacao
            total_sobreposicao += sobreposicao_situacao
            print(
                f"  Total na situação: {total_ids_situacao} | Novas adicionadas: {novos_situacao} | Já existiam: {sobreposicao_situacao}"
            )

        print(f"  Resumo coleta: total_linhas={total_bruto} | unicas={len(todos)} | sobreposicao={total_sobreposicao}")
        return todos

    def abrir_manobra_por_numero(self, numero):
        self.ir_para_busca_manobra()
        self.preparar_busca_por_numero()
        self._fill_primeiro_disponivel([SELETOR_CAMPO_NUMERO], numero)
        self._click_primeiro_disponivel([SELETOR_BTN_PESQUISAR, SELETOR_BTN_PESQUISAR_ALT])

        clicou = False
        for _ in range(14):
            try:
                clicou = self.page.evaluate(
                    """(args) => {
                        const selTables = Array.isArray(args.selTables) ? args.selTables : [args.selTables];
                        const num = args.num;
                        let tabela = null;
                        for (const s of selTables) {
                            const t = document.querySelector(s);
                            if (t) { tabela = t; break; }
                        }
                        if (!tabela) return false;

                        const onlyDigits = (s) => (s || '').replace(/\\D/g, '');
                        const rows = Array.from(tabela.querySelectorAll('tbody > tr'));
                        if (!rows.length) return false;

                        const headerCells = Array.from(tabela.querySelectorAll('thead tr:first-child th'));
                        const headers = headerCells.map(th => (th.innerText || '').trim().toLowerCase());
                        const sample = rows.slice(0, Math.min(20, rows.length));

                        let maxCols = 0;
                        for (const r of sample) {
                            const c = r.querySelectorAll('td').length;
                            if (c > maxCols) maxCols = c;
                        }
                        if (!maxCols) return false;

                        let bestIdx = 0;
                        let bestScore = -1;
                        for (let i = 0; i < maxCols; i++) {
                            let score = 0;
                            for (const r of sample) {
                                const cols = r.querySelectorAll('td');
                                if (cols.length <= i) continue;
                                const digits = onlyDigits(cols[i].innerText);
                                if (digits.length === 9) score += 1;
                            }
                            const h = i < headers.length ? headers[i] : '';
                            if (h.includes('manobra')) score += 3;
                            if (score > bestScore) {
                                bestScore = score;
                                bestIdx = i;
                            }
                        }

                        for (const row of rows) {
                            const cols = row.querySelectorAll('td');
                            if (cols.length <= bestIdx) continue;
                            const val = onlyDigits(cols[bestIdx].innerText);
                            if (val !== num) continue;
                            const a = cols[bestIdx].querySelector('a') || row.querySelector('a');
                            if (a) {
                                a.click();
                                return true;
                            }
                            cols[bestIdx].click();
                            return true;
                        }
                        return false;
                    }""",
                    {"selTables": SELETORES_TABELA_RESULTADOS, "num": str(numero)},
                )
            except:
                clicou = False

            if clicou:
                break
            self.page.wait_for_timeout(250)

        if not clicou:
            return False

        try:
            self.page.wait_for_load_state("domcontentloaded", timeout=10000)
        except:
            pass
        self.page.wait_for_timeout(200)
        return True

    def extrair_criterios_manobra_aberta(self, filtro_alimentadores=None):
        try:
            self.page.wait_for_selector("table[id*='etapasCadastradas'], table[id$=':itensCadastrados']", timeout=6000)
        except:
            pass

        try:
            self.page.evaluate(
                """() => {
                    document.querySelectorAll('.rich-stglpanel-header').forEach(h => {
                        if (h.innerText.includes('Itens') || h.innerText.includes('»') || h.innerText.includes('«')) {
                            const body = document.getElementById(h.id.replace('_header', '_body'));
                            if (body && (body.style.display === 'none' || body.style.display === '')) {
                                h.click();
                            }
                        }
                    });
                }"""
            )
        except:
            pass

        try:
            self.page.wait_for_function("""() => document.querySelectorAll("table[id$=':itensCadastrados']").length > 0""", timeout=3000)
        except:
            pass

        args = {"filtro": list(filtro_alimentadores) if filtro_alimentadores else []}
        return self.page.evaluate(
            """(args) => {
                try {
                    const filtro = args.filtro || [];
                    const usarFiltro = filtro.length > 0;
                    const filtroSet = usarFiltro ? new Set(filtro) : null;

                    const tabelas = Array.from(document.querySelectorAll("table[id$=':itensCadastrados']"));
                    const norm = (s) => s ? s.normalize('NFD').replace(/[\\u0300-\\u036f]/g, '').toLowerCase() : '';
                    const clean = (s) => (s || '').replace(/\\s+/g, ' ').trim();

                    const alims = new Set();
                    const equips = new Set();
                    const equipsLoc = new Set();

                    for (const t of tabelas) {
                        if (!t) continue;
                        const headerEl = t.querySelectorAll('thead th');
                        if (!headerEl.length) continue;
                        const headers = Array.from(headerEl).map(th => clean(th.innerText || ''));
                        const idxEquip = headers.findIndex(h => norm(h).includes('eqpto') || norm(h).includes('trafo'));
                        const idxAlim = headers.findIndex(h => norm(h).includes('alimen') || norm(h).includes('subes'));
                        const idxLocal = headers.findIndex(h => norm(h).includes('local'));

                        const rows = Array.from(t.querySelectorAll('tbody tr'));
                        for (const row of rows) {
                            if (!row) continue;
                            const cols = row.querySelectorAll('td');
                            if (!cols || !cols.length) continue;

                            const eq = (idxEquip !== -1 && cols[idxEquip]) ? clean(cols[idxEquip].innerText) : '';
                            const al = (idxAlim !== -1 && cols[idxAlim]) ? clean(cols[idxAlim].innerText) : '';
                            let lo = (idxLocal !== -1 && cols[idxLocal]) ? clean(cols[idxLocal].innerText) : '';
                            if (lo === '-') lo = '';

                            if (al) alims.add(al);
                            if (!al && !eq) continue;

                            if (usarFiltro && al && !filtroSet.has(al)) continue;

                            if (eq) equips.add(eq);
                            if (eq && lo) equipsLoc.add(eq + '|' + lo);
                        }
                    }

                    return {
                        alimentadores: Array.from(alims),
                        equipamentos: Array.from(equips),
                        equipamentos_locais: Array.from(equipsLoc)
                    };
                } catch(e) {
                    return { alimentadores: [], equipamentos: [], equipamentos_locais: [] };
                }
            }""",
            args,
        )

    def extrair_itens_manobra_aberta(self):
        try:
            self.page.wait_for_selector("table[id*='etapasCadastradas']", timeout=12000)
        except:
            pass

        try:
            self.page.evaluate(
                """() => {
                    let count = 0;
                    document.querySelectorAll('.rich-stglpanel-header').forEach(h => {
                        if (h.innerText.includes('Itens') || h.innerText.includes('»') || h.innerText.includes('«')) {
                            const body = document.getElementById(h.id.replace('_header', '_body'));
                            if (body && (body.style.display === 'none' || body.style.display === '')) {
                                h.click();
                                count++;
                            }
                        }
                    });
                    return count;
                }"""
            )
        except:
            pass

        self.page.wait_for_timeout(1200)

        itens = self.page.evaluate(
            """() => {
                const tabelas = Array.from(document.querySelectorAll("table[id$=':itensCadastrados']"));
                const norm = (s) => s ? s.normalize('NFD').replace(/[\\u0300-\\u036f]/g, '').toLowerCase() : '';
                let res = [];
                for (const t of tabelas) {
                    const headers = Array.from(t.querySelectorAll('thead th')).map(th => (th.innerText || '').trim());
                    const idxEquip = headers.findIndex(h => norm(h).includes('eqpto') || norm(h).includes('trafo'));
                    const idxAlim = headers.findIndex(h => norm(h).includes('alimen') || norm(h).includes('subes'));
                    const idxLocal = headers.findIndex(h => norm(h).includes('local'));

                    const rows = Array.from(t.querySelectorAll('tbody tr'));
                    for (const row of rows) {
                        const cols = row.querySelectorAll('td');
                        if (!cols.length) continue;

                        const eq = (idxEquip !== -1 && cols[idxEquip]) ? (cols[idxEquip].innerText || '').trim() : '';
                        const al = (idxAlim !== -1 && cols[idxAlim]) ? (cols[idxAlim].innerText || '').trim() : '';
                        const lo = (idxLocal !== -1 && cols[idxLocal]) ? (cols[idxLocal].innerText || '').trim() : '';

                        if (!eq && !al) continue;
                        res.push({ equipamento: eq, alimentador: al, local: lo });
                    }
                }
                return res;
            }"""
        )

        seen = set()
        unicos = []
        for it in itens:
            k = (it.get("equipamento", ""), it.get("alimentador", ""), it.get("local", ""))
            if k in seen:
                continue
            seen.add(k)
            unicos.append(it)
        return unicos

    def _obter_view_state(self):
        try:
            v = self.page.evaluate(
                """() => {
                    const el = document.querySelector("input[name='javax.faces.ViewState']");
                    return el ? (el.value || '') : '';
                }"""
            )
            return (v or "").strip()
        except:
            return ""

    def _obter_link_param_resultado_numero(self, numero):
        try:
            return self.page.evaluate(
                """(args) => {
                    const num = String(args.num || '');
                    const selTables = Array.isArray(args.selTables) ? args.selTables : [args.selTables];
                    let tabela = null;
                    for (const s of selTables) {
                        const t = document.querySelector(s);
                        if (t) { tabela = t; break; }
                    }
                    if (!tabela) return '';

                    const onlyDigits = (s) => (s || '').replace(/\\D/g, '');
                    const rows = Array.from(tabela.querySelectorAll('tbody > tr'));
                    for (const row of rows) {
                        const cols = row.querySelectorAll('td');
                        let match = false;
                        for (const td of cols) {
                            const d = onlyDigits(td.innerText);
                            if (d === num) { match = true; break; }
                        }
                        if (!match) continue;

                        const a = row.querySelector('a[id],a[name]');
                        if (!a) return '';
                        return a.getAttribute('id') || a.getAttribute('name') || '';
                    }
                    return '';
                }""",
                {"num": str(numero), "selTables": SELETORES_TABELA_RESULTADOS},
            )
        except:
            return ""

    def _fetch_manobra_geral(self, numero, link_param, view_state):
        payload = [
            ("AJAXREQUEST", "_viewRoot"),
            ("formManobra", "formManobra"),
            ("autoScroll", ""),
            ("javax.faces.ViewState", view_state or ""),
            ("idManobraParam", str(numero)),
            (link_param, link_param),
        ]
        body = urllib.parse.urlencode(payload)
        try:
            return self.page.evaluate(
                """async (args) => {
                    const res = await fetch(args.url, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8' },
                        body: args.body,
                        credentials: 'same-origin'
                    });
                    return { status: res.status, contentType: res.headers.get('content-type') || '', text: await res.text() };
                }""",
                {"url": URL_MANOBRA_GERAL, "body": body},
            )
        except:
            return None

    def _norm_txt(self, s):
        if s is None:
            return ""
        s = str(s)
        s = html_lib.unescape(s)
        s = s.replace("\xa0", " ")
        s = re.sub(r"\s+", " ", s).strip()
        if s == "-":
            return ""
        return s

    def _strip_tags(self, s):
        if not s:
            return ""
        return re.sub(r"<[^>]+>", "", s)

    def _parse_itens_from_html(self, html_text, filtro_alimentadores=None):
        filtro = set(filtro_alimentadores or [])
        usar_filtro = bool(filtro)
        tabelas = re.findall(r'(<table[^>]+id="[^"]*:itensCadastrados"[^>]*>.*?</table>)', html_text or "", flags=re.I | re.S)
        itens = []
        for t in tabelas:
            ths = re.findall(r"<th[^>]*>(.*?)</th>", t, flags=re.I | re.S)
            headers = [self._norm_txt(self._strip_tags(h)).lower() for h in ths]
            idx_equip = -1
            idx_alim = -1
            idx_local = -1
            for i, h in enumerate(headers):
                h2 = re.sub(r"[^\w]+", "", h)
                if idx_equip == -1 and ("eqpto" in h2 or "trafo" in h2):
                    idx_equip = i
                if idx_alim == -1 and ("alimen" in h2 or "subes" in h2):
                    idx_alim = i
                if idx_local == -1 and ("local" in h2):
                    idx_local = i
            if idx_equip == -1:
                idx_equip = 2
            if idx_alim == -1:
                idx_alim = 3
            if idx_local == -1:
                idx_local = 6

            tb = re.search(r"<tbody[^>]*>(.*?)</tbody>", t, flags=re.I | re.S)
            if not tb:
                continue
            tbody = tb.group(1)
            for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", tbody, flags=re.I | re.S):
                tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, flags=re.I | re.S)
                if not tds:
                    continue
                eq = self._norm_txt(self._strip_tags(tds[idx_equip] if idx_equip < len(tds) else ""))
                al = self._norm_txt(self._strip_tags(tds[idx_alim] if idx_alim < len(tds) else ""))
                lo = self._norm_txt(self._strip_tags(tds[idx_local] if idx_local < len(tds) else ""))
                if usar_filtro and al and al not in filtro:
                    continue
                if not eq and not al:
                    continue
                itens.append({"equipamento": eq, "alimentador": al, "local": lo})

        seen = set()
        unicos = []
        for it in itens:
            k = (it.get("equipamento", ""), it.get("alimentador", ""), it.get("local", ""))
            if k in seen:
                continue
            seen.add(k)
            unicos.append(it)
        return unicos

    def extrair_itens_manobra_por_numero_fast(self, numero, filtro_alimentadores=None):
        self.ir_para_busca_manobra()
        self.preparar_busca_por_numero()
        self._fill_primeiro_disponivel([SELETOR_CAMPO_NUMERO], str(numero))
        self.pesquisar(expected_num=numero)

        view_state = self._obter_view_state()
        if not view_state:
            return None
        link_param = self._obter_link_param_resultado_numero(numero)
        if not link_param:
            return None

        resp = self._fetch_manobra_geral(numero, link_param, view_state)
        if not resp or int((resp or {}).get("status") or 0) != 200:
            return None
        txt = (resp or {}).get("text") or ""
        if not txt:
            return None
        return self._parse_itens_from_html(txt, filtro_alimentadores=filtro_alimentadores)

    def _norm(self, v):
        if v is None:
            return ""
        v = str(v).strip()
        if v == "-":
            return ""
        return v

    def montar_criterios(self, itens):
        alims = set()
        equips = set()
        equips_locais = set()
        for it in itens:
            al = self._norm(it.get("alimentador"))
            eq = self._norm(it.get("equipamento"))
            lo = self._norm(it.get("local"))
            if al:
                alims.add(al)
            if eq:
                equips.add(eq)
            if eq and lo:
                equips_locais.add(f"{eq}|{lo}")
        return alims, equips, equips_locais


def main():
    usuario = os.getenv("GDIS_USUARIO", "")
    senha = os.getenv("GDIS_SENHA", "")

    inicio = time.time()
    t_login = None
    t_minha = None
    t_coleta = None
    t_verificacao = None
    app = VerificadorElaboradas()
    storage_state_path = None
    try:
        app.iniciar()
        ok = app.login(usuario, senha)
        if not ok:
            print("Login não realizado.")
            return
        t_login = time.time()

        listar_situacoes_env = (os.getenv("GDIS_LISTAR_SITUACOES", "0") or "").strip().lower()
        if listar_situacoes_env in {"1", "true", "yes", "y"}:
            situacoes = app.listar_situacoes_disponiveis()
            print("\nSITUAÇÕES DISPONÍVEIS:")
            if situacoes:
                for s in situacoes:
                    print(f"  - {s}")
            else:
                print("  (não consegui ler o combo de situação)")
            return
        try:
            fd, storage_state_path = tempfile.mkstemp(prefix="gdis_storage_", suffix=".json")
            os.close(fd)
            app.context.storage_state(path=storage_state_path)
        except:
            storage_state_path = None

        print(f"\n--- BUSCANDO MINHA MANOBRA: {MINHA_MANOBRA_ID} ---")
        fast_env = (os.getenv("GDIS_FAST_ENDPOINT", "1") or "").strip().lower()
        usar_fast = fast_env not in {"0", "false", "no", "n"}
        itens_minha = None
        if usar_fast:
            try:
                itens_minha = app.extrair_itens_manobra_por_numero_fast(MINHA_MANOBRA_ID)
            except:
                itens_minha = None

        if itens_minha is None:
            if not app.abrir_manobra_por_numero(MINHA_MANOBRA_ID):
                print("Manobra não encontrada.")
                return
            itens_minha = app.extrair_itens_manobra_aberta()
            app.voltar_para_busca()
        if itens_minha:
            print("    --- ITENS IDENTIFICADOS ---")
            for i, it in enumerate(itens_minha):
                print(f"    Item {i+1}: {it}")
            print("    ---------------------------")

        meus_alims, meus_equips, meus_equips_locais = app.montar_criterios(itens_minha)
        t_minha = time.time()

        print("\n==================================================")
        print("CRITÉRIOS DE RASTREAMENTO IDENTIFICADOS")
        print("==================================================")
        print(f"ALIMENTADORES ({len(meus_alims)}):")
        for a in sorted(meus_alims):
            print(f"  - {a}")
        print(f"\nEQUIPAMENTOS ({len(meus_equips)}):")
        for e in sorted(meus_equips):
            print(f"  - {e}")
        print("==================================================")

        excluir_env = (os.getenv("GDIS_EXCLUIR_MINHA", "1") or "").strip().lower()
        excluir_minha = excluir_env not in {"0", "false", "no", "n"}
        minha_exclusao = MINHA_MANOBRA_ID if excluir_minha else None

        situacoes_env = (os.getenv("GDIS_SITUACOES", "") or "").strip()
        if situacoes_env:
            situacoes = [s.strip() for s in situacoes_env.split(",") if s.strip()]
        else:
            situacao_env = (os.getenv("GDIS_SITUACAO", "") or "").strip()
            if situacao_env:
                situacoes = [situacao_env]
            else:
                situacoes = ["ELABORADA", "ENVIADA PARA O CONDIS"]
        situacoes_print = ", ".join([s for s in situacoes if s]) or "(todas)"

        print(f"\n--- COLETANDO MANOBRAS ({situacoes_print}) ({DATA_INICIO} a {DATA_FIM}) ---")
        ids = app.coletar_elaboradas(DATA_INICIO, DATA_FIM, minha_exclusao)
        print(f"Total encontradas: {len(ids)}")
        if len(ids) == 0:
            if excluir_minha and MINHA_MANOBRA_ID:
                print(f"Nenhuma para verificar em ({situacoes_print}) (ou só a sua própria manobra apareceu).")
                print("Para testar sem excluir a sua: defina GDIS_EXCLUIR_MINHA=0 e rode novamente.")
            else:
                print(f"Nenhuma para verificar em ({situacoes_print}) nesse período.")
        t_coleta = time.time()

        conflitos = []
        tentadas = 0
        verificadas = 0
        workers_env = (os.getenv("GDIS_WORKERS", "1") or "").strip()
        try:
            workers = int(workers_env)
        except:
            workers = 1
        if workers < 1:
            workers = 1

        force_parallel_env = (os.getenv("GDIS_FORCE_PARALLEL", "0") or "").strip().lower()
        force_parallel = force_parallel_env in {"1", "true", "yes", "y"}
        limite_paralelo = max(30, workers * 10)
        usar_paralelo = (workers > 1 and len(ids) >= limite_paralelo) or (force_parallel and workers > 1 and len(ids) > 0)

        if usar_paralelo:
            print(f"Modo verificação: paralelo ({workers} workers)")
            try:
                app.fechar()
            except:
                pass

            partes = _chunk_list(ids, workers)
            lista_alims = list(meus_alims)
            lista_equips = list(meus_equips)
            lista_equips_locais = list(meus_equips_locais)

            with ProcessPoolExecutor(max_workers=workers) as executor:
                futures = [
                    executor.submit(
                        _worker_verificar,
                        p,
                        usuario,
                        senha,
                        storage_state_path,
                        lista_alims,
                        lista_equips,
                        lista_equips_locais,
                    )
                    for p in partes
                    if p
                ]
                for fut in futures:
                    res = fut.result()
                    conflitos.extend((res or {}).get("conflitos") or [])
                    try:
                        tentadas += int((res or {}).get("tentadas") or 0)
                        verificadas += int((res or {}).get("verificadas") or 0)
                    except:
                        pass
        else:
            if workers > 1 and len(ids) > 0:
                print(f"Modo verificação: sequencial (paralelo só a partir de {limite_paralelo} manobras)")
            total = len(ids)
            fast_env = (os.getenv("GDIS_FAST_ENDPOINT", "1") or "").strip().lower()
            usar_fast = fast_env not in {"0", "false", "no", "n"}
            for i, num in enumerate(ids, start=1):
                tentadas += 1
                print(f"[{i}/{total}] Verificando manobra {num}...")
                criterios = None
                if usar_fast:
                    try:
                        itens = app.extrair_itens_manobra_por_numero_fast(num, filtro_alimentadores=meus_alims)
                        if itens is not None:
                            al, eq, eql = app.montar_criterios(itens)
                            criterios = {
                                "alimentadores": sorted(al),
                                "equipamentos": sorted(eq),
                                "equipamentos_locais": sorted(eql),
                            }
                    except:
                        criterios = None

                if criterios is None:
                    if not app.abrir_manobra_por_numero(num):
                        continue
                    try:
                        criterios = app.extrair_criterios_manobra_aberta(filtro_alimentadores=meus_alims)
                    finally:
                        app.voltar_para_busca()
                verificadas += 1

                alims = set((criterios or {}).get("alimentadores") or [])
                equips = set((criterios or {}).get("equipamentos") or [])
                equips_locais = set((criterios or {}).get("equipamentos_locais") or [])

                inter_alim = meus_alims.intersection(alims)
                if not inter_alim:
                    continue

                inter_eq = meus_equips.intersection(equips)
                inter_eq_loc = meus_equips_locais.intersection(equips_locais)
                if not inter_eq and not inter_eq_loc:
                    continue

                conflitos.append(
                    {
                        "manobra": num,
                        "alimentadores": sorted(inter_alim),
                        "equipamentos": sorted(inter_eq),
                        "equipamentos_locais": sorted(inter_eq_loc),
                    }
                )

        t_verificacao = time.time()
        fim = time.time()
        print("\n" + "=" * 50)
        print("RELATÓRIO FINAL")
        print(f"Tempo Total: {time.strftime('%H:%M:%S', time.gmtime(fim - inicio))}")
        print(f"Manobras tentadas: {tentadas}")
        print(f"Manobras verificadas: {verificadas}")
        print(f"Conflitos encontrados: {len(conflitos)}")
        try:
            if t_login:
                print(f"Tempo login: {time.strftime('%H:%M:%S', time.gmtime(t_login - inicio))}")
            if t_minha and t_login:
                print(f"Tempo minha manobra: {time.strftime('%H:%M:%S', time.gmtime(t_minha - t_login))}")
            if t_coleta and t_minha:
                print(f"Tempo coleta manobras: {time.strftime('%H:%M:%S', time.gmtime(t_coleta - t_minha))}")
            if t_verificacao and t_coleta:
                print(f"Tempo verificação: {time.strftime('%H:%M:%S', time.gmtime(t_verificacao - t_coleta))}")
        except:
            pass
        print("=" * 50)

        if conflitos:
            for c in conflitos:
                print(f"[PERIGO] Manobra {c['manobra']}")
                print(f"         Alimentadores: {c['alimentadores']}")
                if c["equipamentos"]:
                    print(f"         Equipamentos: {c['equipamentos']}")
                if c["equipamentos_locais"]:
                    print(f"         Equipamentos/Locais: {c['equipamentos_locais']}")
                print("-" * 20)
        else:
            print("Nenhum conflito encontrado.")
    finally:
        try:
            app.fechar()
        except:
            pass
        if storage_state_path:
            try:
                os.remove(storage_state_path)
            except:
                pass


if __name__ == "__main__":
    main()
