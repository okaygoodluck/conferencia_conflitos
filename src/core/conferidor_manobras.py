import os
import re
import getpass
import threading
from playwright.sync_api import sync_playwright

class Colors:
    """Códigos de cores ANSI para o terminal"""
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def print_regra(regra_id, nivel, mensagem, log_func=print):
    """Exibe a mensagem da regra formatada com cores e ícones compatíveis com o Dashboard"""
    prefixos = {
        "ERRO": f"{Colors.RED}❌ REGRA {regra_id:02d} [FALHA]:{Colors.RESET}",
        "ALERTA": f"{Colors.YELLOW}⚠️ REGRA {regra_id:02d} [ALERTA]:{Colors.RESET}",
        "OK": f"{Colors.GREEN}✅ REGRA {regra_id:02d} [OK]:{Colors.RESET}",
        "INFO": f"{Colors.BLUE}🔵 REGRA {regra_id:02d} [INFO]:{Colors.RESET}"
    }
    # Se for uma lista de mensagens, imprime cada uma
    if isinstance(mensagem, (list, set)):
        for msg in mensagem:
            log_func(f"   {prefixos.get(nivel, '')} {msg}")
    else:
        log_func(f"   {prefixos.get(nivel, '')} {mensagem}")

# Trava global para evitar que múltiplas threads escrevam no arquivo de cache simultaneamente
_CACHE_LOCK = threading.Lock()

URL_LOGIN = "http://gdis-pm/gdispm/"

"""
REGRAS DO CONFERIDOR DE MANOBRAS IMPLEMENTADAS (1 a 42):
01. Equipamento da Solicitação presente na Manobra
02. Ação Inicial (Abrir/Sinalizar) para equipamentos da Solicitação
03. Alimentador (Manobra vs Solicitação)
04. Local (Manobra vs Solicitação)
05. Bloqueio de RA (Exigência vs Presença de Macros MA52/MA14/MA28)
06. Incompatibilidade de Ação pelo Prefixo do Equipamento
07. Modo Local (MA64) obrigatório para Telecontrolados
08. Macros exclusivas de Reguladores de Tensão (RT)
09. Macros de operação de Religador/Disjuntor
10. Bloqueio/Desbloqueio de Chave Deslocada
11. Alteração de Ajustes de Proteção (Prefixos permitidos)
12. Posicionamento (MA30/MA67) p/ Região (Aviso se TERCEIROS)
13. Abertura sem sinalização pela Região (MA01 sem CORTE DE CARGA)
14. Posicionamento proibido para o executor COD
15. COD só opera equipamentos telecontrolados e permitidos
16. Etapa 'VERIFICACAO PELO COD' exclusiva para o executor COD
17. Verificação de Anormalidade (MA09) vs By-pass
18. Comandos de By-pass (Prefixos permitidos)
19. Macro MAC1 exclusiva para equipamentos físicos (não alimentador)
20. Observação obrigatória para Troca de Elo e Mudança de TAP
21. Anti-Placeholder (Evitar textos genéricos como AAA)
22. Equilíbrio de Ações Inversas e Cronologia de Bloqueios
23. Uso de Gerador (GMT/GBT declarado na Solicitação/Etapa)
24. Validações de Cabeçalho (CI, EQUIPES, GMT, etc.)
25. Horários Repetidos entre Etapas
26. Datas e Horários coerentes por Equipamento
27. Coerência do Executor (Supervisor em D/R; COD 'Para Refletir')
28. Duplicidades de Ação na mesma Etapa
29. Verificação de Anormalidade por Alimentador
30. Ordem Cronológica de Ações (Abrir -> Manobrar -> Fechar)
31. Coerência de POSOPE e Sincronismo Inicial (MA39/MA49)
32. Compatibilidade de Fases (Trifásico vs Monofásico)
33. Chave ASTA (MA30) exige indicação 'COM CARGA'
34. Compatibilidade da macro MAB9 com Prefixo
35. Validação de Equipes no Cabeçalho vs Executor Região
36. Sincronismo de Horário entre Itens e Cabeçalho da Etapa
37. Macro MA60 (Aviso de Telecontrole) exclusiva do COD
38. Equipamentos Manuais operados pela Região
39. Posicionamento (Sim) restrito a Abertura/Fechamento pela Região
40. Aviso de Risco Sistema (Citação de risco no texto)
41. Macro MA63 (Troca de Elo) exclusiva para executor Região
42. Sinalização Pré-Desligamento (MA01 deve ter MA06 até o Desligamento)
"""

def _norm_eqpto(s):
    """Normaliza o número do equipamento para garantir que a comparação seja justa (ex: 24-123 vira 24 - 123)"""
    s = re.sub(r"\s+", " ", (s or "")).strip()
    s = re.sub(r"\s*-\s*", " - ", s)
    return s

def _norm_str(s):
    """Normaliza strings genéricas removendo espaços extras, acentos e capitalizando"""
    if not s: return ""
    import unicodedata
    s = re.sub(r"\s+", " ", str(s)).strip().upper()
    return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')

def _re_macro(m):
    r"""Constrói regex para detectar a macro 'm' no texto, excluindo variantes 'MA18 - Outros'.
    O lookahead negativo (?!\s*-\s*OUTROS) garante que 'MA18 - OUTROS' não seja confundido
    com o código de ação MA18 (ABRIR E SINALIZAR DISJUNTOR/RELIGADOR)."""
    return r'\b\d*' + re.escape(m) + r'\b(?!\s*-\s*OUTROS)'

def _get_eq_id(eq):
    """Extrai o ID real do equipamento, lidando com prefixos e sufixos de transformadores."""
    if not eq or eq == '-': return ""
    parts = [p.strip() for p in eq.split('-')]
    if len(parts) == 1: return parts[0]
    
    # Caso especial: Transformadores ID - Fases - kVA (ex: 191234 - 3 - 75)
    # Se a primeira parte tem 5 ou 6 dígitos, ela é o ID
    if len(parts[0]) >= 5 and parts[0].isdigit():
        return parts[0]
    
    # Caso padrão: Prefixo - ID (ex: 22 - 313300 ou 28 - 12345)
    # Se a primeira parte é curta (prefixo de 2-3 dígitos) e a segunda é longa, a segunda é o ID
    if len(parts) >= 2 and len(parts[1]) >= 4:
        return parts[1]
        
    # Fallback: se houver apenas um hífen e a primeira parte for curta, pega a segunda
    if len(parts) == 2 and len(parts[0]) <= 3:
        return parts[1]
        
    # Último caso: pega a última parte (comportamento original)
    return parts[-1]

def _get_eq_data(dados, eq, alim1, alim2="", local=""):
    """Busca os dados do equipamento resolvendo conflitos pelo NUMERO-LOCAL ou Alimentador"""
    
    num_only = _get_eq_id(eq)
    lista = []
    
    # 1. TENTA POR NUMERO-LOCAL (Mais específico)
    if local:
        local_fixed = str(local).strip()
        if local_fixed and not local_fixed.startswith('8'): 
            local_fixed = '8' + local_fixed
        
        key_local = f"{num_only}-{local_fixed}"
        if key_local in dados:
            lista = dados[key_local]

    # 2. TENTA POR NOME COMPLETO (Ex: 22 - 123456)
    if not lista:
        lista = dados.get(eq)
    
    # 3. TENTA POR NÚMERO SEM PREFIXO (Ex: 123456)
    if not lista and '-' in eq:
        sem_prefixo = eq.split('-', 1)[1].strip()
        lista = dados.get(sem_prefixo)
        
    if not lista: return {}
    
    # --- DESEMPATE UNIVERSAL ---
    if isinstance(lista, dict): lista = [lista] 
    if len(lista) == 1: 
        # print(f"      [DEBUG EQ] Único candidato para {eq}: {lista[0].get('alimentador')} | Local: {lista[0].get('numero_local')}")
        return lista[0]
    
    a1 = _norm_alim_match(alim1)
    a2 = _norm_alim_match(alim2)
    
    # print(f"      [DEBUG EQ] Múltiplos candidatos ({len(lista)}) para {eq}. Alvos norm: {a1} / {a2}")
    
    if a1:
        for item in lista:
            alims_item = item.get('alimentadores') or [item.get('alimentador')]
            for alim_orig in alims_item:
                if _norm_alim_match(alim_orig) == a1: return item
    if a2:
        for item in lista:
            alims_item = item.get('alimentadores') or [item.get('alimentador')]
            for alim_orig in alims_item:
                if _norm_alim_match(alim_orig) == a2: return item
            
    # Último caso: Retorna o primeiro da lista de candidatos detectados
    # print(f"      [DEBUG EQ] Nenhum alimentador casou. Retornando primeiro da lista: {lista[0].get('alimentador')}")
    return lista[0]

def _obter_parametros_conferidor():
    """Dicionário de equipamentos e ações PROIBIDAS para cada prefixo (Sincronizado com Excel)"""
    return {
        "01": ["MA64","MA65", "MA35","MA36", "MA77", "MAB9"], # TRANSFORMADOR DE DISTRIBUICAO (Chave Repetidora 01 c/ Obs)
        "02": [], # REGULADOR DE TENSAO (Tudo permitido)
        "03": ["MA64","MA65", "MA35","MA36", "MA77", "MAB9"], # CHAVE BYPASS
        "04": ["MA64","MA65", "MA35","MA36", "MA77", "MAB9"], # CHAVE FUSIVEL REPETIDORA MT
        "11": ["MA64","MA65", "MA35","MA36", "MA77", "MAB9"], # CH SECC. MT TRIP. OP. S/CARGA
        "13": ["MA64","MA65", "MAB9"], # BANCO CAPACITORES
        "15": ["MA64","MA65", "MAB9"], # TRAFO MT AUTO-PROTEGIDO
        "19": ["MA35","MA36", "MA77", "MA64", "MA65"], # CHAVE SECCIONADORA MT SF6 C.R.
        "20": ["MA35","MA36", "MA77", "MA64", "MA65"], # CHAVE SECCIONADORA MT SF6
        "21": ["MA35","MA36", "MA77"], # DISJUNTOR
        "22": ["MA35","MA36", "MA77"], # RELIGADOR 
        "23": ["MA35","MA36", "MA77"], # SECCIONALIZADOR CONVENCIONAL
        "24": ["MA35","MA36", "MA77", "MA64", "MA65", "MAB9"], # CHAVE FUSIVEL MT DERIVACAO 
        "27": ["MA35","MA36", "MA77", "MA64", "MA65", "MAB9"], # CH SECC. MT TRIP.OP. EM CARGA
        "28": ["MA64","MA65", "MA35","MA36", "MA77", "MAB9"], # CHAVE SECCIONADORA MT UNIP.
        "30": ["MA64","MA65", "MA35","MA36", "MA77", "MAB9"], # TRAFO MT CONVENCIONAL
        "34": ["MA64","MA65", "MA35","MA36", "MA77", "MAB9"], # CHAVE A VACUO
        "36": ["MA64","MA65", "MA35","MA36", "MA77", "MAB9"], # CHAVE FACA ADAPTADA
        "50": ["MA64","MA65", "MA35","MA36", "MA77", "MAB9"], # SECCIONAMENTO OPERATIVO
        "60": ["MA64","MA65", "MA35","MA36", "MA77", "MAB9"], # CH MANOBRA SUB
        "61": ["MA64","MA65", "MA35","MA36", "MA77", "MAB9"], # CH PROTECAO SUB
    }

def _carregar_dados_equipamentos(log_func=print):
    """Lê o arquivo CSV de equipamentos e retorna um dicionário"""
    import json
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    caminho_csv_local = os.path.join(root_dir, "data", "equipamentos_gemini.csv")
    caminho_csv_rede = r"I:\IT\ODCO\PROGRAMACAO_MT\1 - Sistemas da programação\Data_Gemini\equipamentos_gemini.csv"
    
    # Prioriza o caminho de rede para garantir centralização, fallback para local se rede inacessível
    if os.path.exists(caminho_csv_rede):
        caminho_csv = caminho_csv_rede
    else:
        caminho_csv = caminho_csv_local
    
    dados = {}
    if not os.path.exists(caminho_csv):
        log_func(f"[AVISO] Arquivo CSV não encontrado (Regras do Conferidor 7, 31 e 32 ignoradas):\n   {caminho_csv}")
        return dados
        
    try:
        import pandas as pd
        # Tenta ler com separador ponto e vírgula e encoding comum no Brasil (caso gerado pelo Excel)
        try:
            df = pd.read_csv(caminho_csv, sep=';', encoding='latin1', dtype=str)
        except:
            df = pd.read_csv(caminho_csv, sep=',', encoding='utf-8', dtype=str)
            
        df.fillna('', inplace=True)
            
        col_tele = next((c for c in df.columns if 'TELECONTROLADO' in str(c).upper()), None)
        col_eqpto = next((c for c in df.columns if str(c).upper() in ['EQUIPAMENTO', 'CODIGO', 'NUMERO', 'CÓDIGO', 'EQPTO']), None)
        col_posope = next((c for c in df.columns if 'POSOPE' in str(c).upper() or 'ESTADO' in str(c).upper()), None)
        col_fases = next((c for c in df.columns if 'FASES' in str(c).upper() or 'FASE' in str(c).upper()), None)
        cols_alim = [c for c in df.columns if 'ALIMENTADOR' in str(c).upper() or 'REFALM' in str(c).upper()]
        col_num_local = next((c for c in df.columns if 'NUMERO-LOCAL' in str(c).upper()), None)
        
        if not col_eqpto and len(df.columns) > 0:
            col_eqpto = df.columns[0] # Fallback para a primeira coluna
            
        if col_eqpto:
            vals_eqpto = df[col_eqpto].values
            vals_tele = df[col_tele].values if col_tele else [''] * len(df)
            vals_posope = df[col_posope].values if col_posope else [''] * len(df)
            vals_fases = df[col_fases].values if col_fases else [''] * len(df)
            vals_num_local = df[col_num_local].values if col_num_local else [''] * len(df)
            
            # Lista de arrays de alimentadores
            vals_alims = [df[c].values for c in cols_alim]
            
            # zip é imensamente mais rápido que iterrows
            for row_idx in range(len(df)):
                eq_val = vals_eqpto[row_idx]
                t_val = vals_tele[row_idx]
                p_val = vals_posope[row_idx]
                f_val = vals_fases[row_idx]
                nl_val = vals_num_local[row_idx]
                
                # Coleta todos os alimentadores das colunas candidatas
                alim_vals = []
                for v_arr in vals_alims:
                    v = str(v_arr[row_idx]).strip().upper()
                    if v: alim_vals.append(v)
                
                eq = _norm_eqpto(str(eq_val))
                tele = str(t_val).strip().upper() == 'T'
                posope = str(p_val).strip().upper()
                fases = str(f_val).strip().upper()
                num_local = str(nl_val).strip().upper()
                
                record = {
                    'telecontrolado': tele,
                    'posope': posope,
                    'fases': fases,
                    'alimentadores': alim_vals, # Agora é uma lista
                    'numero_local': num_local
                }
                
                # Indexa pela chave principal (equipamento)
                if eq not in dados: dados[eq] = []
                dados[eq].append(record)
                
                # Indexa também pelo NUMERO-LOCAL caso disponível
                if num_local:
                    if num_local not in dados: dados[num_local] = []
                    dados[num_local].append(record)
                
                # Indexa também pelo NUMERO-LOCAL caso disponível
                if num_local:
                    if num_local not in dados: dados[num_local] = []
                    dados[num_local].append(record)
                    
    except Exception as e:
        log_func(f"[AVISO] Erro ao carregar dados do CSV: {e}")
        
    return dados



def main(manobra_param=None, usuario_param=None, senha_param=None, headless=False, log_func=print, dados_equipamentos_cache=None):
    # Sombreamento local para isolar logs por thread sem alterar 2000 linhas de código
    _global_print_regra = globals()['print_regra']
    def print_regra(regra_id, nivel, mensagem):
        _global_print_regra(regra_id, nivel, mensagem, log_func=log_func)
    
    def print(*args, **kwargs):
        # Se for o print do sistema, não fazemos nada para evitar travar o terminal do servidor
        import builtins
        if log_func == getattr(builtins, 'print', None):
            return
        log_func(*args, **kwargs)

    print("=====================================================")
    print("      VERIFICADOR DE MANOBRAS (Regras do Conferidor 1 a 43)        ")
    print("=====================================================")
    
    manobra_num = manobra_param if manobra_param else input("Digite o número da Manobra Base: ").strip()
    if not manobra_num:
        print("Número inválido.")
        return

    usuario = usuario_param if usuario_param else ((os.getenv("GDIS_USUARIO") or "").strip() or input("Usuário: ").strip())
    senha = senha_param if senha_param else ((os.getenv("GDIS_SENHA") or "").strip() or getpass.getpass("Senha: "))

    if dados_equipamentos_cache is not None:
        dados_equipamentos = dados_equipamentos_cache
        print("[OK] Base de equipamentos carregada do cache.")
    else:
        print("\n[INFO] Carregando base de equipamentos... (O primeiro acesso pode levar alguns segundos)")
        dados_equipamentos = _carregar_dados_equipamentos(log_func=log_func)
        print("[OK] Base carregada com sucesso!")
    
    parametros_conferidor = _obter_parametros_conferidor()

    print("\n[1] Iniciando navegador...")
    import tempfile
    
    with sync_playwright() as p:
        caminhos = [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        ]
        executavel = next((c for c in caminhos if os.path.exists(c)), None)
        
        # launch() básico com flags de estabilidade costuma ser mais resiliente que persistent_context no Windows Server
        browser = p.chromium.launch(
            executable_path=executavel,
            headless=headless,
            args=[
                "--disable-dev-shm-usage", 
                "--no-sandbox", 
                "--disable-gpu",
                "--disable-software-rasterizer",
                "--mute-audio",
                "--disable-extensions",
                "--disable-setuid-sandbox"
            ]
        )
        
        context = browser.new_context(viewport={'width': 1280, 'height': 800})
        page = context.new_page()

        try:
            print("    Fazendo login...")
            page.goto(URL_LOGIN)
            if page.locator("input[id='formLogin:userid']").count() > 0:
                page.fill("input[id='formLogin:userid']", usuario)
                page.fill("input[id='formLogin:password']", senha)
                page.click("input[id='formLogin:botao']")
                page.wait_for_selector("input[id='formLogin:userid']", state="detached")
        except Exception:
            try: page.close()
            except Exception: pass
            try: context.close()
            except Exception: pass
            try: browser.close()
            except Exception: pass
            raise

        # ============================================================
        # ETAPA A: EXTRAIR MANOBRA
        # ============================================================
        print("\n[2] Abrindo a Manobra para extração de dados...")
        page.click("text=Consultas")
        page.click("text=Manobra")
        page.wait_for_selector("input[id='formPesquisa:numeroManobra']", timeout=20000)

        page.fill("input[id='formPesquisa:numeroManobra']", manobra_num)
        
        # Limpa as datas para pesquisar especificamente o número
        page.evaluate("""() => {
            const dIni = document.getElementById('formPesquisa:dataInicioInputDate');
            const dFim = document.getElementById('formPesquisa:dataTerminioInputDate') || document.getElementById('formPesquisa:dataTerminoInputDate');
            if (dIni) dIni.value = '';
            if (dFim) dFim.value = '';
        }""")

        page.click("input[id='formPesquisa:j_id109']") # Botão pesquisar
        page.wait_for_selector("table[id*='resulPesManobra']", timeout=15000)
        page.wait_for_timeout(2000)

        # Pega a Solicitação Vinculada na tabela
        print("    Buscando número da Solicitação...")
        solicitacao_num = page.evaluate(f"""(manobra) => {{
            try {{
                const tabela = document.querySelector("table[id*='resulPesManobra']");
                if (!tabela) return null;
                const ths = Array.from(tabela.querySelectorAll('thead th'));
                if (!ths.length) return null;
                const headers = ths.map(th => (th.innerText || '').toLowerCase());
                const idxM = headers.findIndex(h => h.includes('manobra'));
                const idxS = headers.findIndex(h => h.includes('solicita') || h.includes('vinc'));
                if (idxM < 0 || idxS < 0) return null;
                const rows = Array.from(tabela.querySelectorAll('tbody tr'));
                for (const r of rows) {{
                    if (!r) continue;
                    const tds = r.querySelectorAll('td');
                    if (tds.length > Math.max(idxM, idxS)) {{
                        const mVal = (tds[idxM].innerText || '').replace(/\\D/g, '');
                        if (mVal === String(manobra)) {{
                            return (tds[idxS].innerText || '').replace(/\\D/g, '');
                        }}
                    }}
                }}
            }} catch(e) {{}}
            return null;
        }}""", manobra_num)

        if not solicitacao_num:
            print("    [ERRO] Não achei o número da Solicitação vinculada. Verifique a manobra informada.")
            return

        # Abre o detalhe da manobra
        print(f"    Abrindo detalhes da Manobra {manobra_num}...")
        page.evaluate(f"""(num) => {{
            const links = Array.from(document.querySelectorAll("table[id*='resulPesManobra'] a"));
            const link = links.find(l => (l.innerText || '').includes(String(num)));
            if (link) link.click();
        }}""", manobra_num)
        page.wait_for_selector("div[id*='etapasManobraSimplePanelId']", timeout=25000)
        
        # Extrai metadados do cabeçalho da Manobra (Título/Finalidade)
        manobra_header_metadata = page.evaluate("""() => {
            const labels = Array.from(document.querySelectorAll('label, span, td.label'));
            let meta = "";
            for (const l of labels) {
                const txt = (l.textContent || "").toUpperCase();
                if (txt.includes("TITULO") || txt.includes("FINALIDADE") || txt.includes("DESCRICAO")) {
                    const val = l.nextElementSibling ? l.nextElementSibling.textContent : "";
                    meta += " " + txt + ": " + val;
                }
            }
            return meta.toUpperCase();
        }""")

        # Expande painéis da manobra
        page.evaluate("""() => {
            document.querySelectorAll("div[id$='itensManobraSimplePanelId_header']").forEach(h => {
                const b = document.getElementById(h.id.replace('_header', '_body'));
                if (b && (b.style.display === 'none' || b.style.display === '')) { h.click(); }
            });
        }""")
        page.wait_for_timeout(4000) # Espera o AJAX carregar tabelas de etapas

        # Extrai o texto completo das etapas da manobra para buscar macros
        manobra_texto_etapas = page.evaluate("""() => {
            const root = document.querySelector("div[id*='etapasManobraSimplePanelId']");
            return root ? root.textContent || '' : '';
        }""")

        # Extrator universal extremamente robusto (Lida com tabelas paralelas do JSF)
        JS_EXTRACT_RA = r"""() => {
            try {
                const clean = (s) => (s || '').replace(/[\s\xA0]+/g, ' ').trim().toUpperCase();
                const norm = (s) => (s || '').toLowerCase().replace(/[\s\xA0]+/g, ' ').trim();
                
                const targets = ['bloqueio de ra', 'bloqueio de ra:', 'ra', 'ra:'];
                const cells = Array.from(document.querySelectorAll('td, th, span, label, div'));
                
                for (const cell of cells) {
                    if (!cell) continue;
                    const text = norm(cell.textContent);
                    if (targets.includes(text)) {
                        const tr = cell.closest('tr');
                        if (tr) {
                            const table = tr.closest('table');
                            
                            // 1. JSF Parallel Tables (h:panelGrid)
                            if (table) {
                                const tableRows = Array.from(table.querySelectorAll('tr'));
                                const rowIdx = tableRows.indexOf(tr);
                                const parentTd = table.closest('td');
                                if (parentTd && parentTd.nextElementSibling) {
                                    const siblingTable = parentTd.nextElementSibling.querySelector('table');
                                    if (siblingTable) {
                                        const siblingRows = Array.from(siblingTable.querySelectorAll('tr'));
                                        if (rowIdx >= 0 && rowIdx < siblingRows.length && siblingRows[rowIdx]) {
                                            const v = clean(siblingRows[rowIdx].textContent);
                                            if (/\bSIM\b/.test(v)) return 'SIM';
                                            if (/\bN[AÃ]O\b/.test(v)) return 'NAO';
                                        }
                                    }
                                }
                            }
                            
                            // 2. Normal Table / Next Column
                            const cellTd = cell.closest('td, th');
                            if (cellTd) {
                                const cellIdx = Array.from(tr.children).indexOf(cellTd);
                                if (cellIdx >= 0 && cellIdx + 1 < tr.children.length && tr.children[cellIdx + 1]) {
                                    const v = clean(tr.children[cellIdx + 1].textContent);
                                    if (/\bSIM\b/.test(v)) return 'SIM';
                                    if (/\bN[AÃ]O\b/.test(v)) return 'NAO';
                                }
                            }
                        }
                        
                        // 3. Fallback de proximidade de texto bruto na mesma celula
                        const parentText = cell.parentElement ? cell.parentElement.textContent : cell.textContent;
                        const rawCell = clean(parentText);
                        if (/BLOQUEIO DE RA[\s\:\-\|]+\bSIM\b/.test(rawCell) || /\bRA[\s\:\-\|]+\bSIM\b/.test(rawCell)) return 'SIM';
                        if (/BLOQUEIO DE RA[\s\:\-\|]+\bN[AÃ]O\b/.test(rawCell) || /\bRA[\s\:\-\|]+\bN[AÃ]O\b/.test(rawCell)) return 'NAO';
                    }
                }
            } catch(e) {}
            return null;
        }"""

        # Extrai campo "RA: Sim/Não" direto da tela da Manobra como fallback
        manobra_ra_texto = page.evaluate(JS_EXTRACT_RA)

        # Extrai equipamentos e o texto da linha (para achar a ação)
        print("    Extraindo equipamentos e ações da Manobra...")
        manobra_dados = page.evaluate("""() => {
            const norm = (s) => (s || '').normalize('NFD').replace(/[\\u0300-\\u036f]/g, '').toLowerCase().replace(/\\s+/g, ' ').trim();
            const clean = (s) => {
                let res = (s || '').replace(/[\\s\\xA0]+/g, ' ').trim();
                res = res.replace(/SimpleTogglePanelManager\\.add\\(new SimpleTogglePanel\\(.*?\\)\\s*\\);?/gi, '');
                res = res.replace(/[«»]/g, '');
                return res.replace(/\\s+/g, ' ').trim();
            };
            
            const tables = Array.from(document.querySelectorAll("table[id$=':itensCadastrados']"));
            const resultado = [];
            
            for (const tabela of tables) {
                if (!tabela) continue;
                let etapaNome = "";
                let etapaTextoHeader = "";
                const bodyDiv = tabela.closest("div[id$='_body']");
                if (bodyDiv) {
                    const headerDiv = document.getElementById(bodyDiv.id.replace('_body', '_header'));
                    if (headerDiv) {
                        etapaNome = clean(headerDiv.textContent || '');
                    }
                }
                
                const tableId = tabela.id || '';
                const matchPrefix = tableId.match(/^(.*:\\d+:)/);
                if (matchPrefix) {
                    const prefix = matchPrefix[1];
                    const trs = Array.from(document.querySelectorAll('tr.backgroundCinza'));
                    for (const tr of trs) {
                        const firstTd = tr.querySelector('td');
                        if (firstTd && firstTd.id && firstTd.id.startsWith(prefix)) {
                            const trText = Array.from(tr.querySelectorAll('td, th')).map(c => c.textContent.trim()).join(' ');
                            etapaTextoHeader += ' ' + trText;
                        }
                    }
                }
                
                if (!etapaTextoHeader.trim()) {
                    const etapaCandidates = Array.from(document.querySelectorAll('tr, div[class*="header"]'));
                    let bestHeader = '';
                    for (const cand of etapaCandidates) {
                        const c = cand.className || '';
                        const txt = cand.textContent || '';
                        if (c.includes('backgroundCinza') || txt.includes('Etapa:')) {
                            if (txt.length < 300 && (cand.compareDocumentPosition(tabela) & Node.DOCUMENT_POSITION_FOLLOWING)) {
                                let candText = '';
                                if (cand.tagName === 'TR') {
                                    const tds = Array.from(cand.querySelectorAll('td, th'));
                                    if (tds.length) candText = tds.map(cel => cel.textContent.trim()).join(' ');
                                    else candText = txt.replace(/[\\s\\xA0]+/g, ' ').trim();
                                } else {
                                    candText = txt.replace(/[\\s\\xA0]+/g, ' ').trim();
                                }
                                candText = candText.replace(/[\\s\\xA0]+/g, ' ').trim();
                                if (candText.length >= 5 && (candText.includes('Etapa') || candText.includes('ETAPA'))) {
                                    bestHeader = candText;
                                } else if (candText.length > 10 && c.includes('backgroundCinza')) {
                                    bestHeader = candText;
                                }
                            }
                        }
                    }
                    etapaTextoHeader = bestHeader || 'ETAPA DESCONHECIDA';
                }
                
                etapaTextoHeader = clean(etapaTextoHeader);
                
                const ths = Array.from(tabela.querySelectorAll('thead tr:first-child th'));
                const headers = ths.map(th => norm(th.textContent || ''));
                
                let idxAcao = headers.findIndex(h => h.includes('ação') || h.includes('acao') || h.includes('macro'));
                let idxEqpto = headers.findIndex(h => h.includes('eqpto') || h.includes('trafo') || h.includes('equipamento'));
                let idxAlim = headers.findIndex(h => h.includes('alimen') || h.includes('subes'));
                let idxLocal = headers.findIndex(h => h === 'local' || h.includes('local'));
                let idxExec = headers.findIndex(h => h.includes('executor') || h.includes('órgão') || h.includes('orgao') || h.includes('execu'));
                let idxPosic = headers.findIndex(h => h.includes('posicionamento') || h.includes('posic'));
                let idxObs = headers.findIndex(h => h.includes('observação') || h.includes('observacao') || h.includes('obs'));
                let idxData = headers.findIndex(h => h.includes('data') || h.includes('hora'));
                
                const rows = Array.from(tabela.querySelectorAll('tr'));
                let currentEtapaLocal = etapaTextoHeader;
                
                for (const row of rows) {
                    const c = row.className || '';
                    const textContent = row.textContent || '';
                    if (c.includes('backgroundCinza') || c.includes('ui-rowgroup-header') || c.includes('ui-widget-header') || textContent.includes('Etapa:')) {
                        if (textContent.length < 500) {
                            const rowText = Array.from(row.querySelectorAll('td, th')).map(x => x.textContent.trim()).join(' ');
                            const trClean = clean(rowText);
                            if (trClean && !trClean.includes('Operacional') && !trClean.includes('Ação') && !trClean.includes('Eqpto')) {
                                currentEtapaLocal = trClean;
                            }
                        }
                    }
                    
                    const tds = row.querySelectorAll('td');
                    if (tds.length > 3) {
                        const a_mac = (idxAcao >= 0 && tds.length > idxAcao) ? clean(tds[idxAcao].textContent || '') : '';
                        const v = (idxEqpto >= 0 && tds.length > idxEqpto) ? clean(tds[idxEqpto].textContent || '') : '';
                        const a = (idxAlim >= 0 && tds.length > idxAlim) ? clean(tds[idxAlim].textContent || '') : '';
                        const l = (idxLocal >= 0 && tds.length > idxLocal) ? clean(tds[idxLocal].textContent || '') : '';
                        const ex = (idxExec >= 0 && tds.length > idxExec) ? clean(tds[idxExec].textContent || '') : '';
                        const po = (idxPosic >= 0 && tds.length > idxPosic) ? clean(tds[idxPosic].textContent || '') : '';
                        const ob = (idxObs >= 0 && tds.length > idxObs) ? clean(tds[idxObs].textContent || '') : '';
                        const dt = (idxData >= 0 && tds.length > idxData) ? clean(tds[idxData].textContent || '') : '';
                        resultado.push({
                            etapa_nome: etapaNome,
                            etapa_texto_header: currentEtapaLocal,
                            equipamento: v,
                            alimentador: a,
                            local: l,
                            executor: ex,
                            posicionamento: po,
                            observacao: ob,
                            data_hora: dt,
                            acao_bruta: a_mac,
                            texto_linha: clean(Array.from(tds).map(td => td.textContent.trim()).join(' ')).toLowerCase()
                        });
                    }
                }
            }
            return resultado;
        }""")

        # ============================================================
        # ETAPA A.1: RECONSTRUÇÃO LÓGICA DE BLOCOS (Contorno de DOM)
        # ============================================================
        # Como o GDIS envelopa etapas em painéis JSF, usamos a sequência numérica literal.
        bloco_atual = 1
        ultimo_n = -1
        for mi in manobra_dados:
            n = ultimo_n + 10
            # Pega o número real da coluna Nº caso exista no texto (ex: "10 MA31... ")
            partes = mi.get('texto_linha', '').split()
            if partes and partes[0].isdigit():
                n = int(partes[0])
            
            # Se a numeração reinicia/cai, entramos em num novo bloco visual de Etapa
            if n <= ultimo_n:
                bloco_atual += 1
            
            header_str = (mi.get('etapa_texto_header', '') or '')[:100]
            if header_str in ['', '«»ITENS', 'ERRO_CANDIDATOS_VAZIOS_OU_INVISIVEIS']:
                mi['grupo_id'] = f"{mi.get('etapa_nome', '')} | Bloco_Cronologico_{bloco_atual}"
            else:
                mi['grupo_id'] = f"{mi.get('etapa_nome', '')} | {header_str} | Bloco_Cronologico_{bloco_atual}"
            
            ultimo_n = n

        print("    Extraindo cabeçalhos das etapas da Manobra...")
        manobra_etapas_headers = page.evaluate("""() => {
            const trs = Array.from(document.querySelectorAll('tr.backgroundCinza'));
            return trs.map(tr => {
                if (!tr) return null;
                // Itera pelas células para garantir que o texto de cada coluna seja separado por espaço
                const cells = Array.from(tr.querySelectorAll('td, th'));
                const fullText = cells.map(c => (c.textContent || '').trim()).join(' ').replace(/[\\s\\xA0]+/g, ' ').trim();
                
                const m = fullText.match(/(\\d{2}\\/\\d{2}\\/\\d{4}\\s+\\d{2}:\\d{2})/);
                return {
                    texto: fullText,
                    data_hora: m ? m[1] : null
                };
            }).filter(h => h !== null && h.texto.length > 5);
        }""")

        # ============================================================
        # ETAPA B: EXTRAIR SOLICITAÇÃO
        # ============================================================
        print(f"\n[3] Abrindo a Solicitação {solicitacao_num}...")
        page.click("text=Consultas", force=True)
        page.wait_for_timeout(1000)
        try:
            page.click("text=/^\\s*Solicita[cç][aã]o\\s*$/i", timeout=5000)
        except:
            page.click("text=/Solicita[cç][aã]o de Manobra/i", timeout=5000)
        
        page.wait_for_timeout(3000)
        
        # Preenche pesquisa da Solicitação
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

        # Clica no link da solicitação
        page.evaluate(f"""(num) => {{
            const links = Array.from(document.querySelectorAll('a'));
            const link = links.find(l => (l.innerText || '').includes(num));
            if (link) link.click();
        }}""", solicitacao_num)
        page.wait_for_timeout(4000)

        print("    Extraindo painéis da Solicitação (Locais/Serviços)...")
        page.evaluate("""() => {
            document.querySelectorAll('.rich-stglpanel-header').forEach(h => {
                const b = document.getElementById(h.id.replace('_header', '_body'));
                // Tenta abrir se estiver fechado (display none ou se não tiver conteúdo visível)
                if (b && (window.getComputedStyle(b).display === 'none' || b.innerText.trim().length < 5)) { 
                    h.click(); 
                }
            });
        }""")
        # Espera um pouco mais e garante que o AJAX terminou
        page.wait_for_timeout(6000) 

        # Extrai metadados da Solicitação (Descrição/Finalidade)
        solicitacao_header_metadata = page.evaluate("""() => {
            const root = document.body;
            if (!root) return "";
            const labels = Array.from(root.querySelectorAll('label, span, td.label, td'));
            let meta = "";
            for (const l of labels) {
                const txt = (l.textContent || "").toUpperCase();
                if (txt.includes("TITULO") || txt.includes("FINALIDADE") || txt.includes("DESCRICAO")) {
                    const val = l.nextElementSibling ? l.nextElementSibling.textContent : "";
                    meta += " " + txt + ": " + val;
                }
            }
            return meta.toUpperCase();
        }""")

        print("    Extraindo dados gerais da Solicitação (Bloqueio de RA)...")
        solicitacao_bloqueio_ra = page.evaluate("""() => {
            if (!document || !document.body) return null;
            const labels = Array.from(document.querySelectorAll('label, span, td, th'));
            for (const l of labels) {
                const t = l.textContent.toUpperCase();
                if (t.includes('BLOQUEIO DE RA') || (t.includes('BLOQUEIO') && t.includes('RA'))) {
                    const tr = l.closest('tr');
                    const rowText = (tr ? tr.textContent : l.parentElement.textContent).toUpperCase();
                    
                    // Busca flexível: se achar 'SIM' ou 'NAO' na mesma linha/contexto do rótulo
                    const hasSIM = /\bSIM\b/.test(rowText);
                    const hasNAO = /\bN[AÃ]O\b/.test(rowText);
                    
                    if (hasSIM && !hasNAO) return "SIM";
                    if (hasNAO && !hasSIM) return "NAO";
                    if (hasSIM && hasNAO) {
                        // Se houver ambos, tenta ver qual está mais próximo do rótulo 'RA'
                        const posRA = rowText.indexOf('RA');
                        const posSIM = rowText.indexOf('SIM', posRA);
                        const posNAO = rowText.indexOf('NAO', posRA) === -1 ? rowText.indexOf('NÃO', posRA) : rowText.indexOf('NAO', posRA);
                        
                        if (posSIM !== -1 && (posNAO === -1 || posSIM < posNAO)) return "SIM";
                        if (posNAO !== -1 && (posSIM === -1 || posNAO < posSIM)) return "NAO";
                    }
                }
            }
            return null; // Retorna null para acionar o fallback do Python
        }""")
        solicitacao_texto_puro = page.evaluate("() => document.body ? document.body.innerText : ''")

        print("    Extraindo datas da Solicitação (Início/Término)...")
        solicitacao_datas = page.evaluate("""() => {
            if (!document || !document.body) return { inicio: '', termino: '' };
            const clean = (s) => (s || '').replace(/[\\s\\xA0]+/g, ' ').trim();
            const extractDT = (s) => {
                const m = (s || '').match(/(\\d{2}\\/\\d{2}\\/\\d{4}\\s+\\d{2}:\\d{2})/);
                return m ? m[1] : '';
            };
            
            let dIni = '';
            let dFim = '';
            
            const allElements = Array.from(document.querySelectorAll('td, th, span, label'));
            for (const el of allElements) {
                if (!el) continue;
                const txt = (el.textContent || '').toLowerCase();
                
                if (txt.includes('data') && (txt.includes('inicio') || txt.includes('início'))) {
                    let raw = (el.nextElementSibling ? el.nextElementSibling.textContent : '');
                    if (!extractDT(raw)) {
                        const tr = el.closest('tr');
                        const cell = el.closest('td, th');
                        if (tr && tr.nextElementSibling && cell) {
                            const idx = Array.from(tr.children).indexOf(cell);
                            if (idx >= 0 && tr.nextElementSibling.children[idx]) raw = tr.nextElementSibling.children[idx].textContent;
                        }
                    }
                    if (extractDT(raw)) dIni = extractDT(raw);
                }
                
                if (txt.includes('data') && (txt.includes('termino') || txt.includes('término'))) {
                    let raw = (el.nextElementSibling ? el.nextElementSibling.textContent : '');
                    if (!extractDT(raw)) {
                        const tr = el.closest('tr');
                        const cell = el.closest('td, th');
                        if (tr && tr.nextElementSibling && cell) {
                            const idx = Array.from(tr.children).indexOf(cell);
                            if (idx >= 0 && tr.nextElementSibling.children[idx]) raw = tr.nextElementSibling.children[idx].textContent;
                        }
                    }
                    if (extractDT(raw)) dFim = extractDT(raw);
                }
                if (dIni && dFim) break;
            }
            return { inicio: dIni, termino: dFim };
        }""")

        # Extrai os equipamentos listados em Locais de Interrupção
        solicitacao_locais = page.evaluate("""() => {
            const norm = (s) => (s || '').normalize('NFD').replace(/[\\u0300-\\u036f]/g, '').toLowerCase().replace(/\\s+/g, ' ').trim();
            const clean = (s) => (s || '').replace(/\\s+/g, ' ').trim();
            
            const tables = Array.from(document.querySelectorAll('table'));
            const eqptos = [];
            
            for (const tabela of tables) {
                if (!tabela || tabela.innerText.length < 20) continue;

                const rows = Array.from(tabela.querySelectorAll('tr'));
                let headerRowIdx = -1;
                let idxNumero = -1;
                let idxAlim = -1;
                let idxLocal = -1;
                let idxIni = -1;
                let idxFim = -1;
                
                for (let i = 0; i < rows.length; i++) {
                    const row = rows[i];
                    if (!row) continue;
                    const cells = Array.from(row.querySelectorAll('th, td'));
                    const texts = cells.map(c => norm(c.textContent));
                    
                    const tNum = texts.findIndex(t => t.includes('numero') || t.includes('equipamento') || t.includes('trafo'));
                    if (tNum >= 0 && (texts.some(t => t.includes('alimen')) || texts.some(t => t.includes('local')))) {
                        headerRowIdx = i;
                        idxNumero = tNum;
                        idxAlim = texts.findIndex(t => t.includes('alimen'));
                        idxLocal = texts.findIndex(t => t.includes('local'));
                        idxIni = texts.findIndex(t => t.includes('data') && (t.includes('ini')));
                        idxFim = texts.findIndex(t => t.includes('data') && (t.includes('ter')));
                        break;
                    }
                }
                
                if (headerRowIdx >= 0 && idxNumero >= 0) {
                    for (let i = headerRowIdx + 1; i < rows.length; i++) {
                        const row = rows[i];
                        if (!row) continue;
                        const tds = row.querySelectorAll('td');
                        if (tds.length > idxNumero) {
                            const v = clean(tds[idxNumero].textContent || '');
                            const isCode = v.length > 100 || /function\\s*\\(|var\\s+|const\\s+|document\\.|{|}|;|eval\\(/.test(v);
                            if (v && /\\d/.test(v) && v.length > 2 && v.length < 100 && !isCode) {
                                const a = (idxAlim >= 0 && tds.length > idxAlim) ? clean(tds[idxAlim].textContent || '') : '';
                                const l = (idxLocal >= 0 && tds.length > idxLocal) ? clean(tds[idxLocal].textContent || '') : '';
                                const ini = (idxIni >= 0 && tds.length > idxIni) ? clean(tds[idxIni].textContent || '') : '';
                                const fim = (idxFim >= 0 && tds.length > idxFim) ? clean(tds[idxFim].textContent || '') : '';
                                
                                eqptos.push({ numero: v, alimentador: a, local: l, inicio: ini, termino: fim });
                            }
                        }
                    }
                    if (eqptos.length > 0) break;
                }
            }
            return eqptos;
        }""")

        # ============================================================
        # DUMP DE DEBUG (O QUE O ROBÔ ENXERGOU)
        # ============================================================
        print("\n" + "="*115)
        print("🕵️‍♂️ DUMP DE DEBUG: O QUE O ROBÔ EXTRAIU DA TELA")
        print("="*115)
        
        print("\n[DADOS DA SOLICITAÇÃO]")
        print(f"  - Bloqueio de RA: '{solicitacao_bloqueio_ra}'")
        print(f"  - Data Início: '{solicitacao_datas.get('inicio', '')}'")
        print(f"  - Data Término: '{solicitacao_datas.get('termino', '')}'")
        print(f"  - Locais de Interrupção ({len(solicitacao_locais)} encontrados):")
        for sl in solicitacao_locais:
            print(f"      * Eq: '{sl.get('numero')}' | Alim: '{sl.get('alimentador')}' | Local: '{sl.get('local')}'")
            
        print("\n[DADOS DA MANOBRA]")
        print(f"  - Bloqueio de RA (Aba Manobra): '{manobra_ra_texto}'")
        
        # Filtra o "lixo" de JavaScript que vem grudado nos headers do HTML
        headers_limpos = []
        for eh in manobra_etapas_headers:
            t = eh.get('texto', '')
            if 'SimpleTogglePanel' in t or 'NºAçãoEqpto' in re.sub(r'\s+', '', t):
                continue
            headers_limpos.append(eh)

        print(f"  - Cabeçalhos de Etapas ({len(headers_limpos)} válidos encontrados):")
        for eh in headers_limpos:
            txt_clean = re.sub(r'\s+', ' ', eh.get('texto', '')).strip()
            print(f"      * {txt_clean} [Data/Hora: {eh.get('data_hora')}]")
            
        print(f"\n  - Itens da Manobra Detalhados ({len(manobra_dados)} encontrados):")
        
        # Agrupa os itens por etapa para exibir em formato de lista hierárquica
        itens_agrupados = {}
        for md in manobra_dados:
            eh = md.get('etapa_texto_header', '')
            # Limpa o lixo de JSF (SimpleTogglePanel...) e lixo de tabelas (<<>>Itens...)
            eh = re.sub(r'SimpleTogglePanelManager.*', '', eh)
            eh = re.sub(r'«»Itens.*', '', eh)
            eh = re.sub(r'\s+', ' ', eh).strip()
            if not eh: eh = "ETAPA DESCONHECIDA"
            
            if eh not in itens_agrupados:
                itens_agrupados[eh] = []
            itens_agrupados[eh].append(md)
            
        for etapa_nome, lista_itens in itens_agrupados.items():
            print(f"\n      🏷️  {etapa_nome}")
            
            for idx, md in enumerate(lista_itens):
                eq = str(md.get('equipamento', ''))
                al = str(md.get('alimentador', ''))
                lo = str(md.get('local', ''))
                ex = str(md.get('executor', ''))
                po = str(md.get('posicionamento', ''))
                ob = str(md.get('observacao', ''))
                
                tx = str(md.get('texto_linha', '')).upper()
                tx = re.sub(r'^(\d+)(MA[A-Z0-9]{2})', r'\1 \2', tx) # Separa o numero da macro
                tx = re.sub(r'\s+', ' ', tx).strip()
                
                attrs = []
                if eq: attrs.append(f"Eq: {eq}")
                if al: attrs.append(f"Alim: {al}")
                if lo: attrs.append(f"Local: {lo}")
                if ex: attrs.append(f"Exec: {ex}")
                if po: attrs.append(f"Pos: {po}")
                if ob and ob != "-": attrs.append(f"Obs: {ob}")
                
                str_attrs = " | ".join(attrs)
                print(f"          * Item {idx+1}: [{str_attrs}] ➔ Ação: {tx}")
                
        print("\n" + "="*115 + "\n")
        
        # O navegador será fechado agora (ao sair do bloco 'with'), economizando RAM para a validação.

    print("\n[ RELATÓRIO DE VALIDAÇÃO GDIS ]")

    # -----------------------------------------------------------
    # PREPARAÇÃO DE DADOS MESTRE
    # -----------------------------------------------------------
    sol_locais = []
    sol_dict = {}
    for item in solicitacao_locais:
        eq_raw = item.get('numero', '')
        # Filtro de segurança: ignora lixo de JS capturado indevidamente da tela (comum no RichFaces/JSF do GDIS)
        if not eq_raw or len(eq_raw) > 60 or "function" in eq_raw or "{" in eq_raw or "var " in eq_raw:
            continue
        eq_norm = _norm_eqpto(eq_raw)
        obj = {
            'eq': eq_norm,
            'alim': _norm_str(item['alimentador']),
            'local': _norm_str(item['local']),
            'inicio': item.get('inicio', ''),
            'termino': item.get('termino', '')
        }
        sol_locais.append(obj)
        sol_dict[eq_norm] = obj

    manobra_map = {}
    for item in manobra_dados:
        eq = _norm_eqpto(item.get('equipamento'))
        if not eq or eq == '-':
            continue # Ignora etapas puramente de cabeçalho
        if eq not in manobra_map:
            manobra_map[eq] = []
        manobra_map[eq].append({
            'texto_linha': item.get('texto_linha', ''),
            'acao_bruta': _norm_str(item.get('acao_bruta')),
            'alim': _norm_str(item.get('alimentador')),
            'local': _norm_str(item.get('local')),
            'executor': _norm_str(item.get('executor')),
            'posicionamento': _norm_str(item.get('posicionamento')),
            'observacao': _norm_str(item.get('observacao')),
            'etapa_nome': _norm_str(item.get('etapa_nome')),
            'etapa_texto_header': _norm_str(item.get('etapa_texto_header')),
            'grupo_id': item.get('grupo_id', 'Bloco_Desconhecido')
        })

    # Texto completo para buscas globais
    manobra_metadados_globais = (manobra_header_metadata + " " + solicitacao_header_metadata).upper()
    is_manobra_terceiros = "TERCEIROS" in manobra_metadados_globais

    txt_headers = " ".join([h.get('texto', '') for h in manobra_etapas_headers])
    txt_itens = " ".join([(mi.get('texto_linha', '') + " " + mi.get('observacao', '')) for mi in manobra_dados])
    manobra_texto_etapas = (txt_headers + " " + txt_itens).upper()

    # Normaliza o valor de RA extraído
    if solicitacao_bloqueio_ra in ["NÃO", "Nao", "Não"]:
        solicitacao_bloqueio_ra = "NAO"
        
    origem_ra = "Solicitação"
    if solicitacao_bloqueio_ra not in ["SIM", "NAO"]:
        # Plano B: Tenta usar a informação extraída da aba da manobra
        if manobra_ra_texto in ["SIM", "NAO", "NÃO", "Nao", "Não"]:
            solicitacao_bloqueio_ra = "NAO" if manobra_ra_texto.upper() in ["NAO", "NÃO"] else "SIM"
            origem_ra = "Manobra (Fallback)"
        else:
            solicitacao_bloqueio_ra = "NAO"
            origem_ra = "Padrão (Não Encontrado)"

    print("\n=== FASE: Integridade Visual e Sintaxe (Fase 1) ===")

    # REGRA 21 (Anti-Placeholder AAA)
    falhas_r21 = []
    for mi in manobra_dados:
        if mi.get('alimentador') == "AAA" or mi.get('equipamento') == "AAA":
            falhas_r21.append(f"Item '{mi.get('equipamento') or mi.get('alimentador')}'")
    if falhas_r21:
        for f in falhas_r21: print_regra(21, "ERRO", f"Placeholder genérico 'AAA' detectado em {f}")
    else:
        print_regra(21, "OK", "Nenhum placeholder 'AAA' detectado na manobra.")

    # REGRA 28 (Duplicidades na Mesma Etapa)
    duplicatas_r28 = []
    rastreio_etapas = {}
    for mi in manobra_dados:
        etapa_grupo = mi.get('etapa_texto_header', 'ETAPA DESCONHECIDA')
        etapa_nome = mi.get('etapa_nome', 'ETAPA DESCONHECIDA')
        alvo = mi.get('equipamento', '').strip() or mi.get('alimentador', '').strip()
        if not alvo or alvo == '-': continue
        txt_alvo = mi.get('acao_bruta', '') or mi.get('texto_linha', '')
        macros_linha = re.findall(r'\b\d*(MA[A-Z0-9]{2})\b', txt_alvo, re.IGNORECASE)
        if etapa_grupo not in rastreio_etapas: rastreio_etapas[etapa_grupo] = set()
        for m in macros_linha:
            assinatura = (alvo, m.upper())
            if assinatura in rastreio_etapas[etapa_grupo]:
                duplicatas_r28.append(f"Etapa '{etapa_nome}': {m.upper()} duplicada em '{alvo}'")
            else:
                rastreio_etapas[etapa_grupo].add(assinatura)
    if duplicatas_r28:
        for d in duplicatas_r28: print_regra(28, "ERRO", d)
    elif manobra_dados:
        print_regra(28, "OK", "Nenhuma macro duplicada para o mesmo equipamento na mesma etapa.")

    # REGRA 24 (Validações da Primeira Etapa: Quantidades CI, EQUIPES, GMT, etc.)
    if manobra_etapas_headers:
        texto_primeira = manobra_etapas_headers[0]['texto'].upper()
        # Normalização: Garante espaço entre horários e siglas coladas (ex: 08:00CI -> 08:00 CI)
        texto_primeira = re.sub(r'(\d{2}:\d{2})([A-Z])', r'\1 \2', texto_primeira)
        # Garante espaço antes de dois pontos se estiver colado (ex: CI:2 -> CI :2)
        texto_primeira = re.sub(r'([A-Z])(?::)', r'\1 :', texto_primeira)
        
        falhas_r24 = []
        alertas_r24 = []
        
        # Lista de siglas para verificar (Sigla: Descrição)
        siglas_validar = {
            "CI": "Clientes Interrompidos",
            "EQUIPES": "Equipes",
            "GMT": "Gerador MT",
            "GBT": "Gerador BT",
            "MJ": "Megajumper",
            "LV": "Linha Viva",
            "DI": "Drones/Inspeção"
        }
        
        # 1. Sigla EQUIPE (singular) gera alerta
        if re.search(r'\bEQUIPE\s*:', texto_primeira):
            alertas_r24.append("Foi escrito 'EQUIPE:' (singular). O padrão é 'EQUIPES:' no cabeçalho")

        # 2. Verificação de existência e Quantidade
        num_equipes_header = 0
        for sigla, desc in siglas_validar.items():
            # Procura a sigla no texto
            m_sigla = re.search(r'\b' + sigla + r'\b\s*:\s*(\d+)', texto_primeira)
            if re.search(r'\b' + sigla + r'\b', texto_primeira):
                # Se achou a sigla, verifica se tem o formato "SIGLA: numero"
                if m_sigla:
                    if sigla == "EQUIPES":
                        num_equipes_header = int(m_sigla.group(1))
                else:
                    falhas_r24.append(f"O Codigo '{sigla}' está presente mas falta informar a quantidade (Ex: {sigla}:1)")
            else:
                # CI é obrigatório sempre (EQUIPES pode ser opcional conforme nova regra da doc?) 
                # O usuário disse: "siglas obrigatórias (CI)", indicando que EQUIPES agora pode ser apenas validada se presente.
                if sigla in ["CI"]:
                    falhas_r24.append(f"Codigo obrigatório '{sigla}' não encontrado na primeira etapa")

        if falhas_r24:
            for f in falhas_r24: print_regra(24, "ERRO", f"Cabeçalho da 1ª etapa: {f}")
        if alertas_r24:
            for a in alertas_r24: print_regra(24, "ALERTA", f"Cabeçalho da 1ª etapa: {a}")
        if not falhas_r24 and not alertas_r24:
            print_regra(24, "OK", "Siglas e quantidades (CI) do cabeçalho validadas com sucesso.")

    # REGRA 40 (Aviso de Risco Sistema)
    if manobra_etapas_headers:
        if "RISCO SISTEMA" in txt_headers.upper() or "RISCO PARA SISTEMA" in txt_headers.upper():
            if "MANOBRA COM RISCO SISTEMA" in manobra_texto_etapas:
                print_regra(40, "OK", "Identificado aviso de risco no cabeçalho e etapa correspondente na manobra.")
            else:
                print_regra(40, "ERRO", "Cabeçalho informa Risco para Sistema, mas falta a etapa 'MANOBRA COM RISCO SISTEMA'.")

    # REGRA 25 (Horários Repetidos nas Etapas)
    if len(manobra_etapas_headers) >= 3:
        datas_etapas = [eh['data_hora'] for eh in manobra_etapas_headers if eh.get('data_hora')]
        if len(datas_etapas) >= 2 and len(set(datas_etapas)) == 1:
            print_regra(25, "ALERTA", f"Todas as etapas possuem o mesmo horário ('{datas_etapas[0]}'). Verifique a cronologia.")
        else:
            print_regra(25, "OK", "Variação temporal detectada entre as etapas da manobra.")

    # REGRA 20 (Observação obrigatória para Troca de Elo e Mudança de TAP)
    macros_obs_obrigatoria = ["MA63", "MA77"]
    falhas_r20 = set()
    teve_macro_obs = False
    for mi in manobra_dados:
        obs = mi.get('observacao', '').strip()
        eq_temp = mi.get('equipamento', '').strip() or mi.get('alimentador', '').strip()
        for m_obs in macros_obs_obrigatoria:
            txt_alvo = mi.get('acao_bruta', '') or mi.get('texto_linha', '')
            if re.search(r'\b\d*' + m_obs + r'\b', txt_alvo + " " + obs, re.IGNORECASE):
                teve_macro_obs = True
                if not obs or obs == "-":
                    falhas_r20.add(f"{m_obs.upper()} em '{eq_temp}'")
    if falhas_r20:
        print_regra(20, "ERRO", f"Observação obrigatória ('Lamina ou Fusível?') ausente para: {', '.join(sorted(falhas_r20))}")
    elif teve_macro_obs:
        pass  # IGNORADA silenciosa

    print("\n=== FASE: Validações Globais (Fase 2) ===")
    
    # REGRA 26 (Datas e Horários por Equipamento)
    from datetime import datetime
    def parse_dt(s):
        if not s: return None
        try:
            # Tenta extrair o padrão de data do meio de lixo se necessário
            m = re.search(r'(\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2})', str(s))
            if m: return datetime.strptime(m.group(1), "%d/%m/%Y %H:%M")
            return None
        except: return None

    dt_sol_ini = parse_dt(solicitacao_datas.get('inicio', ''))
    dt_sol_fim = parse_dt(solicitacao_datas.get('termino', ''))

    print("\n🔹 Verificando Cronogramas (Regra 26 - Início real em 'Desligamento')...")
    
    # Se não temos datas globais e nem locais, emitimos um alerta único de scraping
    if not dt_sol_ini and not any(sol_dict.values()):
        print_regra(26, "ALERTA", "Dificuldade técnica ao ler horários autorizados da solicitação. Validação de cronograma prejudicada.")

    for eq, items in manobra_map.items():
        todos_horarios_validos = []
        horarios_deslig = []
        
        for mi in items:
            dt_str = mi.get('etapa_texto_header', '')
            etapa_full = (mi.get('etapa_nome', '') + ' ' + dt_str).upper()
            
            # Filtro para ignorar etapas de preparação, administrativas ou informativas
            is_preparacao = any(x in etapa_full for x in ["PREPARACAO", "PREPARAÇÃO", "COMUNICACAO", "COMUNICAÇÃO", "REGISTRO", "OBSERVACAO", "OBSERVAÇÃO"])
            
            m_dt = re.search(r'(\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2})', dt_str)
            if m_dt:
                dt_obj = parse_dt(m_dt.group(1))
                if dt_obj:
                    if not is_preparacao:
                        todos_horarios_validos.append(dt_obj)
                        if "DESLIGAMENTO" in etapa_full:
                            horarios_deslig.append(dt_obj)
        
        if not todos_horarios_validos: continue
        
        ini_man_real = min(horarios_deslig) if horarios_deslig else None
        fim_man = max(todos_horarios_validos)
        
        lim_ini = dt_sol_ini
        lim_fim = dt_sol_fim
        
        info_sol = sol_dict.get(eq)
        is_apoio = (info_sol is None)
        
        if info_sol:
            dt_indiv_ini = parse_dt(info_sol.get('inicio', ''))
            dt_indiv_fim = parse_dt(info_sol.get('termino', ''))
            if dt_indiv_ini: lim_ini = dt_indiv_ini
            if dt_indiv_fim: lim_fim = dt_indiv_fim
            
        falhas_r26 = []
        # Valida antecipação (Apenas se houver início de desligamento identificado)
        if lim_ini and ini_man_real and ini_man_real < lim_ini:
            falhas_r26.append(f"Início antecipado do desligamento ({ini_man_real.strftime('%H:%M')}) vs Autorizado ({lim_ini.strftime('%H:%M')})")
        
        # Valida término
        if lim_fim and fim_man > lim_fim:
            falhas_r26.append(f"Término tardio ({fim_man.strftime('%H:%M')}) vs Autorizado ({lim_fim.strftime('%H:%M')})")
            
        if falhas_r26:
            msg_f = " e ".join(falhas_r26)
            tipo_msg = "ERRO" if not is_apoio else "ALERTA"
            print_regra(26, tipo_msg, f"Equipamento '{eq}': Divergência de cronograma. {msg_f}")
        else:
            if not lim_ini or not lim_fim:
                if not is_apoio and dt_sol_ini:
                    pass # Evita log de ausência se não achou as datas individuais (já tem o alerta global)


    # REGRA 5 (Bloqueio de RA)
    print(f"🔹 Bloqueio de RA (Valor: {solicitacao_bloqueio_ra} | Origem: {origem_ra})")
    if solicitacao_bloqueio_ra == "SIM":
        tem_macro_ra = any(re.search(r'\b\d*' + m + r'\b', (manobra_texto_etapas or ""), re.IGNORECASE) for m in ["MA52", "MA14", "MA28"])
        if not tem_macro_ra:
            for mi in manobra_dados:
                if any(re.search(r'\b\d*' + m + r'\b', mi.get('texto_linha', '') + " " + mi.get('observacao', ''), re.IGNORECASE) for m in ["MA52", "MA14", "MA28"]):
                    tem_macro_ra = True
                    break
        
        if tem_macro_ra:
            print_regra(5, "OK", "Planejamento da manobra possui macro de bloqueio MA52/MA14/MA28, conforme exigido.")
        else:
            print_regra(5, "ERRO", "A solicitação exige bloqueio de Religamento Automático (RA), mas a manobra não contém as macros obrigatórias (MA52, MA14 ou MA28).")
    else:
        macros_encontradas = set()
        for m in ["MA52", "MA14", "MA28"]:
            if re.search(r'\b\d*' + m + r'\b', (manobra_texto_etapas or ""), re.IGNORECASE):
                macros_encontradas.add(m)
                
        if not macros_encontradas:
            for mi in manobra_dados:
                for m in ["MA52", "MA14", "MA28"]:
                    if re.search(r'\b\d*' + m + r'\b', mi.get('texto_linha', '') + " " + mi.get('observacao', ''), re.IGNORECASE):
                        macros_encontradas.add(m)
                        
        if macros_encontradas:
            str_macros = ", ".join(sorted(macros_encontradas))
            print_regra(5, "ERRO", f"A solicitação NÃO exige bloqueio de RA, porém a manobra contém macros de bloqueio indevidas: {str_macros}.")
        else:
            print_regra(5, "OK", "Bloqueio de RA validado: a manobra está coerente com a solicitação.")

    # REGRA 23 (Uso de Gerador)
    exige_gerador = False
    motivo_gerador = ""
    if re.search(r'\b(gerador|ugtm|gmd|gmt|gbt)\b', solicitacao_texto_puro or "", re.IGNORECASE):
        exige_gerador, motivo_gerador = True, "Citação de gerador/UGTM na Solicitação"
    if not exige_gerador:
        for item in manobra_dados:
            txt_comp = (item.get('etapa_texto_header', '') + " " + item.get('etapa_nome', '') + " " + item.get('texto_linha', '') + " " + item.get('observacao', ''))
            if re.search(r'\b(gerador|ugtm|gmd|gmt|gbt)\b', txt_comp, re.IGNORECASE):
                exige_gerador, motivo_gerador = True, "Citação de gerador/UGTM nas etapas"
                break
            if re.search(r'\bmanobra\s+pelo\s+t[eé]cnico\b', txt_comp, re.IGNORECASE):
                exige_gerador, motivo_gerador = True, "Etapa 'MANOBRA PELO TECNICO' detectada"
                break
    if exige_gerador:
        if manobra_etapas_headers and re.search(r'\bG[MB]T\s*:', manobra_etapas_headers[0]['texto'].upper()):
            print_regra(23, "OK", f"Uso de gerador/UGTM justificado com declaração no cabeçalho ({motivo_gerador}).")
        else:
            print_regra(23, "ALERTA", f"{motivo_gerador} detectado, mas a primeira etapa não declarou 'GMT:' ou 'GBT:'. Verifique a necessidade de registro.")
    else:
        print_regra(23, "OK", "Nenhum uso de gerador ou UGTM detectado.")

    # REGRA 27 (Coerência do Executor)
    falhas_r27 = set()
    for mi in manobra_dados:
        etapa_n = re.sub(r'[ÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜ]', lambda m: 'AAAAAEEEEIIIIOOOOOUUUU'['ÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜ'.find(m.group(0))], mi.get('etapa_nome', '').upper())
        exec_n = re.sub(r'[ÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜ]', lambda m: 'AAAAAEEEEIIIIOOOOOUUUU'['ÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜ'.find(m.group(0))], mi.get('executor', '').upper())
        if "DESLIGAMENTO" in etapa_n and "RELIGAMENTO" not in etapa_n and "SUPERVISOR" not in exec_n:
            falhas_r27.add(f"'{mi.get('etapa_nome')}' exige 'Supervisor' (encontrado: '{mi.get('executor')}')")
        elif "RELIGAMENTO" in etapa_n and "SUPERVISOR" not in exec_n:
            falhas_r27.add(f"'{mi.get('etapa_nome')}' exige 'Supervisor' (encontrado: '{mi.get('executor')}')")
        elif "MANOBRA PELO TECNICO" in etapa_n and "TECNICO" not in exec_n:
            falhas_r27.add(f"'{mi.get('etapa_nome')}' exige 'Técnico' (encontrado: '{mi.get('executor')}')")
    if falhas_r27:
        print_regra(27, "ALERTA", falhas_r27)
    elif manobra_dados:
        print_regra(27, "OK", "Executores estão coerentes com as etapas de Desligamento, Religamento e Manobra pelo Técnico.")

    # REGRA 29 (Verificação de Anormalidade por Alimentador)
    contagem_alim = {}
    verificacao_cod_ma09 = set()
    for mi in manobra_dados:
        alim = mi.get('alimentador', '').strip()
        eq = mi.get('equipamento', '').strip()
        eff_alim = alim if alim and alim != '-' and bool(re.search(r'[0-9]', alim)) else None
        
        # Se for um item de alimentador puro (Ex: PIUD217) no campo equipamento
        if bool(re.search(r'[A-Za-z]', eq)) and bool(re.search(r'[0-9]', eq)) and ('-' not in eq) and eq != '-' and not eff_alim:
            eff_alim = eq
            
        if eff_alim:
            contagem_alim[eff_alim] = contagem_alim.get(eff_alim, 0) + 1
            
        et = mi.get('etapa_texto_header', '') + " " + mi.get('etapa_nome', '')
        tx = mi.get('texto_linha', '')
        ob = mi.get('observacao', '')
        execut_cod = mi.get('executor', '')
        
        is_cod_executando = bool(re.search(r'\bCOD\b', execut_cod, re.IGNORECASE)) or bool(re.search(r'\bVERIFICA[CÇ]?[AÃ]?O\s*(?:PELO|DO|DA)?\s*COD\b', et + " " + tx + " " + ob, re.IGNORECASE))
        if is_cod_executando and re.search(r'\b\d*MA09\b', tx + " " + ob, re.IGNORECASE):
            if eff_alim: 
                verificacao_cod_ma09.add(eff_alim)
            else:
                print_regra(29, "ALERTA", "Ação MA09 detectada pelo COD, mas o campo 'Alimentador' está vazio. Não foi possível vincular a verificação.")

    falhas_r29 = [f"Alimentador '{a}' manobrado sem a ação MA09 (Verificação de Anormalidade) pelo COD." for a, c in contagem_alim.items() if a not in verificacao_cod_ma09]
    if falhas_r29:
        print_regra(29, "ERRO", falhas_r29)
    elif contagem_alim:
        print_regra(29, "OK", "Todos os alimentadores envolvidos possuem a verificação MA09 vinculada ao COD.")

    print("\n=== FASE: Cruzamento com a Solicitação (Fase 3) ===")
    if not sol_locais:
        print("⚠️  A Solicitação não possui equipamentos listados em 'Locais de interrupção'.")
    else:
        for sol_item in sol_locais:
            eq = sol_item['eq']
            sol_alim = sol_item['alim']
            sol_local = sol_item['local']
            
            print(f"\n🔹 [SOLICITAÇÃO] Equipamento: {eq} | Alimentador: {sol_alim or '-'} | Local: {sol_local or '-'}")
            
            if eq not in manobra_map:
                # Fallback 1: tentar casar ignorando prefixos (e.g. "24 - 12345" na solicitação, "12345" na manobra)
                eq_sem_prefixo = _get_eq_id(eq)
                encontrou_fallback = False
                for k in manobra_map.keys():
                    k_sem_prefixo = _get_eq_id(k)
                    if eq_sem_prefixo == k_sem_prefixo:
                        eq = k
                        encontrou_fallback = True
                        break
                
                # Fallback 2: equipamento aparece na coluna Observação (ex: Gerador de BT vinculado)
                eq_em_observacao = False
                if not encontrou_fallback:
                    eq_digits = re.sub(r'[^0-9]', '', eq)  # extrai só os dígitos do eq da solicitação
                    if eq_digits:
                        for mi in manobra_dados:
                            obs_digits = re.sub(r'[^0-9]', '', mi.get('observacao', ''))
                            if eq_digits in obs_digits and len(eq_digits) >= 5:
                                encontrou_fallback = True
                                eq_em_observacao = True
                                print_regra(1, "OK", f"Equipamento '{eq}' identificado na coluna Observação (vínculo de Gerador/Equipamento auxiliar).")
                                break  # sai do loop interno de manobra_dados
                
                if not encontrou_fallback:
                    print_regra(1, "ERRO", f"Equipamento da Solicitação '{eq}' NÃO foi encontrado na Manobra. Verifique se foi omitido ou se há erro no nome.")
                    continue
                
                if eq_em_observacao:
                    continue  # Pula Regras do Conferidor 3, 4, 12, 13... pois o eq não tem itens diretos na manobra
            
            if eq in manobra_map:
                print_regra(1, "OK", f"Equipamento '{eq}' presente na Manobra.")
            manobra_items = manobra_map.get(eq, [])

            # REGRA 3
            if not sol_alim or sol_alim == "-":
                pass  # IGNORADA silenciosa
            else:
                alim_ok = any(mi['alim'] == sol_alim for mi in manobra_items)
                if alim_ok:
                    print_regra(3, "OK", f"Alimentador '{sol_alim}' confirmado para o equipamento '{eq}'.")
                else:
                    alims_found = set(mi['alim'] for mi in manobra_items if mi['alim'])
                    alims_str = ", ".join(alims_found) if alims_found else "Nenhum"
                    print_regra(3, "ERRO", f"Alimentador divergente para '{eq}'. Esperado: {sol_alim}, Encontrado na Manobra: {alims_str}.")

            # REGRA 4
            if not sol_local or sol_local == "-":
                pass  # IGNORADA silenciosa
            else:
                local_ok = any(mi['local'] == sol_local for mi in manobra_items)
                if local_ok:
                    print_regra(4, "OK", f"Local '{sol_local}' confirmado para o equipamento '{eq}'.")
                else:
                    locais_found = set(mi['local'] for mi in manobra_items if mi['local'])
                    locais_str = ", ".join(locais_found) if locais_found else "Nenhum"
                    print_regra(4, "ERRO", f"Local divergente para '{eq}'. Esperado: {sol_local}, Encontrado na Manobra: {locais_str}.")

    print("\n=== FASE: Restrições Físicas e Engenharia (Fase 4) ===")
    if not manobra_map:
        print("⚠️  Manobra vazia. Sem equipamentos manobrados.")
        
    # Encontra o limite cronológico da etapa de DESLIGAMENTO para a Regra de Sinalização
    limite_cronologia_desligamento = -1
    for mi in manobra_dados:
        nome_etapa = mi.get('etapa_nome', '').upper()
        if "DESLIGAMENTO" in nome_etapa and "RELIGAMENTO" not in nome_etapa:
            limite_cronologia_desligamento = max(limite_cronologia_desligamento, mi.get('cronologia', 0))

    # Macros globais para identificação de ações (Usadas em múltiplas regras)
    macros_abertura = re.compile(r'\b\d*(MA01|MA31|MA30|MA18|MA22|MA24|MA54|MA56|MAA9)\b(?!\s*-\s*OUTROS)')
    macros_fechamento = re.compile(r'\b\d*(MA02|MA66|MA67|MA19|MA23|MA25|MA55|MA57|MAB1)\b(?!\s*-\s*OUTROS)')

    for eq, manobra_items in manobra_map.items():
        print(f"\n🔹 Equipamento: {eq}")
        sol_info = sol_dict.get(eq, {})
        sol_alim = sol_info.get('alim', '')
        alim_manobra = manobra_items[0].get('alim', '')
        local_manobra = manobra_items[0].get('local', '')
        eq_data = _get_eq_data(dados_equipamentos, eq, alim_manobra, sol_alim, local_manobra)
        
        # REGRA 31: ESTADO DO EQUIPAMENTO
        # Verifica se o equipamento está sendo aberto/fechado em coerência com seu estado atual no Gemini

        # Identifica o prefixo do equipamento para aplicar regras específicas (Ex: 01=Trafo, 22=Religador)
        # Regex lida com transformadores ID - Fases - kVA
        is_trafo = bool(re.match(r"^\d{5,7}\s*-\s*\d+\s*-\s*\d+$", eq))
        prefixo = "01" if is_trafo else (eq.split('-')[0].strip().zfill(2) if '-' in eq else "")
        is_alim = bool(re.search(r'[A-Za-z]', eq)) and ('-' not in eq)

        # REGRA 6 (Incompatibilidade de Ação pelo Prefixo)
        if prefixo and prefixo in parametros_conferidor and len(parametros_conferidor[prefixo]) > 0:
            acoes_proibidas = parametros_conferidor[prefixo]
            acoes_encontradas_proibidas = []
            for mi in manobra_items:
                texto_linha = mi['texto_linha']
                for acao_proibida in acoes_proibidas:
                    # Usa regex ignorando maiúsculas/minúsculas para buscar o código (ex: MA31) ou palavra exata
                    if re.search(r'\b' + re.escape(acao_proibida) + r'\b', texto_linha, re.IGNORECASE):
                        acoes_encontradas_proibidas.append(acao_proibida.upper())
            
            if acoes_encontradas_proibidas:
                acoes_str = ", ".join(set(acoes_encontradas_proibidas))
                print_regra(6, "ERRO", f"O equipamento '{eq}' possui ações incompatíveis com seu prefixo: '{acoes_str}'. Revise as macros.")
            else:
                print_regra(6, "OK", f"Nenhuma ação incompatível detectada para o prefixo de '{eq}'.")
        else:
            pass  # IGNORADA silenciosa

        # REGRA 7 (Modo Local para Equipamentos Telecontrolados)
        if eq in sol_dict:
            is_telecontrolado = eq_data.get('telecontrolado', False)
            if prefixo == "02":
                print_regra(7, "OK", f"Equipamento '{eq}' é Regulador de Tensão, isento de Modo Local (MA64).")
            elif is_telecontrolado:
                acao_ma64_encontrada = any(re.search(r'\b\d*MA64\b', mi['texto_linha'], re.IGNORECASE) for mi in manobra_items)
                if acao_ma64_encontrada:
                    print_regra(7, "OK", f"Equipamento telecontrolado '{eq}' possui a macro MA64 (Modo Local).")
                else:
                    print_regra(7, "ERRO", f"O equipamento '{eq}' é telecontrolado, mas a macro MA64 (Modo Local) NÃO foi encontrada.")
            else:
                print_regra(7, "OK", f"Equipamento '{eq}' é manual, não exige Modo Local.")
        else:
            pass  # IGNORADA silenciosa

        # REGRA 31 (Coerência de POSOPE: Abertura em NF, Fechamento em NA)
        posope = eq_data.get('posope', '')
        estado_simulado = posope
        primeira_acao = None
        erro_31 = []
        
        # Auxiliares para Regra de Sinalização Pré-Desligamento
        abriu_ate_desligamento = False
        quem_abriu_ate_desligamento = ""
        sinalizou_ate_desligamento = False

        is_primeiro_item_eq = True
        for mi in manobra_items:
            etapa_txt = (mi.get('etapa_nome', '') + ' ' + mi.get('etapa_texto_header', '')).upper()
            txt = mi['texto_linha'].upper()
            executor = mi.get('executor', '').upper()
            obs = mi.get('observacao', '').upper()
            cron = mi.get('cronologia', 0)
            is_dr = "DESLIGAMENTO" in etapa_txt or "RELIGAMENTO" in etapa_txt
            
            # --- REGRA 41: MA63 (TROCA DE ELO FUSÍVEL) ---
            if "MA63" in txt:
                 # Remove acentos para comparação robusta
                 def normalizar(t):
                     import unicodedata
                     return "".join(c for c in unicodedata.normalize('NFD', t) if unicodedata.category(c) != 'Mn')
                 if "REGIAO" not in normalizar(executor):
                     print_regra(41, "ERRO", f"Macro MA63 (Troca de Elo) executada por '{executor}'. Deve ser realizada obrigatoriamente pela Região.")

            # --- REGRA 31: Sincronização Inicial ---
            if is_primeiro_item_eq:
                if "MA39" in txt: # Confirmar Aberto
                    estado_simulado = "A"
                    print_regra(31, "INFO", f"Sincronizando estado de '{eq}' para ABERTO via macro MA39.")
                elif "MA49" in txt: # Confirmar Fechado
                    estado_simulado = "F"
                    print_regra(31, "INFO", f"Sincronizando estado de '{eq}' para FECHADO via macro MA49.")
                is_primeiro_item_eq = False

            is_abertura = bool(macros_abertura.search(txt) or re.search(r'\bABRIR\b', txt))
            is_fechamento = bool(macros_fechamento.search(txt) or re.search(r'\bFECHAR\b', txt))

            # --- RASTREIO PARA REGRA DE SINALIZAÇÃO ---
            if cron <= limite_cronologia_desligamento:
                if is_abertura:
                    abriu_ate_desligamento = True
                    quem_abriu_ate_desligamento = executor
                if "MA06" in txt:
                    sinalizou_ate_desligamento = True

            if is_abertura:
                if not primeira_acao: primeira_acao = 'ABRIR'
                if estado_simulado == 'A':
                    # Falha: Abrindo algo que já está aberto ou que acabamos de abrir
                    # Nota: ignoramos etapas de normalização PARA O ALERTA INICIAL se o usuário quiser ser flexível, 
                    # mas para SEGURANÇA, abrir o que já está aberto é sempre erro de instrução.
                    msg = f"Abrindo equipamento que já consta como Aberto (Estado Atual={estado_simulado})"
                    erro_31.append(msg)
                estado_simulado = 'A'
            elif is_fechamento:
                if not primeira_acao: primeira_acao = 'FECHAR'
                if estado_simulado == 'F':
                    msg = f"Fechando equipamento que já consta como Fechado (Estado Atual={estado_simulado})"
                    erro_31.append(msg)
                estado_simulado = 'F'

        # --- REGRA 42: SINALIZAÇÃO PÓS-ABERTURA (ATÉ DESLIGAMENTO) ---
        if abriu_ate_desligamento and not sinalizou_ate_desligamento:
            if "COD" in quem_abriu_ate_desligamento:
                print_regra(42, "ALERTA", f"Equipamento '{eq}' aberto pelo COD até o desligamento, mas sem macro MA06 de sinalização.")
            else:
                print_regra(42, "ERRO", f"Equipamento '{eq}' aberto por '{quem_abriu_ate_desligamento}' até o desligamento, mas sem macro MA06 de sinalização.")

        # --- REGRA 31: EVOLUÇÃO DO ESTADO POSOPE ---
        if posope in ['A', 'F']:
            if erro_31:
                str_erros = " | ".join(sorted(set(erro_31)))
                print_regra(31, "ERRO", f"Equipamento '{eq}': {str_erros}")
            elif primeira_acao:
                print_regra(31, "OK", f"Ações coerentes com a evolução do estado POSOPE={posope} em '{eq}'.")
            else:
                # Se não houve ação mas o estado final bate, pode ser sincronismo
                tem_sinc = any(re.search(r'\b\d*(MA39|MA49)\b', mi['texto_linha'], re.IGNORECASE) for mi in manobra_items)
                if tem_sinc:
                    print_regra(31, "INFO", f"Estado de '{eq}' sincronizado via macro de supervisão (MA39/MA49).")
                else:
                    print_regra(31, "OK", f"Equipamento '{eq}' manteve estado estável POSOPE={posope}.")
        else:
            pass # IGNORADA silenciosa

        # REGRA 8 (Macros exclusivas de RT)
        macros_rt = ["MA35", "MA36", "MA77"]
        acoes_rt_encontradas = set()
        for mi in manobra_items:
            for m_rt in macros_rt:
                if re.search(r'\b\d*' + m_rt + r'\b', mi['texto_linha'], re.IGNORECASE):
                    acoes_rt_encontradas.add(m_rt.upper())
        if acoes_rt_encontradas:
            is_rt = (prefixo == "02")
            if not (is_rt or is_alim):
                str_macros = ", ".join(sorted(acoes_rt_encontradas))
                print_regra(8, "ERRO", f"As macros {str_macros} são exclusivas de Reguladores de Tensão. O equipamento '{eq}' não é um RT.")
            else:
                print_regra(8, "OK", "Macros exclusivas de RT aplicadas corretamente.")
        else:
            pass  # IGNORADA silenciosa

        # REGRA 9 (Macros de operação de Religador/Disjuntor)
        macros_relig_disj = ["MA14", "MA15", "MA16", "MA17", "MA19", "MA20", "MAA4", "MAA5"]
        acoes_rd_encontradas = set()
        for mi in manobra_items:
            for m_rd in macros_relig_disj:
                if re.search(r'\b\d*' + m_rd + r'\b', mi['texto_linha'], re.IGNORECASE):
                    acoes_rd_encontradas.add(m_rd.upper())
        if acoes_rd_encontradas:
            is_relig_disj = (prefixo in ["21", "22"])
            if not (is_relig_disj or is_alim):
                str_macros = ", ".join(sorted(acoes_rd_encontradas))
                print_regra(9, "ERRO", f"As macros ({str_macros}) são exclusivas de Religador/Disjuntor. O equipamento '{eq}' não pertence a esta categoria.")
            else:
                print_regra(9, "OK", "Macros de Religador/Disjuntor aplicadas corretamente.")
        else:
            pass  # IGNORADA silenciosa

        # REGRA 10 (Bloqueio/Desbloqueio de Chave Deslocada)
        macros_bloqueio = ["MA28", "MA29"]
        acoes_bloq_encontradas = []
        falha_regra10 = False
        motivo_falha_10 = ""
        
        for mi in manobra_items:
            for m_bloq in macros_bloqueio:
                if re.search(r'\b\d*' + m_bloq + r'\b', mi['texto_linha'], re.IGNORECASE):
                    acoes_bloq_encontradas.append(m_bloq.upper())
                    
                    if prefixo not in ["01", "04"]:
                        falha_regra10 = True
                        motivo_falha_10 = f"Permitido apenas para prefixos 01 ou 04."
                    elif prefixo == "01":
                        # Verifica se tem 'CHAVE DESLOCADA' na mesma linha, aceitando espaços extras no meio
                        if not re.search(r'\bCHAVE\s+DESLOCADA\b', mi['texto_linha'], re.IGNORECASE):
                            falha_regra10 = True
                            motivo_falha_10 = f"Prefixo 01 exige a observação 'CHAVE DESLOCADA' junto à macro."

        if acoes_bloq_encontradas:
            str_macros_bloq = ", ".join(sorted(set(acoes_bloq_encontradas)))
            if falha_regra10:
                print_regra(10, "ERRO", f"As macros ({str_macros_bloq}) são inválidas para o equipamento '{eq}'. {motivo_falha_10}")
            else:
                print_regra(10, "OK", "Macros de Bloqueio/Desbloqueio de Chave Deslocada aplicadas corretamente.")
        else:
            pass  # IGNORADA silenciosa

        # REGRA 11 (Alteração de Ajustes de Proteção)
        macros_ajustes = ["MAA1", "MAA2", "MAA3", "MA89"]
        acoes_ajustes_encontradas = set()
        for mi in manobra_items:
            for m_ajuste in macros_ajustes:
                if re.search(r'\b\d*' + m_ajuste + r'\b', mi['texto_linha'], re.IGNORECASE):
                    acoes_ajustes_encontradas.add(m_ajuste.upper())
        if acoes_ajustes_encontradas:
            is_protecao = (prefixo in ["21", "22", "23"])
            if not (is_protecao or is_alim):
                str_macros_ajustes = ", ".join(sorted(acoes_ajustes_encontradas))
                print_regra(11, "ERRO", f"Macros de alteração de ajustes ({str_macros_ajustes}) aplicadas em equipamento inválido: '{eq}'. Permitido apenas para prefixos 21, 22 e 23.")
            else:
                print_regra(11, "OK", "Macros de alteração de ajustes de proteção aplicadas corretamente.")
        else:
            pass  # IGNORADA silenciosa

        # REGRA 12 (Posicionamento obrigatório para operação local/Região)
        macros_operacao = ["MA01", "MA02", "MA31", "MA66", "MA30", "MA67"]
        falhas_12 = set()
        teve_operacao_regiao = False
        is_telecontrolado = eq_data.get('telecontrolado', False)
        tem_mab9 = any(re.search(r'\b\d*MAB9\b', mi['texto_linha'], re.IGNORECASE) for mi in manobra_items)
        for mi in manobra_items:
            execut = mi['executor'].upper()
            posic = mi['posicionamento'].upper()
            pos_obrigatorio = (posic == 'SIM')
            if 'REGIAO' in execut or 'REGIÃO' in execut:
                for m_op in macros_operacao:
                    if re.search(r'\b\d*' + m_op + r'\b', mi['texto_linha'], re.IGNORECASE):
                        teve_operacao_regiao = True
                        if is_telecontrolado and prefixo != "02" and not pos_obrigatorio and not tem_mab9:
                            falhas_12.add(m_op.upper())
        if falhas_12:
            str_macros = ", ".join(sorted(falhas_12))
            if is_manobra_terceiros:
                print_regra(12, "ALERTA", f"MANOBRA DE TERCEIROS: Executor 'Região' operando equipamento telecontrolado '{eq}' ({str_macros}) sem a coluna 'Posicionamento' marcada.")
            else:
                print_regra(12, "ERRO", f"Executor 'Região' operando equipamento telecontrolado '{eq}' ({str_macros}) sem a coluna 'Posicionamento' marcada.")
        elif teve_operacao_regiao:
            if prefixo == "02":
                 print_regra(12, "OK", f"Equipamento '{eq}' (Regulador de Tensão) operado corretamente: telecontrole restrito aos TAPs.")
            elif is_telecontrolado and not tem_mab9:
                print_regra(12, "OK", "Operação local de equipamento telecontrolado validada com Posicionamento = Sim.")
            elif tem_mab9:
                print_regra(12, "OK", "Exceção validada: macro MAB9 justifica a ausência de telecontrole/posicionamento.")
            else:
                print_regra(12, "OK", f"Equipamento '{eq}' é manual, não exige marcação de posicionamento.")
        else:
            pass  # IGNORADA silenciosa

        # REGRA 13 (Abertura sem sinalização pela Região)
        falha_r13 = False
        teve_ma01_regiao = False
        for mi in manobra_items:
            execut = mi['executor'].upper()
            if 'REGIAO' in execut or 'REGIÃO' in execut:
                if re.search(r'\b\d*MA01\b', mi['texto_linha'], re.IGNORECASE):
                    teve_ma01_regiao = True
                    if is_telecontrolado and not tem_mab9:
                        if not re.search(r'\bCORTE\s+DE\s+CARGA\b', mi['texto_linha'], re.IGNORECASE):
                            falha_r13 = True
        if falha_r13:
            print_regra(13, "ALERTA", f"Executor 'Região' realizando abertura (MA01) em '{eq}' sem a indicação de 'CORTE DE CARGA'. Verifique a sinalização.")
        elif teve_ma01_regiao:
            if not is_telecontrolado or tem_mab9:
                print_regra(13, "OK", f"Abertura de equipamento manual ou justificado por MAB9 validada para '{eq}'.")
            else:
                print_regra(13, "OK", f"Abertura local MA01 de '{eq}' confirmada com 'CORTE DE CARGA'.")
        else:
            pass  # IGNORADA silenciosa

        # REGRA 14 (Posicionamento proibido para COD)
        falha_r14 = False
        teve_cod = False
        for mi in manobra_items:
            execut = mi['executor'].upper()
            posic = mi['posicionamento'].upper()
            pos = (posic == 'SIM')
            if re.search(r'\bCOD\b', execut, re.IGNORECASE):
                teve_cod = True
                if pos:
                    falha_r14 = True
        if falha_r14:
            print_regra(14, "ERRO", f"O executor 'COD' não pode utilizar a coluna 'Posicionamento' (detectado no equipamento '{eq}').")
        elif teve_cod:
            print_regra(14, "OK", f"Operações do COD no equipamento '{eq}' estão sem marcação indevida de posicionamento.")
        else:
            pass  # IGNORADA silenciosa

        # REGRA 15 (COD só opera equipamentos telecontrolados e permitidos)
        macros_operacao_cod = ["MA01", "MA02", "MA31", "MA30", "MA66", "MA67"]
        falhas_r15 = set()
        motivos_r15 = set()
        teve_operacao_cod = False
        for mi in manobra_items:
            execut = mi['executor'].upper()
            if re.search(r'\bCOD\b', execut, re.IGNORECASE):
                for m_op in macros_operacao_cod:
                    if re.search(r'\b\d*' + m_op + r'\b', mi['texto_linha'], re.IGNORECASE):
                        teve_operacao_cod = True
                        is_prefixo_valido = prefixo in ["02", "19", "20", "21", "22", "23"] or is_alim
                        if not is_prefixo_valido:
                            falhas_r15.add(m_op.upper())
                            motivos_r15.add("Prefixo não permitido para operação remota")
                        elif not eq_data.get('telecontrolado', False):
                            falhas_r15.add(m_op.upper())
                            motivos_r15.add("Equipamento não possui telecontrole")
                        elif prefixo == "02" and m_op.upper() in ["MA01", "MA02", "MA31", "MA30"]:
                            falhas_r15.add(m_op.upper())
                            motivos_r15.add("COD não realiza abertura/fechamento direto de Regulador de Tensão (02)")
        if falhas_r15:
            str_macros = ", ".join(sorted(falhas_r15))
            str_motivos = " e ".join(sorted(motivos_r15))
            print_regra(15, "ERRO", f"O COD está executando as macros ({str_macros}) irregularmente em '{eq}'. Motivo: {str_motivos}.")
        elif teve_operacao_cod:
            print_regra(15, "OK", f"Operação remota do COD em '{eq}' validada (equipamento telecontrolado e prefixo autorizado).")
        else:
            pass  # IGNORADA silenciosa

        # REGRA 16 (Verificação pelo COD exclusiva do COD)
        falha_r16 = False
        teve_verificacao_cod = False
        executores_invalidos_r16 = set()
        for mi in manobra_items:
            eh = mi.get('etapa_texto_header', '')
            if re.search(r'\bVERIFICA[CÇ]?[AÃ]?O\s*(?:PELO|DO|DA)?\s*COD\b', eh + " " + mi.get('etapa_nome', '') + " " + mi['texto_linha'] + " " + mi.get('observacao', ''), re.IGNORECASE):
                teve_verificacao_cod = True
                execut = mi['executor'].upper()
                if not re.search(r'\bCOD\b', execut, re.IGNORECASE):
                    falha_r16 = True
                    executores_invalidos_r16.add(execut if execut else "Vazio")
        if falha_r16:
            str_executores = ", ".join(sorted(executores_invalidos_r16))
            print_regra(16, "ERRO", f"A etapa 'VERIFICAÇÃO PELO COD' possui executor inválido ('{str_executores}') para o equipamento '{eq}'.")
        elif teve_verificacao_cod:
            print_regra(16, "OK", f"Etapa de verificação pelo COD realizada corretamente para o equipamento '{eq}'.")
        else:
            pass  # IGNORADA silenciosa

        # REGRA 17 (Verificação de Anormalidade MA09 vs By-pass)
        falha_r17 = False
        teve_ma09 = False
        motivo_r17 = ""
        for mi in manobra_items:
            if re.search(r'\b\d*MA09\b', mi['texto_linha'], re.IGNORECASE):
                teve_ma09 = True
                txt = mi['texto_linha'].upper()
                is_bypass = "BY-PASS" in txt or "BYPASS" in txt or "PASSAR" in txt
                
                if not is_bypass and not is_alim:
                    falha_r17 = True
                    motivo_r17 = "Macro MA09 (Anormalidade) só deve ser executada para o Alimentador como um todo."
                elif is_bypass and prefixo not in ["02", "22", "23"]:
                    falha_r17 = True
                    motivo_r17 = f"Macro MA09 (By-pass) aplicada em equipamento '{eq}'. Permitido apenas em prefixos 02, 22, 23."
        if falha_r17:
            print_regra(17, "ERRO", motivo_r17)
        elif teve_ma09:
            print_regra(17, "OK", "Macro MA09 (Anormalidade/By-pass) aplicada corretamente conforme o contexto.")
        else:
            pass  # IGNORADA silenciosa

        # REGRA 18 (Comandos de By-pass)
        macros_bypass = ["MAB8", "MAB9", "MA09"]
        falhas_r18 = set()
        teve_bypass = False
        for mi in manobra_items:
            eh = mi.get('etapa_texto_header', '')
            is_cod = bool(re.search(r'\bCOD\b', mi['executor'], re.IGNORECASE)) or bool(re.search(r'\bVERIFICA[CÇ]?[AÃ]?O\s*(?:PELO|DO|DA)?\s*COD\b', eh + " " + mi.get('etapa_nome', '') + " " + mi['texto_linha'], re.IGNORECASE))
            for m_bp in macros_bypass:
                if re.search(r'\b\d*' + m_bp + r'\b', mi['texto_linha'], re.IGNORECASE):
                    # Exceção: MA09 na verificação do COD não é tratada como by-pass nesta regra
                    if m_bp.upper() == "MA09" and is_cod:
                        continue 
                    teve_bypass = True
                    if prefixo not in ["02", "22", "23"]:
                        falhas_r18.add(m_bp.upper())
        if falhas_r18:
            str_bp = ", ".join(sorted(falhas_r18))
            print_regra(18, "ERRO", f"Comandos de by-pass ({str_bp}) detectados em '{eq}'. Permitido apenas para prefixos 02, 22 e 23.")
        elif teve_bypass:
            print_regra(18, "OK", f"Comandos de by-pass em '{eq}' aplicados em equipamento autorizado.")
        else:
            pass  # IGNORADA silenciosa

        # REGRA 19 (MAC1 exclusiva para equipamento físico)
        teve_mac1 = False
        falha_r19 = False
        for mi in manobra_items:
            if re.search(r'\b\d*MAC1\b', mi['texto_linha'], re.IGNORECASE):
                teve_mac1 = True
                if is_alim:
                    falha_r19 = True
        if falha_r19:
            print_regra(19, "ERRO", f"Macro MAC1 aplicada indevidamente em Alimentador '{eq}'. Esta macro exige um equipamento físico.")
        elif teve_mac1:
            print_regra(19, "OK", f"Macro MAC1 aplicada corretamente em equipamento físico '{eq}'.")
        # REGRA 39 (Posicionamento para Manobra x Abertura/Fechamento e Região)
        falhas_r39 = set()
        for mi in manobra_items:
            posic = mi.get('posicionamento', '').upper()
            if posic == 'SIM':
                execut = mi.get('executor', '').upper()
                txt = mi.get('texto_linha', '').upper()
                
                is_abertura = bool(macros_abertura.search(txt) or re.search(r'\bABRIR\b', txt))
                is_fechamento = bool(macros_fechamento.search(txt) or re.search(r'\bFECHAR\b', txt))
                
                is_regiao = ('REGIAO' in execut or 'REGIÃO' in execut)
                
                if not (is_abertura or is_fechamento):
                    falhas_r39.add(f"Ação não é Abertura/Fechamento (Ação detectada: {txt.strip()[:20]})")
                if not is_regiao:
                    falhas_r39.add(f"Executor não é Região (Atual: {execut})")
                    
        if falhas_r39:
            str_falhas = ", ".join(sorted(falhas_r39))
            print_regra(39, "ERRO", f"Equipamento '{eq}': Posicionamento marcado como 'Sim', mas violou as diretrizes: {str_falhas}.")
        else:
            tem_pos_sim = any(mi.get('posicionamento', '').upper() == 'SIM' for mi in manobra_items)
            if tem_pos_sim:
                print_regra(39, "OK", f"Posicionamento de '{eq}' justificado com executor Região e ação de Abertura/Fechamento.")
            else:
                pass # IGNORADA silenciosa

    print("\n" + "="*80)
    print("\n=== FASE: Relações de Equipes (Fase 4.1) ===")
    print("="*80)
    # REGRA 35 (Equipes no Cabeçalho vs Executor Região)
    if manobra_dados and manobra_etapas_headers:
        texto_primeira = manobra_etapas_headers[0]['texto'].upper()
        tem_equipes_header = bool(re.search(r'\bEQUIPES\b\s*:\s*\d+', texto_primeira))
        
        tem_executor_regiao = any('REGIAO' in mi.get('executor', '').upper() or 'REGIÃO' in mi.get('executor', '').upper() for mi in manobra_dados)
        
        if tem_executor_regiao and not tem_equipes_header:
            print_regra(35, "ERRO", "Identificado executor 'Região', mas a diretriz 'EQUIPES:X' não foi informada no cabeçalho da primeira etapa.")
        elif tem_equipes_header and not tem_executor_regiao:
            print_regra(35, "ALERTA", "Informado 'EQUIPES:X' no cabeçalho, mas nenhum passo possui executor 'Região'.")
        else:
            if tem_equipes_header and tem_executor_regiao:
                print_regra(35, "OK", "Equipes informadas no cabeçalho e confirmadas por ações da Região.")
            else:
                pass # Ninguém tem Região nem Equipes: OK silencioso

    print("\n=== FASE: Balanço e Cronologia (Fase 5) ===")
    if not manobra_map:
        print("⚠️  Manobra vazia. Sem equipamentos manobrados.")
        
    falhas_r22 = {}
    for eq, manobra_items in manobra_map.items():
        print(f"\n🔹 Equipamento: {eq}")
        
        # Obtém prefixo do equipamento para inverter MA77 corretamente (Regra 22)
        eq_info_rule22 = _get_eq_data(dados_equipamentos, eq, next((mi.get('alim','') for mi in manobra_items), ''))
        prefixo_eq = "01" if re.match(r"^\d{5,7}\s*-\s*\d+\s*-\s*\d+$", eq) else (eq.split('-')[0].strip().zfill(2) if '-' in eq else "")
        
        # REGRA 2 (Ação Inicial de Abertura) - Apenas para equipamentos da solicitação
        if eq in sol_dict:
            padrao_abrir = re.compile(r'\b(abrir|aberto|sinalizar|sinalizado)\b', re.IGNORECASE)
            if any(padrao_abrir.search(mi['texto_linha']) for mi in manobra_items):
                print_regra(2, "OK", f"Ação inicial de abrir/sinalizar confirmada para o equipamento '{eq}'.")
            else:
                print_regra(2, "ALERTA", f"Equipamento '{eq}' presente na manobra sem detecção de ação inicial de Abrir ou Sinalizar.")

        # REGRA 22 (Ações Inversas / Esquecidas / Cronologia de Bloqueios)
        rastreamento_inversas = {
            "Bastão de Secc. (MA58/MA59)": (["MA58"], ["MA59"]),
            "Equip. em Serviço (MA68/MA69)": (["MA68"], ["MA69"]),
            "By-pass (MA09/MA10)": (["MA09"], ["MA10"]),
            "Sinalização/RN/ST (MA06/MA07)": (["MA06"], ["MA07"]),
            "Bloq RA Relig. (MA14/MA16)": (["MA14"], ["MA16"]),
            "Bloq ST Relig. (MA15/MA17)": (["MA15"], ["MA17"]),
            "At/Sinaliz. (MA30/MA67)": (["MA31", "MA30"], ["MA67", "MA66"]), # MA31 vira MA66, MA30 vira MA67
            "Bloq RA Equip. (MA21/MA23)": (["MA21"], ["MA23"]),
            "Bloq RA Chave (MA28/MA29)": (["MA28"], ["MA29"]),
            "Rede BT (MA56/MA57)": (["MA56"], ["MA57"]),
            "Rede MT (MA54/MA55)": (["MA54"], ["MA55"]),
            "Aterramento (MA42/MA43)": (["MA42"], ["MA43"]),
            "Aut. COD Deslig. (MA40/MA41)": (["MA40"], ["MA41"]),
            "Bloq RA COD (MA52/MA53)": (["MA52"], ["MA53"]),
            "Barramento (MA24/MA25)": (["MA24"], ["MA25"]),
            "Disjuntor/Relig. (MA18/MA19)": (["MA18"], ["MA19"]),
            "PLE (MA96/MA97)": (["MA96"], ["MA97"]),
            "Subestação (MA22/MA23)": (["MA22"], ["MA23"]),
            "Bloq RA Genérico (MA04/MA05)": (["MA04"], ["MA05"]),
            "Ajuste Alt. (MAA1/MAA2/MAA3/MA89)": (["MAA1", "MAA2", "MAA3"], ["MA89"]),
            "Transf. Auto (MAA4/MAA5)": (["MAA4"], ["MAA4"]), # MAA4 vira MAA5 mas na volta? Geralmente MAA5
            "Aut. Manobrar (MAA7/MAA8)": (["MAA7"], ["MAA8"]),
            "Intert/Aterramento (MAA9/MAB1)": (["MAA9"], ["MAB1"]),
            "Test/At/Intert (MAB2/MAB3)": (["MAB2"], ["MAB3"]),
            "Intertravar (MAB4/MAB5)": (["MAB4"], ["MAB5"]),
            "Disjuntor Cliente (MAB6/MAB7)": (["MAB6"], ["MAB7"]),
            "PLE COD (MAC2/MA26)": (["MAC2"], ["MA26"]),
            "Aut. Serviço (MAAS/MATS)": (["MAAS"], ["MATS"]),
            "Abertura Simples (MA01/MA02)": (["MA01"], ["MA02"]),
            "Modo Local (MA64/MA65)": (["MA64"], ["MA65"])
        }
        
        if prefixo_eq == "02":
            rastreamento_inversas["RT: Neutro/Tap (MA35/MA77 -> MA36)"] = (["MA35", "MA77"], ["MA36"])
        else:
            rastreamento_inversas["2º Relé Neutro/Tap (MA77/MA78)"] = (["MA77"], ["MA78"])
            rastreamento_inversas["Regulador Neutro (MA35/MA36)"] = (["MA35"], ["MA36"])
        
        # Bloqueios Críticos que exigem verificação de cronologia (Lock -> Unlock após desligamento)
        # Formato: { "Lock": "Unlock", "Nome Amigável": GroupName }
        bloqueios_cronologicos = {
            "MA06": ("MA07", "Sinalização/RN/ST"),
            "MA14": ("MA16", "Bloqueio RA Religador"),
            "MA15": ("MA17", "Bloqueio ST Religador")
        }
        
        saldos = {k: 0 for k in rastreamento_inversas}
        counts_bloqueios = {m: {"pre": 0, "post": 0} for m in ["MA06", "MA07", "MA14", "MA16", "MA15", "MA17"]}
        
        passou_deslig = False
        teve_rastreio_inversa = False

        for mi in manobra_items:
            etapa_txt = (mi.get('etapa_nome', '') + ' ' + mi.get('etapa_texto_header', '')).upper()
            if "DESLIGAMENTO" in etapa_txt: passou_deslig = True
            
            txt = mi['texto_linha'].upper()
            
            # Contagem para validação cronológica (Fase PRE e POST)
            for m_lock in counts_bloqueios.keys():
                if re.search(_re_macro(m_lock), txt):
                    zona = "post" if passou_deslig else "pre"
                    counts_bloqueios[m_lock][zona] += 1

            for nome_grupo, (aberturas, fechamentos) in rastreamento_inversas.items():
                for m_ab in aberturas:
                    if re.search(_re_macro(m_ab), txt):
                        saldos[nome_grupo] += 1
                        teve_rastreio_inversa = True
                for m_fe in fechamentos:
                    if re.search(_re_macro(m_fe), txt):
                        saldos[nome_grupo] -= 1
                        teve_rastreio_inversa = True

        # Analisa falhas cronológicas e de esquecimento
        falhas_r22_list = []
        
        # 1. Verificação de Equilíbrio Geral (Saldos)
        for grupo, saldo in saldos.items():
            if saldo != 0:
                acao_falta = "Inversão/Normalização" if saldo > 0 else "Ação Inicial/Bloqueio"
                falhas_r22_list.append(f"{grupo} ({acao_falta} ausente)")

        # 2. Verificação Cronológica Específica para Bloqueios
        for m_lock, (m_unlock, nome_friendly) in bloqueios_cronologicos.items():
            tot_lock = counts_bloqueios[m_lock]["pre"] + counts_bloqueios[m_lock]["post"]
            tot_unlock = counts_bloqueios[m_unlock]["pre"] + counts_bloqueios[m_unlock]["post"]
            
            if tot_lock > 0:
                # Se bloqueou, deve ter desbloqueado
                if tot_unlock == 0:
                    falhas_r22_list.append(f"{nome_friendly}: Bloqueou ({m_lock}) mas NÃO normalizou ({m_unlock})")
                elif tot_lock != tot_unlock:
                    falhas_r22_list.append(f"{nome_friendly}: Quantidade de {m_lock} ({tot_lock}) difere de {m_unlock} ({tot_unlock})")
                
                # Regra de Ouro: Bloqueio deve vir ANTES da normalização
                if counts_bloqueios[m_unlock]["pre"] > counts_bloqueios[m_lock]["pre"]:
                    falhas_r22_list.append(f"{nome_friendly}: Normalização ({m_unlock}) detectada antes do Bloqueio ({m_lock})")

        if falhas_r22_list:
            str_falhas = " | ".join(sorted(set(falhas_r22_list)))
            print_regra(22, "ERRO", f"Equipamento '{eq}': {str_falhas}")
        elif teve_rastreio_inversa:
            print_regra(22, "OK", f"Equilíbrio de ações e cronologia de bloqueios validados em '{eq}'.")
        else:
            pass  # IGNORADA silenciosa

        # REGRA 30 (Ordem Cronológica de Ações)
        saldos_crono = {k: 0 for k in rastreamento_inversas}
        falhas_r30 = set()
        teve_acao_crono = False

        for mi in manobra_items:
            txt = mi['texto_linha'].upper()
            eh = mi.get('etapa_texto_header', '').upper()
            etapa_nome = eh + " " + mi.get('etapa_nome', '').upper()
            is_verificacao_cod = bool(re.search(r'\bVERIFICA[CÇ][AÃ]O\s+PELO\s+COD\b', etapa_nome)) or bool(re.search(r'\bVERIFICA[CÇ][AÃ]O\s+PELO\s+COD\b', txt))
            
            if is_verificacao_cod:
                if re.search(r'\b\d*MA39\b', txt):
                    if "Abertura Simples (MA01/MA02)" in saldos_crono: saldos_crono["Abertura Simples (MA01/MA02)"] += 1
                    if "Abertura (MA31/MA66)" in saldos_crono: saldos_crono["Abertura (MA31/MA66)"] += 1
                    if "At/Sinaliz. (MA30/MA67)" in saldos_crono: saldos_crono["At/Sinaliz. (MA30/MA67)"] += 1
                    if "Disjuntor/Relig. (MA18/MA19)" in saldos_crono: saldos_crono["Disjuntor/Relig. (MA18/MA19)"] += 1
                    teve_acao_crono = True
                if re.search(r'\b\d*MA49\b', txt):
                    if "Abertura Simples (MA01/MA02)" in saldos_crono: saldos_crono["Abertura Simples (MA01/MA02)"] = 0
                    if "Abertura (MA31/MA66)" in saldos_crono: saldos_crono["Abertura (MA31/MA66)"] = 0
                    if "At/Sinaliz. (MA30/MA67)" in saldos_crono: saldos_crono["At/Sinaliz. (MA30/MA67)"] = 0
                    if "Disjuntor/Relig. (MA18/MA19)" in saldos_crono: saldos_crono["Disjuntor/Relig. (MA18/MA19)"] = 0
                    teve_acao_crono = True

            for nome_grupo, (aberturas, fechamentos) in rastreamento_inversas.items():
                for m_ab in aberturas:
                    if re.search(_re_macro(m_ab), txt):
                        saldos_crono[nome_grupo] += 1
                        teve_acao_crono = True
                
                for m_fe in fechamentos:
                    if re.search(_re_macro(m_fe), txt):
                        # Equipamentos NA (normalmente abertos/tie switch) podem iniciar com
                        # fechamento sem abertura prévia. Na verdade, operações de chaveamento
                        # devem ser ignoradas da regra de pré-condição estrita da Regra 30.
                        if saldos_crono[nome_grupo] <= 0:
                            if nome_grupo not in ["Abertura Simples (MA01/MA02)", "Abertura (MA31/MA66)", "At/Sinaliz. (MA30/MA67)", "Disjuntor/Relig. (MA18/MA19)", "Subestação (MA22/MA23)", "Barramento (MA24/MA25)", "Rede BT (MA56/MA57)", "Rede MT (MA54/MA55)"]:
                                falhas_r30.add(f"'{m_fe}' sem '{'/'.join(aberturas)}' prévio")
                        else:
                            saldos_crono[nome_grupo] -= 1
                        teve_acao_crono = True

        if falhas_r30:
            str_falhas = ", ".join(sorted(falhas_r30))
            print_regra(30, "ERRO", f"Ordem cronológica invertida no equipamento '{eq}': {str_falhas}")
        elif teve_acao_crono:
            print_regra(30, "OK", f"Ações e reversões executadas na ordem cronológica correta em '{eq}'.")
        else:
            pass  # IGNORADA silenciosa

    # FASE 6: COMPATIBILIDADE E SINCRONISMO FINAL
    print("\n=== FASE: Compatibilidade e Sincronismo Final (Fase 6) ===")

    # REGRA 32 (Incompatibilidade de Fases: Abrir Trifásico e Fechar Monofásico no MESMO ALIMENTADOR)
    print("🔹 Verificando Compatibilidade de Fases (Regra 32)...")
    falhas_r32 = False
    teve_fases = False
    
    def get_etapa_ident(mi):
        return mi.get('grupo_id', 'Bloco_Desconhecido')
        
    grupos_etapas = set(get_etapa_ident(mi) for m_items in manobra_map.values() for mi in m_items)
    
    for eh_grupo in grupos_etapas:
        if not eh_grupo or eh_grupo == '|': continue
        # Agrupar por alimentador dentro de cada etapa para não confundir circuitos distintos
        abertos_por_alim = {}   # alim -> [(eq, fases)]
        fechados_por_alim = {}  # alim -> [(eq, fases)]
        
        for eq_map, m_items in manobra_map.items():
            for mi in m_items:
                if get_etapa_ident(mi) != eh_grupo: continue
                txt = mi['texto_linha'].upper()
                alim_key = mi.get('alim', '') or 'SEM_ALIM'
                fases_eq = _get_eq_data(dados_equipamentos, eq_map, mi.get('alim', '')).get('fases', '')
                if not fases_eq: continue
                if re.search(r'\b\d*(MA01|MA31|MA30|MA18|MA22|MA24|MA54|MA56|MAA9)\b(?!\s*-\s*OUTROS)', txt) or re.search(r'\bABRIR\b', txt):
                    abertos_por_alim.setdefault(alim_key, []).append((eq_map, fases_eq))
                elif re.search(r'\b\d*(MA02|MA66|MA67|MA19|MA23|MA25|MA55|MA57|MAB1)\b(?!\s*-\s*OUTROS)', txt) or re.search(r'\bFECHAR\b', txt):
                    fechados_por_alim.setdefault(alim_key, []).append((eq_map, fases_eq))
        
        # Verifica incompatível apenas quando o MESMO alimentador tem tri aberto e mono fechado
        for alim_key in set(abertos_por_alim.keys()) & set(fechados_por_alim.keys()):
            abriu_tri = [e for e, f in abertos_por_alim[alim_key] if f == 'ABC']
            fechou_mono = [e for e, f in fechados_por_alim[alim_key] if f in ['A', 'B', 'C']]
            if abriu_tri and fechou_mono:
                falhas_r32 = True
                str_tri = ", ".join(abriu_tri)
                str_mono = ", ".join(fechou_mono)
                print_regra(32, "ERRO", f"Etapa '{eh_grupo}' | Alim {alim_key}: Abrindo Trifásico ({str_tri}) e Fechando Monofásico ({str_mono}) na mesma etapa.")
            elif abriu_tri or fechou_mono:
                teve_fases = True
    
    if not falhas_r32 and teve_fases:
        print_regra(32, "OK", "Compatibilidade de fases validada nas transferências por alimentador.")

    # REGRA 33 (MA30 ASTA sem carga)
    print("🔹 Verificando Chave ASTA (Regra 33)...")
    falha_r33 = False
    for mi in manobra_dados:
        tx = mi.get('texto_linha', '').upper()
        ob = mi.get('observacao', '').upper()
        if re.search(r'\b\d*MA30\b', tx, re.IGNORECASE):
            # Se encontrar MA30, deve ter "COM CARGA"
            if "COM CARGA" not in (tx + " " + ob):
                falha_r33 = True
                print_regra(33, "ERRO", "Chave ASTA (MA30) operada sem indicação de 'COM CARGA'.")
    if not falha_r33 and any(re.search(r'\b\d*MA30\b', mi.get('texto_linha', ''), re.IGNORECASE) for mi in manobra_dados):
        print_regra(33, "OK", "Todas as operações de chave ASTA (MA30) possuem indicação de 'COM CARGA'.")

    # REGRA 35 (Validação de Equipes/Região)
    print("🔹 Verificando Equipes vs Executor (Regra 35)...")
    if 'num_equipes_header' in locals() and num_equipes_header > 0:
        tem_regiao = False
        for mi in manobra_dados:
            exec_norm = _norm_str(mi.get('executor', ''))
            if "REGIAO" in exec_norm:
                tem_regiao = True
                break
        
        if not tem_regiao:
            print_regra(35, "ALERTA", f"Cabeçalho indica EQUIPES:{num_equipes_header}, mas nenhuma ação possui 'Região' como executor.")
        else:
            print_regra(35, "OK", "Equipes indicadas no cabeçalho e confirmadas por ações da Região.")

    # REGRA 36 (Sincronismo de Horário: Item vs Etapa)
    print("🔹 Verificando Sincronismo de Horário (Regra 36)...")
    falhas_r36 = []
    for mi in manobra_dados:
        eh_str = mi.get('etapa_texto_header', '')
        m_dt_header = re.search(r'(\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2})', eh_str)
        dt_item_str = mi.get('data_hora', '').strip()
        
        if m_dt_header and dt_item_str and dt_item_str != "-":
            dt_header = m_dt_header.group(1)
            if len(dt_item_str) <= 5: 
                data_prefix = dt_header.split()[0]
                dt_item_completa = f"{data_prefix} {dt_item_str}"
            else:
                dt_item_completa = dt_item_str
            
            if dt_header != dt_item_completa:
                eq_id = mi.get('equipamento') or mi.get('alimentador') or "Item"
                falhas_r36.append(f"Etapa '{dt_header}' vs Item '{dt_item_completa}' em '{eq_id}'")

    if falhas_r36:
        for f in falhas_r36: print_regra(36, "ALERTA", f"Divergência de horário detectada: {f}")
    else:
        print_regra(36, "OK", "Horários dos itens perfeitamente sincronizados com os cabeçalhos das etapas.")

    # REGRA 37 (Executor MA60 deve ser COD)
    print("🔹 Verificando Executor MA60 (Regra 37)...")
    falhas_r37 = []
    for mi in manobra_dados:
        txt_alvo = (mi.get('acao_bruta', '') + " " + mi.get('texto_linha', '')).upper()
        if re.search(r'\b\d*MA60\b', txt_alvo):
            execut = mi.get('executor', '').upper()
            if "COD" not in execut:
                eq_id = mi.get('equipamento') or mi.get('alimentador') or "Item"
                falhas_r37.append(f"Ação MA60 em '{eq_id}' possui executor '{execut}' (Exige COD)")

    if falhas_r37:
        for f in falhas_r37: print_regra(37, "ERRO", f)
    elif any(re.search(r'\b\d*MA60\b', (mi.get('acao_bruta','') + " " + mi.get('texto_linha','')).upper()) for mi in manobra_dados):
        print_regra(37, "OK", "Todas as ações MA60 (Abertura sob Carga) atribuídas corretamente ao COD.")
    else:
        print_regra(37, "OK", "Nenhuma ação MA60 (Abertura sob Carga) detectada ou necessária.")

    # REGRA 38 (Validação de Equipamentos Manuais vs Executor COD)
    if 'num_equipes_header' in locals() and num_equipes_header > 0:
        print("\n=== FASE: Equipamentos Manuais (Regra 38) ===")
        falhas_r38 = []
        etapas_alvo = ["MANOBRA", "MANOBRA COM RISCO SISTEMA", "MANOBRA COM PIQUE"]
        macros_alvo = ["MA01", "MA02", "MA31", "MA66", "MA30", "MA67"]
        
        for mi in manobra_dados:
            etapa_nome = mi.get('etapa_nome', '').upper()
            if any(e in etapa_nome for e in etapas_alvo):
                txt_alvo = (mi.get('acao_bruta', '') + " " + mi.get('texto_linha', '')).upper()
                # Verifica se contém alguma das macros alvo
                if any(re.search(r'\b\d*' + m + r'\b', txt_alvo) for m in macros_alvo):
                    eq_nome = mi.get('equipamento', '')
                    alim = mi.get('alim', '')
                    info_eq = _get_eq_data(dados_equipamentos, eq_nome, alim)
                    
                    # Se NÃO for telecontrolado e executor for COD -> ERRO
                    if info_eq and info_eq.get('telecontrolado') is False:
                        execut = mi.get('executor', '').upper()
                        if "COD" in execut:
                            falhas_r38.append(f"Equipamento manual '{eq_nome}' na etapa '{etapa_nome}' está com executor '{execut}' (Deveria ser REGIAO)")

        if falhas_r38:
            for f in falhas_r38: print_regra(38, "ERRO", f)
        else:
            print_regra(38, "OK", "Operações em equipamentos manuais executadas corretamente pela Região.")

    # REGRA 43 (Executor em Desligamento/Religamento)
    print("\n=== FASE: Desligamento/Religamento (Regra 43) ===")
    falhas_r43 = []
    alertas_r43 = []
    for mi in manobra_dados:
        et_nome = mi.get('etapa_nome', '').upper()
        if "DESLIGAMENTO" in et_nome or "RELIGAMENTO" in et_nome:
            executor = mi.get('executor', '').upper()
            obs = mi.get('observacao', '').upper()
            
            if "SUPERVISOR" not in executor:
                eq_id = mi.get('equipamento') or mi.get('alimentador') or "Item"
                msg = f"Equipamento '{eq_id}' na etapa '{et_nome}' com executor '{executor}'"
                
                # Se for COD + PARA REFLETIR -> ALERTA
                if "COD" in executor and "PARA REFLETIR" in obs:
                    alertas_r43.append(f"{msg} (Alerta: Possui 'PARA REFLETIR')")
                else:
                    falhas_r43.append(f"{msg} (Erro: Exige SUPERVISOR)")

    if falhas_r43:
        for f in falhas_r43: print_regra(43, "ERRO", f)
    if alertas_r43:
        for a in alertas_r43: print_regra(43, "ALERTA", a)
    if not falhas_r43 and not alertas_r43:
        print_regra(43, "OK", "Todas as etapas de Desligamento/Religamento executadas pelo Supervisor conforme norma.")

    # ============================================================
    # FIM DA VERIFICAÇÃO
    # ============================================================

        # Encerramento ordenado e seguro: page -> context -> browser
        # Cada etapa em try/except para evitar "Event loop is closed"
        try:
            page.close()
        except Exception:
            pass
        try:
            context.close()
        except Exception:
            pass
        try:
            browser.close()
        except Exception:
            pass

    print("\n" + f"{Colors.GREEN}{Colors.BOLD}" + "="*57)
    print("      VERIFICAÇÃO CONCLUÍDA COM SUCESSO!         ")
    print("="*57 + f"{Colors.RESET}")
    
    if not manobra_param:
        input("\nPressione Enter para encerrar...")

if __name__ == "__main__":
    main()