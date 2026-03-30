import os
import re
import getpass
from playwright.sync_api import sync_playwright

URL_LOGIN = "http://gdis-pm/gdispm/"

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
    """Constrói regex para detectar a macro 'm' no texto, excluindo variantes 'MA18 - Outros'.
    O lookahead negativo (?!\s*-\s*OUTROS) garante que 'MA18 - OUTROS' não seja confundido
    com o código de ação MA18 (ABRIR E SINALIZAR DISJUNTOR/RELIGADOR)."""
    return r'\b\d*' + re.escape(m) + r'\b(?!\s*-\s*OUTROS)'

def _norm_alim_match(s):
    """Normaliza o alimentador para bater nomes como PZLU008 e PZLU08"""
    if not s: return ""
    s = re.sub(r"[^A-Z0-9]", "", str(s).upper())
    return re.sub(r"([A-Z]+)0+(\d+)", r"\1\2", s)

def _get_eq_data(dados, eq, alim1, alim2=""):
    """Busca os dados do equipamento resolvendo conflitos de nomes iguais pelo Alimentador (REFALM)"""
    lista = dados.get(eq)
    
    # Fallback inteligente: se a manobra tem prefixo (24 - 83306) mas no CSV está só o número (83306)
    if not lista and '-' in eq:
        sem_prefixo = eq.split('-', 1)[1].strip()
        lista = dados.get(sem_prefixo)
        
        # Fallback secundário: tenta buscar tudo junto sem espaços (ex: 24-83306)
        if not lista:
            lista = dados.get(eq.replace(' ', ''))
        
        # Fallback terciário: limpar formatações completas
        if not lista:
            eq_clean = re.sub(r"[^A-Z0-9]", "", eq.upper())
            for k, v in dados.items():
                if re.sub(r"[^A-Z0-9]", "", k.upper()) == eq_clean:
                    lista = v
                    break
    if not lista: return {}
    if isinstance(lista, dict): lista = [lista]
    if len(lista) == 1: return lista[0]
    a1 = _norm_alim_match(alim1)
    a2 = _norm_alim_match(alim2)
    if a1:
        for item in lista:
            if item.get('alimentador') == a1: return item
    if a2:
        for item in lista:
            if item.get('alimentador') == a2: return item
    return lista[0]

def _obter_regras_equipamentos():
    """Dicionário de equipamentos e ações PROIBIDAS para cada prefixo (Sincronizado com Excel)"""
    return {
        "01": ["MA64","MA65", "MA35","MA36", "MA77", "MAB9"],
        "02": [], # REGULADOR DE TENSAO (Tudo permitido)
        "03": ["MA64","MA65", "MA35","MA36", "MA77", "MAB9"],
        "04": ["MA64","MA65", "MA35","MA36", "MA77", "MAB9"],
        "11": ["MA64","MA65", "MA35","MA36", "MA77", "MAB9"],
        "13": ["MA64","MA65", "MAB9"],
        "15": ["MA64","MA65", "MAB9"],
        "19": ["MA35","MA36", "MA77", "MA64", "MA65"],
        "20": ["MA35","MA36", "MA77", "MA64", "MA65"],
        "21": ["MA35","MA36", "MA77"],
        "22": ["MA35","MA36", "MA77"],
        "23": ["MA35","MA36", "MA77"],
        "24": ["MA35","MA36", "MA77", "MA64", "MA65", "MAB9"],
        "27": ["MA35","MA36", "MA77", "MA64", "MA65", "MAB9"],
        "28": ["MA64","MA65", "MA35","MA36", "MA77", "MAB9"],
        "30": ["MA64","MA65", "MA35","MA36", "MA77", "MAB9"],
        "34": ["MA64","MA65", "MA35","MA36", "MA77", "MAB9"],
        "36": ["MA64","MA65", "MA35","MA36", "MA77", "MAB9"],
        "50": ["MA64","MA65", "MA35","MA36", "MA77", "MAB9"],
        "60": ["MA64","MA65", "MA35","MA36", "MA77", "MAB9"],
        "61": ["MA64","MA65", "MA35","MA36", "MA77", "MAB9"],
    }

def _carregar_dados_equipamentos():
    import json
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    caminho_csv_local = os.path.join(root_dir, "data", "equipamentos_gemini.csv")
    caminho_csv_rede = r"I:\IT\ODCO\PUBLICA\Kennedy\Projetos\dados Gemini\equipamentos_gemini.csv"
    caminho_csv = caminho_csv_local if os.path.exists(caminho_csv_local) else caminho_csv_rede
    caminho_cache = os.path.join(root_dir, "temp", "equipamentos_cache.json")
    os.makedirs(os.path.dirname(caminho_cache), exist_ok=True)
    csv_existe, cache_existe = os.path.exists(caminho_csv), os.path.exists(caminho_cache)
    if cache_existe:
        if not csv_existe or os.path.getmtime(caminho_cache) >= os.path.getmtime(caminho_csv):
            try:
                with open(caminho_cache, 'r', encoding='utf-8') as f: return json.load(f)
            except: pass
    import tempfile
    caminho_cache_temp = os.path.join(tempfile.gettempdir(), "equipamentos_cache.json")
    if os.path.exists(caminho_cache_temp):
        if not csv_existe or os.path.getmtime(caminho_cache_temp) >= os.path.getmtime(caminho_csv):
            try:
                with open(caminho_cache_temp, 'r', encoding='utf-8') as f: return json.load(f)
            except: pass
    dados = {}
    if not csv_existe: return dados
    try:
        import pandas as pd
        try: df = pd.read_csv(caminho_csv, sep=';', encoding='latin1', dtype=str)
        except: df = pd.read_csv(caminho_csv, sep=',', encoding='utf-8', dtype=str)
        df.fillna('', inplace=True)
        col_tele = next((c for c in df.columns if 'TELECONTROLADO' in str(c).upper()), None)
        col_eqpto = next((c for c in df.columns if str(c).upper() in ['EQUIPAMENTO', 'CODIGO', 'NUMERO', 'CÓDIGO', 'EQPTO']), None)
        col_posope = next((c for c in df.columns if 'POSOPE' in str(c).upper() or 'ESTADO' in str(c).upper()), None)
        col_fases = next((c for c in df.columns if 'FASES' in str(c).upper() or 'FASE' in str(c).upper()), None)
        col_alim = next((c for c in df.columns if 'ALIMENTADOR' in str(c).upper() or 'REFALM' in str(c).upper()), None)
        if col_tele and col_eqpto:
            for eq_val, t_val, p_val, f_val, a_val in zip(df[col_eqpto].values, df[col_tele].values, df[col_posope].values, df[col_fases].values, df[col_alim].values):
                eq, tele, posope, fases, alim_val = _norm_eqpto(str(eq_val)), str(t_val).strip().upper() == 'T', str(p_val).strip().upper(), str(f_val).strip().upper(), str(a_val).strip().upper()
                if eq not in dados: dados[eq] = []
                dados[eq].append({'telecontrolado': tele, 'posope': posope, 'fases': fases, 'alimentador': alim_val})
        try:
            with open(caminho_cache, 'w', encoding='utf-8') as f: json.dump(dados, f, ensure_ascii=False)
        except:
            try:
                with open(caminho_cache_temp, 'w', encoding='utf-8') as f: json.dump(dados, f, ensure_ascii=False)
            except: pass
    except: pass
    return dados

class _DualWriter:
    def __init__(self, real_stdout, buffer): self._real, self._buf = real_stdout, buffer
    def write(self, msg): self._real.write(msg); self._buf.write(msg)
    def flush(self): self._real.flush(); self._buf.flush()

def main(manobra_param=None, usuario_param=None, senha_param=None, headless=False):
    manobra_num = manobra_param if manobra_param else input("Manobra Base: ").strip()
    usuario = usuario_param or os.getenv("GDIS_USUARIO") or input("Usuário: ").strip()
    senha = senha_param or os.getenv("GDIS_SENHA") or getpass.getpass("Senha: ")
    regras_equipamentos, dados_equipamentos = _obter_regras_equipamentos(), _carregar_dados_equipamentos()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless if manobra_param else False)
        page = browser.new_page()
        page.goto(URL_LOGIN)
        if page.locator("input[id='formLogin:userid']").count() > 0:
            page.fill("input[id='formLogin:userid']", str(usuario))
            page.fill("input[id='formLogin:password']", str(senha))
            page.click("input[id='formLogin:botao']")
        page.click("text=Consultas"); page.click("text=Manobra")
        page.fill("input[id='formPesquisa:numeroManobra']", manobra_num)
        page.click("input[id='formPesquisa:j_id109']") # Pesquisar
        page.wait_for_selector("table[id*='resulPesManobra']", timeout=15000)
        solicitacao_num = page.evaluate(f"(m) => {{ const t = document.querySelector(\"table[id*='resulPesManobra']\"); if(!t) return null; const rows = Array.from(t.querySelectorAll('tbody tr')); for(const r of rows){{ const tds = r.querySelectorAll('td'); if(tds.length > 5 && tds[2].innerText.replace(/\\D/g,'') === String(m)) return tds[5].innerText.replace(/\\D/g,''); }} return null; }}", manobra_num)
        page.evaluate(f"(num) => {{ const links = Array.from(document.querySelectorAll(\"table[id*='resulPesManobra'] a\")); const l = links.find(x => (x.innerText || '').includes(String(num))); if(l) l.click(); }}", manobra_num)
        page.wait_for_selector("div[id*='etapasManobraSimplePanelId']", timeout=15000)
        manobra_dados = page.evaluate("""() => {
            const clean = (s) => (s || '').replace(/[\\s\\xA0]+/g, ' ').replace(/SimpleTogglePanelManager\\.add\\(.*?\\);?/gi, '').replace(/[«»]/g, '').trim();
            const res = [];
            document.querySelectorAll("table[id$=':itensCadastrados']").forEach(t => {
                const hNode = document.getElementById(t.closest("div[id$='_body']").id.replace('_body','_header'));
                const etapaH = hNode ? clean(hNode.textContent) : "ETAPA";
                t.querySelectorAll('tr').forEach(r => {
                    const tds = r.querySelectorAll('td');
                    if(tds.length > 4) res.push({
                        etapa_nome: etapaH, equipamento: clean(tds[2].textContent), alimentador: clean(tds[3].textContent), 
                        executor: clean(tds[6].textContent), acao_bruta: clean(tds[1].textContent), texto_linha: clean(r.textContent).toLowerCase()
                    });
                });
            });
            return res;
        }""")
        # Validação Simplificada de Regras (Exemplo focado na Regra 22/30 de RT)
        manobra_map = {}
        for item in manobra_dados:
            eq = _norm_eqpto(item['equipamento'])
            if eq and eq != '-':
                if eq not in manobra_map: manobra_map[eq] = []
                manobra_map[eq].append(item)

        print("\n=== VALIDAÇÃO DE REGRAS (FOCO RT) ===")
        for eq, items in manobra_map.items():
            prefixo = eq.split('-')[0].strip().zfill(2) if '-' in eq else ""
            acoes = " ".join([it['texto_linha'] for it in items]).upper()
            
            # Lógica Consolidada RT (MA35/MA77 -> MA36)
            if prefixo == "02":
                teve_abertura = "MA35" in acoes or "MA77" in acoes
                teve_fechamento = "MA36" in acoes
                if teve_abertura and not teve_fechamento:
                    print(f"   ❌ REGRA 22: FALHA (RT '{eq}': MA35/MA77 exige inversão por MA36).")
                elif teve_fechamento and not teve_abertura:
                    print(f"   ❌ REGRA 30: FALHA (RT '{eq}': MA36 sem MA35/MA77 prévio).")
                elif teve_abertura and teve_fechamento:
                    print(f"   ✅ REGRA 22/30: OK (RT '{eq}': Inversão MA35/MA77 -> MA36 validada).")
            else:
                # Outros equipamentos (MA77 -> MA78)
                if "MA77" in acoes and "MA78" not in acoes:
                    print(f"   ❌ REGRA 22: FALHA (Equipamento '{eq}': MA77 exige inversão por MA78).")
                elif "MA78" in acoes and "MA77" not in acoes:
                    print(f"   ❌ REGRA 30: FALHA (Equipamento '{eq}': MA78 sem MA77 prévio).")

if __name__ == "__main__":
    main()
