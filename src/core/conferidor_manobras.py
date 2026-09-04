import os
import re
import getpass
import time
import json
from playwright.sync_api import sync_playwright

class Colors:
    """Códigos de cores ANSI para o terminal"""
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
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

URL_LOGIN = "http://gdis-pm/gdispm/"

# Motor de Validação das Regras Operacionais de Manobra (SD/ADMS CEMIG)

def _norm_eqpto(s):
    """Normaliza o número do equipamento para garantir que a comparação seja justa (ex: 24-123 vira 24 - 123)"""
    s = re.sub(r"\s+", " ", (s or "")).strip()
    s = re.sub(r"\s*-\s*", " - ", s)
    return s

def _compare_local(sol_local, manobra_local):
    """
    Compara o local/código do local entre Solicitação e Manobra.
    Retorna True se os códigos numéricos forem idênticos, se forem substrings ou se houver equivalência direta.
    Ignora valores nulos ou '-'.
    """
    if not sol_local or sol_local == '-' or not manobra_local or manobra_local == '-':
        return False
    s_clean = str(sol_local).strip()
    m_clean = str(manobra_local).strip()
    if s_clean == m_clean:
        return True
    if s_clean in m_clean or m_clean in s_clean:
        return True
    s_digits = re.findall(r'\b\d{3,6}\b', s_clean)
    m_digits = re.findall(r'\b\d{3,6}\b', m_clean)
    if s_digits and m_digits:
        return any(d in m_digits for d in s_digits)
    return False


INVALID_EQPTO_TERMS = {
    "RISCO SISTEMA",
    "RISCO PARA SISTEMA",
    "MANOBRA COM RISCO SISTEMA",
    "MANOBRA COM RISCO",
    "MANOBRA COM PIQUE",
    "MANOBRA",
    "PIQUE",
    "BLOQUEIO",
    "SEM INTERRUPCAO",
    "SEM INTERRUPÇÃO",
    "NENHUM",
    "NENHUMA",
    "CANCELADA",
    "OBSERVACAO",
    "OBSERVAÇÃO",
    "INFORMACAO",
    "INFORMAÇÃO",
    "LOCAL",
    "LOCAIS",
    "LOCAIS DE INTERRUPÇÃO",
    "LOCAIS DE INTERRUPCAO",
    "ALIMENTADOR",
    "SUBESTACAO",
    "SUBESTAÇÃO",
}


def _is_eqpto_valido(s):
    if not s or not isinstance(s, str):
        return False
    s_clean = s.strip()
    s_upper = s_clean.upper()
    if not s_upper or s_upper in ("-", " - ", "--", "N/A", "NONE", "NULL"):
        return False
    if s_upper in INVALID_EQPTO_TERMS:
        return False
    if s_upper.startswith("ETAPA") or "RISCO SISTEMA" in s_upper or "RISCO PARA SISTEMA" in s_upper or "MANOBRA COM RISCO" in s_upper:
        return False
    if re.fullmatch(r"\d{1,3}", s_upper):
        return False
    return True

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
    """Busca os dados do equipamento resolvendo conflitos pelo NUMERO-LOCAL ou Alimentador/Localidade"""
    
    # Normalização definida localmente para garantir escopo em qualquer contexto de execução
    def _norm(s):
        return re.sub(r"[^A-Z0-9]", "", str(s).upper()) if s else ""

    num_only = _get_eq_id(eq)
    lista = []
    
    # 1. TENTA POR NUMERO-LOCAL (Mais específico - chave exata com código de localidade)
    if local:
        local_fixed = str(local).strip()
        # Se for código numérico curto (ex: 1113), tenta o padrão '8'
        if local_fixed.isdigit() and len(local_fixed) <= 5 and not local_fixed.startswith('8'):
            local_fixed = '8' + local_fixed
        
        key_local = f"{num_only}-{local_fixed}"
        if key_local in dados:
            lista = dados[key_local]

    # 2. TENTA POR NÚMERO PURO (Ex: 107457)
    if not lista and num_only:
        lista = dados.get(num_only)

    # 3. TENTA POR NOME COMPLETO (Ex: 22 - 123456)
    if not lista:
        lista = dados.get(eq)
    
    # 4. TENTA POR NÚMERO SEM PREFIXO (Ex: 123456)
    if not lista and '-' in eq:
        sem_prefixo = eq.split('-', 1)[1].strip()
        lista = dados.get(sem_prefixo)
        
    if not lista: return {}
    
    # --- DESEMPATE UNIVERSAL ---
    if isinstance(lista, dict): lista = [lista] 
    if len(lista) == 1: 
        return lista[0]
    
    # Se chegamos aqui, há colisão de nomes. Vamos filtrar.
    
    # A. FILTRAR POR LOCALIDADE (String)
    if local and not str(local).isdigit():
        local_norm = _norm(local)
        candidatos_local = []
        for item in lista:
            # Tenta bater com localidade ou municipio
            if local_norm in _norm(item.get('localidade')) or local_norm in _norm(item.get('municipio')):
                candidatos_local.append(item)
        
        if len(candidatos_local) == 1:
            return candidatos_local[0]
        elif len(candidatos_local) > 1:
            lista = candidatos_local # Refina a busca para os que bateram o local

    # B. FILTRAR POR ALIMENTADOR
    a1 = _norm(alim1)
    a2 = _norm(alim2)
    
    if a1:
        for item in lista:
            alims_item = item.get('alimentadores') or [item.get('alimentador')]
            for alim_orig in alims_item:
                if _norm(alim_orig) == a1: return item
    if a2:
        for item in lista:
            alims_item = item.get('alimentadores') or [item.get('alimentador')]
            for alim_orig in alims_item:
                if _norm(alim_orig) == a2: return item
            
    # Último caso: Retorna o primeiro da lista de candidatos detectados
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

def _consultar_topologia_gdis(context, cod_alim: str, usuario: str = "", log_func=print) -> dict:
    """
    Consulta dinamicamente a topologia ao vivo do alimentador na API do GDIS (getRedeAlimentador).
    Retorna um dicionário indexado de equipamentos com estado POSOPE, fases, tipo e telecontrole.
    """
    if not cod_alim or cod_alim == '-':
        return {}

    cod_clean = str(cod_alim).strip().upper()
    if not callable(log_func):
        log_func = print

    url_rede = os.environ.get(
        "GDIS_REDE_URL",
        "http://gdis-apoio:80/gdis-do-web/services/getRedeAlimentador"
    )

    # 1. Captura o JSESSIONID e outros cookies da sessão ativa do Playwright
    jsessionid = None
    cookie_header_parts = []
    try:
        cookies = context.cookies()
        for cookie in cookies:
            c_name = cookie.get("name", "")
            c_val = cookie.get("value", "")
            c_domain = str(cookie.get("domain", "")).lower()
            cookie_header_parts.append(f"{c_name}={c_val}")
            if "JSESSIONID" in c_name.upper():
                if "apoio" in c_domain or not jsessionid:
                    jsessionid = c_val
    except Exception as e_cook:
        log_func(f"[GDIS Dinâmico] Aviso ao obter cookies da sessão: {e_cook}")

    candidatos = [cod_clean]
    m = re.match(r'^([A-Z]{3,4})[\s\-_/]*(\d{1,4})$', cod_clean)
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
            f"{subes}-{num_int:02d}",
            f"{subes} {num_int:03d}",
            f"{subes}{num_int:03d}",
            f"{subes} {num_int}",
            f"{subes}{num_int}"
        ])
    elif ' ' in cod_clean:
        candidatos.append(cod_clean.replace(' ', ''))

    # Deduplica preservando ordem
    vistos = set()
    candidatos = [c for c in candidatos if not (c in vistos or vistos.add(c))]

    dados_json = None
    for cand in candidatos:
        payload = {
            "alim": cand,
            "ambiente": "operacao",
            "userName": usuario or "",
            "salt": str(int(time.time() * 1000))
        }
        params = {}
        if jsessionid:
            params["sessionId"] = jsessionid

        headers = {
            "User-Agent": "Jakarta Commons-HttpClient/3.1"
        }

        log_func(f"[GDIS Dinâmico] Consultando topologia ao vivo para o alimentador '{cand}'...")

        # Tentativa 1: Via context.request do Playwright (compartilha contexto de rede e cookies do browser)
        try:
            resp = context.request.post(
                url_rede,
                params=params,
                headers=headers,
                form=payload,
                timeout=30000
            )
            if resp.status == 200:
                txt_resp = resp.text()
                if "cookiecheck" not in txt_resp:
                    try:
                        cand_json = resp.json()
                        if isinstance(cand_json, dict) and cand_json.get("nos"):
                            dados_json = cand_json
                            cod_clean = cand
                            break
                    except Exception:
                        pass
                else:
                    log_func(f"[GDIS Dinâmico] Servidor Apoio solicitou cookiecheck para '{cand}'.")
            elif resp.status == 204:
                log_func(f"[GDIS Dinâmico] Alimentador '{cand}' sem rede cadastrada no GDIS Apoio (HTTP 204).")
            else:
                log_func(f"[GDIS Dinâmico] HTTP {resp.status} retornado para '{cand}'.")
        except Exception as e_pw:
            log_func(f"[GDIS Dinâmico] Tentando fallback HTTP direto para '{cand}': {e_pw}")

        # Tentativa 2: Fallback via urllib caso Playwright request não tenha retornado dados
        if not dados_json and jsessionid:
            try:
                import urllib.request, urllib.parse
                url_full = url_rede + "?" + urllib.parse.urlencode(params)
                encoded_body = urllib.parse.urlencode(payload).encode("utf-8")
                h_urllib = {
                    "User-Agent": "Jakarta Commons-HttpClient/3.1",
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Cookie": "; ".join(cookie_header_parts)
                }
                req = urllib.request.Request(url_full, data=encoded_body, headers=h_urllib, method="POST")
                with urllib.request.urlopen(req, timeout=30) as r:
                    if r.status == 200:
                        raw_text = r.read().decode("utf-8", errors="replace")
                        if "cookiecheck" not in raw_text:
                            cand_json = json.loads(raw_text)
                            if isinstance(cand_json, dict) and cand_json.get("nos"):
                                dados_json = cand_json
                                cod_clean = cand
                                break
                        else:
                            log_func(f"[GDIS Dinâmico] Servidor Apoio requer autenticação em gdis-apoio.")
            except Exception as e_url:
                log_func(f"[GDIS Dinâmico] Fallback HTTP: {e_url}")

        if dados_json and isinstance(dados_json, dict) and dados_json.get("nos"):
            break

    if not dados_json or not isinstance(dados_json, dict) or "nos" not in dados_json:
        return {}

    nos = dados_json.get("nos", [])
    equipamentos = {}

    for no in nos:
        if not isinstance(no, dict):
            continue
        numeq = str(no.get("numeq", "")).strip()
        if not numeq or numeq == "-":
            continue

        base_posope = str(
            no.get("POSOPE") or no.get("posope") or no.get("r_posope") or 
            no.get("estado") or no.get("r_estado") or no.get("pos_ope") or 
            no.get("posOpe") or no.get("situacao") or no.get("posicao") or ""
        ).strip().upper()

        if base_posope in ["A", "ABERTO", "ABERTA", "DESLIGADO", "NA", "N.A.", "NORMALMENTE ABERTO", "NORMALMENTE ABERTA", "NORMAL ABERTO", "NORMAL ABERTA", "AB", "0"]:
            posope = "A"
        elif base_posope in ["F", "FECHADO", "FECHADA", "LIGADO", "NF", "N.F.", "NORMALMENTE FECHADO", "NORMALMENTE FECHADA", "NORMAL FECHADO", "NORMAL FECHADA", "FC", "1"]:
            posope = "F"
        else:
            posope = ""

        tipo = str(no.get("r_tipoeq", no.get("tipono", ""))).strip()
        fases = str(no.get("r_fases", no.get("fases", ""))).strip().upper()
        controle = str(no.get("r_controle", "")).strip().lower()
        telecom = str(no.get("telecom", "")).strip().upper()

        if telecom == "S" or any(w in controle for w in ["telecontrolado", "remoto", "automacao", "automatico"]):
            telecontrolado = True
        elif "manual" in controle or fases in ["A", "B", "C"]:
            telecontrolado = False
        else:
            telecontrolado = None

        refalm = str(no.get("refalm", cod_clean)).strip().upper()
        refalm_2 = str(no.get("refalm_2", no.get("refalm2", ""))).strip().upper()
        alims = [a for a in [refalm, refalm_2] if a]

        rec = {
            "numero": numeq,
            "tipo": tipo,
            "telecontrolado": telecontrolado,
            "posope": posope,
            "fases": fases,
            "alimentadores": alims,
            "localidade": str(no.get("logradouro", no.get("endereco_livre", ""))).strip(),
            "municipio": str(no.get("municipio", "")).strip(),
            "tensao": str(no.get("tensao", no.get("kv", ""))).strip(),
            "origem": "GDIS_AO_VIVO"
        }

        # Indexa pelo número puro (ex: '359323')
        numeq_clean = _get_eq_id(numeq) or numeq
        if numeq not in equipamentos:
            equipamentos[numeq] = []
        equipamentos[numeq].append(rec)
        if numeq_clean != numeq:
            if numeq_clean not in equipamentos:
                equipamentos[numeq_clean] = []
            equipamentos[numeq_clean].append(rec)

        # Indexa também com prefixo inferido para busca rápida
        prefixo = _obter_prefixo_equipamento(numeq, rec)
        if prefixo and numeq_clean:
            k_pref = f"{prefixo} - {numeq_clean}"
            if k_pref not in equipamentos:
                equipamentos[k_pref] = []
            equipamentos[k_pref].append(rec)

    log_func(f"[GDIS Dinâmico] Sucesso: {len(nos)} nós recebidos ({len(equipamentos)} equipamentos indexados) para '{cod_clean}'.")
    return equipamentos


def _obter_prefixo_equipamento(eq, eq_data=None):
    """
    Retorna o prefixo/família do equipamento (ex: '01' para Trafo, '22' para Religador, '28' para Seccionadora).
    Dá prioridade aos dados do cadastro/topologia (eq_data) e usa fallback pelo formato da string.
    """
    if eq_data:
        p_data = eq_data.get('prefixo') or eq_data.get('tipo') or eq_data.get('familia')
        if p_data:
            p_str = str(p_data).strip()
            if p_str.isdigit():
                return p_str.zfill(2)
            p_upper = p_str.upper()
            if 'RELIGADOR' in p_upper: return '22'
            if 'DISJUNTOR' in p_upper: return '21'
            if 'SECCIONATOR' in p_upper or 'SECCIONALIZADOR' in p_upper: return '23'
            if 'REGULADOR' in p_upper: return '02'
            if 'FUSIVEL' in p_upper or 'FUSÍVEL' in p_upper: return '04'
            if 'FACA ADAPTADA' in p_upper or 'CHAVE FACA ADAPTADA' in p_upper: return '36'
            if 'FACA UNIPOLAR' in p_upper: return '28'
            if 'FACA' in p_upper: return '36'
            if 'SECCIONADORA' in p_upper: return '28'
            if 'TRANSFORMADOR' in p_upper or 'TRAFO' in p_upper: return '01'

    # Fallback por formato de string (ex: "22 - 12345" ou Regex de Trafo)
    if re.match(r"^\d{5,7}\s*-\s*\d+\s*-\s*\d+$", str(eq)):
        return "01"
    if '-' in str(eq):
        part = str(eq).split('-')[0].strip()
        if part.isdigit():
            return part.zfill(2)
    return ""


def _verificar_telecontrole(eq_nome, eq_data=None, manobra_items=None, sol_info=None):
    """
    Verifica se o equipamento é telecontrolado.
    1. Se o equipamento for monofásico (fases A, B ou C), NÃO possui telecontrole na distribuição.
    2. Se os dados da topologia/solicitação/manobra indicarem explicitamente o estado de telecontrole (True/False), utiliza.
    3. Se houver qualquer indicação textual de ser manual / sem telecontrole / chave faca, retorna False.
    4. Se houver indicação textual de telecontrole / modo remoto, retorna True.
    5. Se houver operação sendo realizada pelo COD ou macros telecontroladas (MA01/MA02 pelo COD, MA64, MA14, MA15, etc.), assume telecontrolado = True.
    6. Por tipo/prefixo do equipamento:
       - Prefixos '02', '19', '20', '21', '22', '23' trifásicos: Religadores de linha/SE e disjuntores são telecontrolados por padrão.
       - Prefixo '28', '36', '37' (Chaves manuais): Retorna False por padrão.
    """
    eq_clean = str(eq_nome or '').strip()
    prefixo = eq_clean.split('-')[0].strip() if '-' in eq_clean else ''

    # Se o equipamento é monofásico, não é telecontrolado na rede de distribuição
    fases = _obter_fases_equipamento(eq_nome, eq_data, manobra_items, sol_info)
    if fases in ['A', 'B', 'C']:
        return False

    if eq_data and isinstance(eq_data, dict):
        if eq_data.get('telecontrolado') is not None:
            return bool(eq_data.get('telecontrolado'))
        desc = (str(eq_data.get('tipo', '')) + ' ' + str(eq_data.get('descricao', '')) + ' ' + str(eq_data.get('comentario', ''))).upper()
        if any(w in desc for w in ['MANUAL', 'SEM TELECONTROLE', 'NAO TELECONTROLADO', 'NÃO TELECONTROLADO', 'SEM MODULO', 'SEM MÓDULO', 'CHAVE FACA']):
            return False
        if any(w in desc for w in ['TELECONTROLADO', 'TELECONTROLADA', 'MODO REMOTO', 'AUTOMAÇÃO', 'AUTOMÁTICO', 'AUTOMATICO']):
            return True

    if sol_info and isinstance(sol_info, dict):
        if sol_info.get('telecontrolado') is not None:
            return bool(sol_info.get('telecontrolado'))
        txt_sol = (str(sol_info.get('eq', '')) + ' ' + str(sol_info.get('local', '')) + ' ' + str(sol_info.get('observacao', ''))).upper()
        if any(w in txt_sol for w in ['MANUAL', 'SEM TELECONTROLE', 'NAO TELECONTROLADO', 'NÃO TELECONTROLADO', 'SEM MODULO', 'SEM MÓDULO', 'CHAVE FACA']):
            return False
        if any(w in txt_sol for w in ['TELECONTROLADO', 'TELECONTROLADA', 'MODO REMOTO', 'AUTOMAÇÃO', 'AUTOMÁTICO', 'AUTOMATICO']):
            return True

    items = []
    if isinstance(manobra_items, list):
        items = manobra_items
    elif isinstance(manobra_items, dict):
        items = [manobra_items]

    tem_operacao_cod = False
    tem_macro_telecontrole = False

    for mi in items:
        if isinstance(mi, dict):
            if mi.get('telecontrolado') is not None:
                return bool(mi.get('telecontrolado'))
            txt_mi = (str(mi.get('texto_linha', '')) + ' ' + str(mi.get('observacao', '')) + ' ' + str(mi.get('etapa_nome', ''))).upper()
            if any(w in txt_mi for w in ['MANUAL', 'SEM TELECONTROLE', 'NAO TELECONTROLADO', 'NÃO TELECONTROLADO', 'SEM MODULO', 'SEM MÓDULO', 'CHAVE FACA']):
                return False
            if any(w in txt_mi for w in ['TELECONTROLADO', 'TELECONTROLADA', 'MODO REMOTO', 'AUTOMAÇÃO', 'AUTOMÁTICO', 'AUTOMATICO']):
                return True
            
            execut = mi.get('executor', '').upper()
            if re.search(r'\bCOD\b', execut):
                tem_operacao_cod = True
            
            if re.search(r'\b\d*(MA64|MA65|MA14|MA15|MA16|MA17|MA52)\b', txt_mi):
                tem_macro_telecontrole = True

    # Se há operação remota executada pelo COD ou macros explícitas de telecontrole, é telecontrolado
    if tem_operacao_cod or tem_macro_telecontrole:
        return True

    # Classificação padrão por prefixo do equipamento
    # Subestação (21, 23), Reguladores (02), Religadores de Linha Trifásicos (19, 20, 22): Telecontrolados por padrão
    if prefixo in ["02", "19", "20", "21", "22", "23"]:
        return True

    return False


def _obter_limite_pre_desligamento(manobra_dados):
    """
    Retorna a cronologia máxima das etapas pré-desligamento / pré-trabalho (fase de alívio, preparação e desligamento).
    Considera:
    1. Etapas de DESLIGAMENTO, CORTE, ISOLAMENTO e AUTORIZAÇÃO DO PLE/BI.
    2. Etapas de DISPENSA DO PLE/BI, NORMALIZAR, RELIGAMENTO, RECOMPOSIÇÃO (marcam o início da restauração/recomposição pós-obra).
    Garante que a etapa de desligamento nunca seja descartada prematuramente por menções internas a bloqueios ou prazos.
    Retorna -1 caso não haja etapas de corte/desligamento nem autorização de PLE/BI.
    """
    limite_desligamento = -1
    cron_primeiro_retorno = float('inf')

    for mi in manobra_dados:
        if not isinstance(mi, dict): continue
        nome_etapa = (
            str(mi.get('etapa_nome', '')) + ' ' + 
            str(mi.get('etapa_texto_header', '')) + ' ' + 
            str(mi.get('grupo_id', ''))
        ).upper()
        
        cron = mi.get('cronologia', 0)
        
        eh_deslig = any(w in nome_etapa for w in ["DESLIGAMENTO", "CORTE", "ISOLAMENTO"]) and "RELIGAMENTO" not in nome_etapa
        eh_aut = any(w in nome_etapa for w in ["AUTORIZACAO", "AUTORIZAÇÃO"]) and "DISPENSA" not in nome_etapa

        if eh_deslig or eh_aut:
            limite_desligamento = max(limite_desligamento, cron)
            
        termos_retorno = ["RELIGAMENTO", "DISPENSA DO PLE", "DISPENSA DO BI", "DISPENSA DE PLE", "RECOMPOSICAO", "RECOMPOSIÇÃO", "RESTABELECIMENTO"]
        tem_retorno = any(w in nome_etapa for w in termos_retorno) or ("NORMALIZAR" in nome_etapa and not eh_deslig)
        if tem_retorno:
            if cron > 0:
                cron_primeiro_retorno = min(cron_primeiro_retorno, cron)

    if limite_desligamento != -1:
        return limite_desligamento
    elif cron_primeiro_retorno != float('inf'):
        return cron_primeiro_retorno - 1
    return -1


def _item_pertence_fase_desligamento(mi, limite_cronologia_desligamento):
    """
    Verifica se o item da manobra pertence à fase de preparação/desligamento (inclusive toda a etapa de desligamento).
    Garante que ações de abertura e delimitação executadas na etapa de desligamento sejam contabilizadas na Regra 02.
    """
    nome_et = (
        str(mi.get('etapa_nome', '')) + ' ' + 
        str(mi.get('etapa_texto_header', '')) + ' ' + 
        str(mi.get('grupo_id', ''))
    ).upper()
    
    # Etapas explícitas de recomposição pós-obra não pertencem à fase de desligamento
    if any(w in nome_et for w in ["RELIGAMENTO", "RECOMPOSICAO", "RECOMPOSIÇÃO", "RESTABELECIMENTO"]):
        return False
    if any(w in nome_et for w in ["DISPENSA DO PLE", "DISPENSA DO BI", "DISPENSA DE PLE"]):
        return False
    if "NORMALIZAR" in nome_et and not any(w in nome_et for w in ["DESLIGAMENTO", "CORTE", "ISOLAMENTO"]):
        return False

    # Etapas explícitas de desligamento, isolamento, corte ou autorização pertencem sempre à fase
    if any(w in nome_et for w in ["DESLIGAMENTO", "CORTE", "ISOLAMENTO", "AUTORIZACAO", "AUTORIZAÇÃO"]):
        return True

    # Demais itens anteriores ao retorno pós-obra
    cron = mi.get('cronologia', 0)
    if limite_cronologia_desligamento == -1 or cron <= limite_cronologia_desligamento:
        return True

    return False


def _obter_fases_equipamento(eq_nome, eq_data=None, mi=None, sol_info=None):
    """
    Identifica o número de fases do equipamento ('ABC', 'A', 'B', 'C').
    Prioriza topologia/cadastro, dados da solicitação e inspeção ampla de texto dos itens da manobra.
    """
    if eq_data and isinstance(eq_data, dict):
        if eq_data.get('fases'):
            f = str(eq_data.get('fases')).strip().upper()
            if f in ['A', 'B', 'C', 'ABC']: return f
            if any(k in f for k in ['MONO', '1', 'UNIP']): return 'A'
        desc = (str(eq_data.get('tipo', '')) + ' ' + str(eq_data.get('descricao', '')) + ' ' + str(eq_data.get('nome', '')) + ' ' + str(eq_data.get('comentario', ''))).upper()
        if any(w in desc for w in ['MONOFASICO', 'MONOFÁSICO', 'MONOFASICA', 'MONOFÁSICA', 'UNIPOLAR']):
            return 'A'

    if sol_info and isinstance(sol_info, dict):
        if sol_info.get('fases'):
            f = str(sol_info.get('fases')).strip().upper()
            if f in ['A', 'B', 'C', 'ABC']: return f
            if any(k in f for k in ['MONO', '1', 'UNIP']): return 'A'
        txt_sol = (str(sol_info.get('eq', '')) + ' ' + str(sol_info.get('local', '')) + ' ' + str(sol_info.get('observacao', ''))).upper()
        if any(w in txt_sol for w in ['MONOFASICO', 'MONOFÁSICO', 'MONOFASICA', 'MONOFÁSICA', 'UNIPOLAR']):
            return 'A'

    items_to_check = []
    if isinstance(mi, list):
        items_to_check = mi
    elif isinstance(mi, dict):
        items_to_check = [mi]

    for item in items_to_check:
        if not isinstance(item, dict): continue
        if item.get('fases'):
            f = str(item.get('fases')).strip().upper()
            if f in ['A', 'B', 'C', 'ABC']: return f
            if any(k in f for k in ['MONO', '1', 'UNIP']): return 'A'
        
        txt_full = (
            str(item.get('texto_linha', '')) + ' ' + 
            str(item.get('observacao', '')) + ' ' + 
            str(item.get('acao_bruta', '')) + ' ' + 
            str(item.get('equipamento', '')) + ' ' +
            str(item.get('etapa_nome', '')) + ' ' +
            str(item.get('etapa_texto_header', '')) + ' ' +
            str(item.get('local', '')) + ' ' +
            str(item.get('posicionamento', ''))
        ).upper()

        if re.search(r'\bFASE\s*[-_]?\s*B\b|\bFASEB\b', txt_full) and not re.search(r'\bSUBSTATION\b', txt_full):
            return 'B'
        if re.search(r'\bFASE\s*[-_]?\s*C\b|\bFASEC\b', txt_full) and not re.search(r'\bSUBSTATION\b', txt_full):
            return 'C'

        if re.search(r'\bFASE\s*[-_]?\s*A\b|\bFASEA\b|\bMONOF[ÁA]SIC[AO]\b|\bUNIPOLAR\b|\b1\s*FASE\b', txt_full):
            return 'A'

    eq_upper = str(eq_nome or '').upper()
    if re.search(r'\bFASE\s*[-_]?\s*B\b|\bFASEB\b', eq_upper): return 'B'
    if re.search(r'\bFASE\s*[-_]?\s*C\b|\bFASEC\b', eq_upper): return 'C'
    if re.search(r'\bFASE\s*[-_]?\s*A\b|\bFASEA\b|\bMONOF[ÁA]SIC[AO]\b|\bUNIPOLAR\b', eq_upper): return 'A'

    return 'ABC'

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
    print("      VERIFICADOR DE MANOBRAS (Regras do Conferidor 1 a 44)        ")
    print("=====================================================")
    
    if isinstance(manobra_param, list):
        manobras_lista = [str(m).strip() for m in manobra_param if str(m).strip()]
    elif manobra_param:
        manobras_lista = list(dict.fromkeys(re.findall(r'\b\d{6,10}\b', str(manobra_param))))
    else:
        inp = input("Digite o(s) número(s) da(s) Manobra(s): ").strip()
        manobras_lista = list(dict.fromkeys(re.findall(r'\b\d{6,10}\b', inp)))

    if not manobras_lista:
        print("[ERRO] Nenhum número de manobra válido informado.")
        return

    usuario = usuario_param if usuario_param else ((os.getenv("GDIS_USUARIO") or "").strip() or input("Usuário: ").strip())
    senha = senha_param if senha_param else ((os.getenv("GDIS_SENHA") or "").strip() or getpass.getpass("Senha: "))

    # Modo 100% dinâmico via GDIS (sem dependência de bases estáticas CSV)
    dados_equipamentos = dados_equipamentos_cache if isinstance(dados_equipamentos_cache, dict) else {}
    print("[OK] Modo de conferência 100% dinâmica GDIS ativo (sem bases CSV estáticas).")
    
    parametros_conferidor = _obter_parametros_conferidor()

    print("\n[1] Iniciando navegador...")
    
    with sync_playwright() as p:
        browser_args = [
            "--disable-dev-shm-usage", 
            "--no-sandbox", 
            "--disable-gpu", 
            "--disable-software-rasterizer",
            "--mute-audio", 
            "--disable-extensions", 
            "--disable-setuid-sandbox"
        ]
        try:
            browser = p.chromium.launch(channel="msedge", headless=headless, args=browser_args)
        except Exception:
            browser = p.chromium.launch(headless=headless, args=browser_args)
        
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

            # Autenticação em segundo plano no GDIS Apoio para habilitar a API getRedeAlimentador
            try:
                page_apoio = context.new_page()
                page_apoio.goto("http://gdis-apoio/gdisweb/login.jsf", timeout=12000)
                if page_apoio.locator("input[id='form_login:login_username']").count() > 0:
                    page_apoio.fill("input[id='form_login:login_username']", usuario)
                    page_apoio.fill("input[id='form_login:login_pwd']", senha)
                    page_apoio.click("input[id='form_login:login_ok']")
                    try:
                        page_apoio.wait_for_load_state("domcontentloaded", timeout=8000)
                    except Exception:
                        pass
                page_apoio.close()
            except Exception as e_apoio:
                print(f"    [AVISO] Integração GDIS Apoio: {e_apoio}")
        except Exception:
            try: page.close()
            except Exception: pass
            try: context.close()
            except Exception: pass
            try: browser.close()
            except Exception: pass
            raise

        total_manobras = len(manobras_lista)
        for idx_m, manobra_num in enumerate(manobras_lista, start=1):
            print("\n" + "="*80)
            print(f">>> MANOBRA_START: {manobra_num} ({idx_m}/{total_manobras})")
            print("="*80)
            try:
                # Garante que o navegador esteja na página inicial limpa do GDIS para evitar conflitos de DOM entre manobras
                try:
                    page.goto(URL_LOGIN)
                    page.wait_for_selector("text=Consultas", timeout=15000)
                except Exception as e_nav:
                    print(f"    [AVISO] Falha ao resetar navegação para a página inicial: {e_nav}")

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
                
                # Aguarda especificamente até que a tabela traga o link contendo o número da manobra pesquisada
                try:
                    page.wait_for_selector(f"table[id*='resulPesManobra'] a:has-text('{manobra_num}')", timeout=15000)
                except Exception:
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
                    raise RuntimeError(f"Não foi possível encontrar o número da Solicitação vinculada à manobra {manobra_num}.")

                # Abre o detalhe da manobra
                print(f"    Abrindo detalhes da Manobra {manobra_num}...")
                link_clicked = page.evaluate(f"""(num) => {{
                    const links = Array.from(document.querySelectorAll("table[id*='resulPesManobra'] a"));
                    const link = links.find(l => (l.innerText || '').includes(String(num)));
                    if (link) {{
                        link.click();
                        return true;
                    }}
                    return false;
                }}""", manobra_num)

                if not link_clicked:
                    raise RuntimeError(f"Link para a manobra {manobra_num} não foi encontrado na tabela de resultados da pesquisa.")

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
                        let idxPosic = headers.findIndex(h => h.includes('posicionamento') || h.includes('posic') || h.includes('pos. manobrar') || h.includes('pos.manobrar') || h.includes('pos. manobra') || h.includes('pos.'));
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
                for idx, mi in enumerate(manobra_dados, start=1):
                    if 'cronologia' not in mi or not mi['cronologia']:
                        mi['cronologia'] = idx
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

                # Extrai os equipamentos listados em Locais de Interrupção (com suporte a paginação de até 10 páginas)
                solicitacao_locais = []
                for pag in range(1, 11):
                    novos_eqs = page.evaluate("""() => {
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

                    if novos_eqs:
                        for ne in novos_eqs:
                            if _is_eqpto_valido(ne.get('numero')):
                                if not any(e['numero'] == ne['numero'] and e.get('alimentador') == ne.get('alimentador') and e.get('local') == ne.get('local') for e in solicitacao_locais):
                                    solicitacao_locais.append(ne)

                    # Tenta ir para a próxima página no datascroller do RichFaces (limite estrito de 10 páginas)
                    target_page = pag + 1
                    avancou = page.evaluate("""(targetPage) => {
                        const norm = (s) => (s || '').normalize('NFD').replace(/[\\u0300-\\u036f]/g, '').toLowerCase().replace(/\\s+/g, ' ').trim();
                
                        // 1. Tentar encontrar a seção/painel específica de 'Locais de Interrupção'
                        let container = document;
                        const headers = Array.from(document.querySelectorAll('.rich-stglpanel-header, .rich-panel-header, div, th, td'));
                        const headerLocais = headers.find(h => norm(h.textContent).includes('locais de interrupcao'));
                
                        if (headerLocais) {
                            const parentPanel = headerLocais.closest('.rich-stglpanel, .rich-panel, form');
                            if (parentPanel) container = parentPanel;
                        }

                        // 2. Tenta clicar diretamente na célula com o número da próxima página (ex: "2", "3")
                        const pageCells = Array.from(container.querySelectorAll('.rich-datascr-inact, [class*="datascr"] td'));
                        for (const cell of pageCells) {
                            const txt = (cell.textContent || cell.innerText || '').trim();
                            if (txt === String(targetPage)) {
                                cell.click();
                                return true;
                            }
                        }

                        // 3. Coletar botões do datascroller para encontrar o botão 'Próxima' (>)
                        const candidates = Array.from(container.querySelectorAll('.rich-datascr-button-next, .rich-datascr-button, [class*="datascr-button"], [id*="ds_next"]'));
                
                        for (const btn of candidates) {
                            const txt = (btn.textContent || btn.innerText || '').trim();
                            const cls = (btn.className || '');
                    
                            // Somente desabilitado se tiver dsbl/dsbld/disabled (NÃO inact, pois inact indica página clicável!)
                            const isDisabled = cls.includes('dsbl') || cls.includes('dsbld') || btn.hasAttribute('disabled') || btn.getAttribute('aria-disabled') === 'true';
                            if (isDisabled) continue;
                    
                            const isNextClass = cls.includes('next');
                            const isNextSymbol = ['>', '»', '›', '&gt;'].includes(txt) || txt.includes('>') || txt.includes('»');
                    
                            if (isNextClass || isNextSymbol) {
                                btn.click();
                                return true;
                            }
                        }

                        // 4. Fallback global no document inteiro
                        if (container !== document) {
                            const globalCells = Array.from(document.querySelectorAll('.rich-datascr-inact'));
                            for (const cell of globalCells) {
                                if ((cell.textContent || '').trim() === String(targetPage)) {
                                    cell.click();
                                    return true;
                                }
                            }

                            const globalCandidates = Array.from(document.querySelectorAll('.rich-datascr-button-next, [class*="datascr-button"], [id*="ds_next"]'));
                            for (const btn of globalCandidates) {
                                const txt = (btn.textContent || btn.innerText || '').trim();
                                const cls = (btn.className || '');
                                const isDisabled = cls.includes('dsbl') || cls.includes('dsbld') || btn.hasAttribute('disabled');
                                if (isDisabled) continue;
                                if (cls.includes('next') || ['>', '»', '›'].includes(txt) || txt.includes('>') || txt.includes('»')) {
                                    btn.click();
                                    return true;
                                }
                            }
                        }

                        return false;
                    }""", target_page)

                    if not avancou:
                        break
            
                    # Aguarda o modal de carregamento (statusModal ou modalPanel) desaparecer completamente
                    page.wait_for_timeout(300)
                    try:
                        page.wait_for_function("""() => {
                            const modal = document.getElementById('statusModal') || document.getElementById('statusPanel') || document.querySelector('.rich-modalpanel');
                            if (!modal) return true;
                            const s = window.getComputedStyle(modal);
                            return !s || s.display === 'none' || s.visibility === 'hidden';
                        }""", timeout=15000)
                    except Exception:
                        pass
                    page.wait_for_timeout(800)

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

                # ============================================================
                # ETAPA C: SINCRONIZAÇÃO DINÂMICA VIA GDIS (getRedeAlimentador)
                # ============================================================
                alims_envolvidos = set()
                regex_alim_patt = re.compile(r'\b([A-Z]{3,4}\s*[-/]?\s*\d{1,4})\b', re.IGNORECASE)

                def _registrar_alims(val):
                    if not val: return
                    s_val = str(val).strip().upper()
                    if len(s_val) < 3 or s_val.startswith('SEM'): return
                    encontrados = regex_alim_patt.findall(s_val)
                    for ea in encontrados:
                        m_n = re.match(r'^([A-Z]{3,4})\s*[-/]?\s*(\d{1,4})$', ea.strip())
                        if m_n:
                            alims_envolvidos.add(f"{m_n.group(1)} {m_n.group(2)}")
                        else:
                            alims_envolvidos.add(re.sub(r'\s+', ' ', ea).strip())

                for md in manobra_dados:
                    for c_nome in ['alimentador', 'alim', 'texto_linha', 'observacao', 'etapa_nome', 'etapa_texto_header']:
                        _registrar_alims(md.get(c_nome, ''))

                for sl in solicitacao_locais:
                    _registrar_alims(sl.get('alimentador', ''))

                for eh in manobra_etapas_headers:
                    _registrar_alims(eh.get('texto', ''))

                if alims_envolvidos:
                    print(f"\n[GDIS Dinâmico] Identificado(s) {len(alims_envolvidos)} alimentador(es) na Manobra: {', '.join(sorted(alims_envolvidos))}")
                    for cod_alim in sorted(alims_envolvidos):
                        dados_dinamicos = _consultar_topologia_gdis(context, cod_alim, usuario, log_func=print)
                        if dados_dinamicos:
                            for k, lista_recs in dados_dinamicos.items():
                                dados_equipamentos[k] = lista_recs

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
                for idx, item in enumerate(manobra_dados, start=1):
                    if 'cronologia' not in item or not item['cronologia']:
                        item['cronologia'] = idx
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
                        'grupo_id': item.get('grupo_id', 'Bloco_Desconhecido'),
                        'cronologia': item.get('cronologia', idx)
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
                    for f in falhas_r21: print_regra(21, "ERRO", f"Texto genérico 'AAA' pendente de preenchimento na linha de {f}.")
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
                            duplicatas_r28.append(f"Etapa '{etapa_nome}': A macro {m.upper()} foi duplicada para o equipamento '{alvo}'.")
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
                        alertas_r24.append("Informado 'EQUIPE:' no singular. O padrão correto no cabeçalho é 'EQUIPES:'")

                    # 2. Verificação de existência e Quantidade
                    num_equipes_header = 0
                    for sigla, _ in siglas_validar.items():
                        # Procura a sigla no texto
                        m_sigla = re.search(r'\b' + sigla + r'\b\s*:\s*(\d+)', texto_primeira)
                        if re.search(r'\b' + sigla + r'\b', texto_primeira):
                            # Se achou a sigla, verifica se tem o formato "SIGLA: numero"
                            if m_sigla:
                                if sigla == "EQUIPES":
                                    num_equipes_header = int(m_sigla.group(1))
                            else:
                                falhas_r24.append(f"Código '{sigla}' informado no cabeçalho sem a quantidade (exemplo exigido: '{sigla}:1')")
                        else:
                            if sigla in ["CI"]:
                                falhas_r24.append(f"Código obrigatório '{sigla}' não informado no cabeçalho da primeira etapa")

                    if falhas_r24:
                        for f in falhas_r24: print_regra(24, "ERRO", f"Primeira Etapa: {f}")
                    if alertas_r24:
                        for a in alertas_r24: print_regra(24, "ALERTA", f"Primeira Etapa: {a}")
                    if not falhas_r24 and not alertas_r24:
                        print_regra(24, "OK", "Siglas e quantidades (CI) do cabeçalho validadas com sucesso.")

                # REGRA 40 (Aviso de Risco Sistema - Bidirecional)
                cabecalho_tem_risco = False
                if manobra_etapas_headers:
                    cabecalho_tem_risco = "RISCO SISTEMA" in txt_headers.upper() or "RISCO PARA SISTEMA" in txt_headers.upper()

                etapas_risco_alvo = ["MANOBRA COM RISCO SISTEMA", "MANOBRA C/ PIQUE RISCO SISTEMA"]
                etapa_tem_risco = any(et_r in manobra_texto_etapas for et_r in etapas_risco_alvo)

                if cabecalho_tem_risco and etapa_tem_risco:
                    print_regra(40, "OK", "Aviso de Risco para o Sistema no cabeçalho e etapa correspondente validados.")
                elif cabecalho_tem_risco and not etapa_tem_risco:
                    print_regra(40, "ERRO", "Cabeçalho indica Risco para o Sistema, mas a etapa 'MANOBRA COM RISCO SISTEMA' não foi criada.")
                elif not cabecalho_tem_risco and etapa_tem_risco:
                    print_regra(40, "ERRO", "Manobra possui etapa de Risco para o Sistema, mas a marcação 'RISCO SISTEMA' está ausente no cabeçalho.")

                # REGRA 25 (Horários Repetidos nas Etapas)
                if len(manobra_etapas_headers) >= 3:
                    datas_etapas = [eh['data_hora'] for eh in manobra_etapas_headers if eh.get('data_hora')]
                    if len(datas_etapas) >= 2 and len(set(datas_etapas)) == 1:
                        print_regra(25, "ALERTA", f"Todas as etapas apresentam o mesmo horário ('{datas_etapas[0]}'). Verifique o cronograma.")
                    else:
                        print_regra(25, "OK", "Variação temporal entre as etapas validada com sucesso.")

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
                    print_regra(20, "ERRO", f"Equipamento com {', '.join(sorted(falhas_r20))}: Exige informar se é Lâmina ou Fusível (com valor do elo) na observação.")
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
                    print_regra(26, "ALERTA", "Solicitação: Falha na leitura dos horários autorizados. Verifique manualmente o cronograma.")

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
                        falhas_r26.append(f"Início antecipado ({ini_man_real.strftime('%H:%M')}) vs Autorizado ({lim_ini.strftime('%H:%M')})")
        
                    # Valida término
                    if lim_fim and fim_man > lim_fim:
                        falhas_r26.append(f"Término tardio ({fim_man.strftime('%H:%M')}) vs Autorizado ({lim_fim.strftime('%H:%M')})")
            
                    if falhas_r26:
                        msg_f = " e ".join(falhas_r26)
                        tipo_msg = "ERRO" if not is_apoio else "ALERTA"
                        print_regra(26, tipo_msg, f"Equipamento '{eq}': Divergência no cronograma ({msg_f}). Ajuste o horário da etapa.")
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
                        print_regra(5, "OK", "Bloqueio de RA: Macros de bloqueio (MA52/MA14/MA28) confirmadas conforme exigido na solicitação.")
                    else:
                        print_regra(5, "ERRO", "Manobra: Solicitação exige bloqueio de Religamento Automático (RA), mas as macros de bloqueio (MA52, MA14 ou MA28) não foram inseridas.")
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
                        print_regra(5, "ERRO", f"Manobra: Solicitação NÃO exige bloqueio de RA, porém foram inseridas macros de bloqueio indevidas ({str_macros}). Remova as macros de bloqueio.")
                    else:
                        print_regra(5, "OK", "Bloqueio de RA: Ausência de bloqueio validada com sucesso conforme a solicitação.")

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
                        print_regra(23, "OK", f"Primeira Etapa: Declaração de gerador/UGTM no cabeçalho confirmada ({motivo_gerador}).")
                    else:
                        print_regra(23, "ALERTA", f"Primeira Etapa: {motivo_gerador} identificado, mas o cabeçalho não contém a indicação 'GMT:' ou 'GBT:'. Insira a indicação correspondente.")
                else:
                    print_regra(23, "OK", "Primeira Etapa: Ausência de geradores/UGTM validada com sucesso.")

                # REGRA 27 (Coerência do Executor)
                falhas_r27 = set()
                for mi in manobra_dados:
                    # Inspeção completa do nome da etapa e do texto do cabeçalho da etapa
                    etapa_n = re.sub(r'[ÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜ]', lambda m: 'AAAAAEEEEIIIIOOOOOUUUU'['ÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜ'.find(m.group(0))], f"{mi.get('etapa_nome', '')} {mi.get('etapa_texto_header', '')}".upper())
                    exec_n = re.sub(r'[ÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜ]', lambda m: 'AAAAAEEEEIIIIOOOOOUUUU'['ÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜ'.find(m.group(0))], mi.get('executor', '').strip().upper())
                    obs_n = re.sub(r'[ÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜ]', lambda m: 'AAAAAEEEEIIIIOOOOOUUUU'['ÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜ'.find(m.group(0))], f"{mi.get('observacao', '')} {mi.get('texto_linha', '')}".upper())
        
                    has_para_refletir = "PARA REFLETIR" in obs_n
        
                    # Executores Estritos Permitidos
                    is_exec_supervisor = (exec_n == "SUPERVISOR")
                    is_exec_cod_valido = (exec_n == "COD") and has_para_refletir
                    is_exec_tecnico = (exec_n == "TECNICO")
                    is_exec_regiao = (exec_n == "REGIAO")

                    # Se for manobra de TERCEIROS, Região e Técnico também podem atuar no Desligamento/Religamento
                    exec_valido_dr = is_exec_supervisor or is_exec_cod_valido or (is_manobra_terceiros and (is_exec_regiao or is_exec_tecnico))

                    nome_exib = mi.get('etapa_nome') or mi.get('etapa_texto_header') or 'Etapa'

                    is_desligamento = "DESLIGAMENTO" in etapa_n and "RELIGAMENTO" not in etapa_n
                    is_religamento = "RELIGAMENTO" in etapa_n

                    if (is_desligamento or is_religamento) and not exec_valido_dr:
                        tipo_etapa = "Desligamento" if is_desligamento else "Religamento"
                        if exec_n == "COD" and not has_para_refletir:
                            falhas_r27.add(f"Etapa '{nome_exib}': {tipo_etapa} executado pelo COD exige incluir a observação '(PARA REFLETIR)'.")
                        else:
                            falhas_r27.add(f"Etapa '{nome_exib}': {tipo_etapa} exige executor 'SUPERVISOR' ou 'COD (PARA REFLETIR)' (encontrado: '{mi.get('executor') or 'Vazio'}').")
                    elif ("MANOBRA PELO TECNICO" in etapa_n or "MANOBRA PELO TÉCNICO" in etapa_n) and not is_exec_tecnico:
                        falhas_r27.add(f"Etapa '{nome_exib}': Etapa 'MANOBRA PELO TÉCNICO' exige executor 'TECNICO' (encontrado: '{mi.get('executor') or 'Vazio'}').")

                if falhas_r27:
                    print_regra(27, "ALERTA", falhas_r27)
                elif manobra_dados:
                    print_regra(27, "OK", "Executores validados com sucesso para as etapas de Desligamento, Religamento e Manobra pelo Técnico.")

                # REGRA 29 (Verificação de Anormalidade por Alimentador)
                contagem_alim = {}
                verificacao_cod_ma09 = set()
                alimentadores_isentos = set()
                for mi in manobra_dados:
                    alim = mi.get('alimentador', '').strip()
                    eq = mi.get('equipamento', '').strip()
                    eff_alim = alim if alim and alim != '-' and bool(re.search(r'[0-9]', alim)) else None
        
                    # Se for um item de alimentador puro (Ex: PIUD217) no campo equipamento
                    if bool(re.search(r'[A-Za-z]', eq)) and bool(re.search(r'[0-9]', eq)) and ('-' not in eq) and eq != '-' and not eff_alim:
                        eff_alim = eq

                    # Fallback de busca de alimentador pelo equipamento se eff_alim ainda não foi encontrado
                    if not eff_alim and eq:
                        if eq in sol_dict:
                            eff_alim = sol_dict[eq].get('alim')
                        if not eff_alim:
                            eq_info = _get_eq_data(dados_equipamentos, eq, '')
                            if isinstance(eq_info, dict):
                                eff_alim = eq_info.get('alim')
            
                    if eff_alim:
                        contagem_alim[eff_alim] = contagem_alim.get(eff_alim, 0) + 1
            
                    et = mi.get('etapa_texto_header', '') + " " + mi.get('etapa_nome', '')
                    tx = mi.get('texto_linha', '')
                    ob = mi.get('observacao', '')
                    execut_cod = mi.get('executor', '')
        
                    # Checar se é uma etapa de MANOBRA PELO TÉCNICO com comentário de GERADOR ou DISJUNTOR DE INTERLIGAÇÃO
                    txt_completo_item = f"{et} {tx} {ob} {eq}".upper()
                    txt_sem_acento = re.sub(r'[ÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜ]', lambda m: 'AAAAAEEEEIIIIOOOOOUUUU'['ÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜ'.find(m.group(0))], txt_completo_item)
        
                    is_manobra_tecnico = "MANOBRA PELO TECNICO" in txt_sem_acento
                    tem_isencao_gerador = any(termo in txt_sem_acento for termo in [
                        "GERADOR DE BT",
                        "GERADOR DE MT",
                        "DISJUNTOR DE INTERLIGACAO"
                    ])
        
                    if is_manobra_tecnico and tem_isencao_gerador and eff_alim:
                        alimentadores_isentos.add(eff_alim)
            
                    is_cod_executando = bool(re.search(r'\bCOD\b', execut_cod, re.IGNORECASE)) or bool(re.search(r'\bVERIFICA[CÇ]?[AÃ]?O\s*(?:PELO|DO|DA)?\s*COD\b', et + " " + tx + " " + ob, re.IGNORECASE))
                    if is_cod_executando and re.search(r'\b\d*MA09\b', tx + " " + ob, re.IGNORECASE):
                        if eff_alim: 
                            verificacao_cod_ma09.add(eff_alim)
                        else:
                            print_regra(29, "ALERTA", "Linha com MA09 pelo COD: Campo 'Alimentador' está vazio. Preencha o alimentador correspondente.")

                falhas_r29 = [f"Alimentador '{a}': Manobra iniciada sem a ação MA09 (Verificação de Anormalidade) pelo COD. Insira a macro MA09." for a, c in contagem_alim.items() if a not in verificacao_cod_ma09 and a not in alimentadores_isentos]
                if falhas_r29:
                    print_regra(29, "ERRO", falhas_r29)
                elif contagem_alim:
                    print_regra(29, "OK", "Todos os alimentadores envolvidos possuem a verificação MA09 vinculada ao COD (ou são isentos por se tratarem de Geradores/Interligação de SE fictícia).")

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
                                print_regra(1, "ERRO", f"Equipamento '{eq}' (constante na Solicitação) não foi encontrado na Manobra. Insira o equipamento na manobra ou corrija o nome.")
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
                                print_regra(3, "ERRO", f"Equipamento '{eq}': Alimentador divergente da Solicitação (Esperado: {sol_alim}, Encontrado: {alims_str}). Ajuste o alimentador na manobra.")

                        # REGRA 4
                        if not sol_local or sol_local == "-":
                            pass  # IGNORADA silenciosa
                        else:
                            local_ok = any(_compare_local(sol_local, mi['local']) for mi in manobra_items)
                            if local_ok:
                                print_regra(4, "OK", f"Local '{sol_local}' confirmado para o equipamento '{eq}'.")
                            else:
                                locais_found = set(mi['local'] for mi in manobra_items if mi['local'] and mi['local'] != '-')
                                locais_str = ", ".join(locais_found) if locais_found else "Nenhum"
                                print_regra(4, "ERRO", f"Equipamento '{eq}': Local divergente da Solicitação (Esperado: {sol_local}, Encontrado: {locais_str}). Ajuste o local na manobra.")


                print("\n=== FASE: Restrições Físicas e Engenharia (Fase 4) ===")
                if not manobra_map:
                    print("⚠️  Manobra vazia. Sem equipamentos manobrados.")
        
                # Encontra o limite cronológico da etapa de DESLIGAMENTO para a Regra de Sinalização
                limite_cronologia_desligamento = _obter_limite_pre_desligamento(manobra_dados)

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
                    is_telecontrolado = _verificar_telecontrole(eq, eq_data, manobra_items)
        
                    # REGRA 31: ESTADO DO EQUIPAMENTO
                    # Verifica se o equipamento está sendo aberto/fechado em coerência com seu estado atual no Gemini

                    # Identifica o prefixo do equipamento (priorizando topologia e fallback por string)
                    prefixo = _obter_prefixo_equipamento(eq, eq_data)
                    is_trafo = (prefixo == "01")
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
                            print_regra(6, "ERRO", f"Equipamento '{eq}': Ações ({acoes_str}) são incompatíveis com o prefixo do equipamento. Corrija as macros.")
                        else:
                            print_regra(6, "OK", f"Nenhuma ação incompatível detectada para o prefixo de '{eq}'.")
                    else:
                        pass  # IGNORADA silenciosa

                    # REGRA 7 (Modo Local para Equipamentos Telecontrolados)
                    fases_eq = _obter_fases_equipamento(eq, eq_data, manobra_items, sol_info)
                    txt_busca_mono = (
                        str(eq) + ' ' + 
                        str(eq_data) + ' ' + 
                        str(sol_info) + ' ' + 
                        ' '.join([
                            str(mi.get('texto_linha', '')) + ' ' + 
                            str(mi.get('observacao', '')) + ' ' + 
                            str(mi.get('etapa_nome', '')) + ' ' + 
                            str(mi.get('etapa_texto_header', '')) 
                            for mi in manobra_items
                        ])
                    ).upper()
        
                    is_monofasico = (fases_eq in ['A', 'B', 'C']) or any(w in txt_busca_mono for w in [
                        'MONOFASICO', 'MONOFÁSICO', 'MONOFASICA', 'MONOFÁSICA', 'MONOFA', 'MONO', 
                        'UNIPOLAR', 'UNIP', 'FASE A', 'FASE B', 'FASE C', 'FASE-A', 'FASE-B', 'FASE-C', 
                        'FASEA', 'FASEB', 'FASEC', '1FASE', '1-FASE', '1 FASE', '1PH'
                    ])

                    # Equipamentos com apenas ações de sinalização (MA06, MA07, MA08, MAA6, MAA7) não exigem MA64
                    tem_apenas_sinalizacao = False
                    if manobra_items:
                        tem_apenas_sinalizacao = all(
                            bool(re.search(r'\b\d*(MA06|MA07|MA08|MAA6|MAA7)\b', mi.get('texto_linha', ''), re.IGNORECASE)) or 
                            'SINALIZAR' in mi.get('texto_linha', '').upper()
                            for mi in manobra_items
                        )

                    # Operação efetuada pelo técnico no campo ou em etapa de manobra pelo técnico é isenta de MA64
                    is_operacao_tecnico = False
                    if manobra_items:
                        is_operacao_tecnico = any(
                            str(mi.get('executor', '')).upper() in ['TECNICO', 'TÉCNICO', 'REGIAO', 'REGIÃO'] or
                            any(k in (str(mi.get('etapa_nome', '')) + ' ' + str(mi.get('etapa_texto_header', ''))).upper() for k in ['TECNICO', 'TÉCNICO', 'CAMPO'])
                            for mi in manobra_items
                        )

                    if eq in sol_dict:
                        if prefixo == "02":
                            print_regra(7, "OK", f"Equipamento '{eq}' é Regulador de Tensão, isento de Modo Local (MA64).")
                        elif is_monofasico:
                            print_regra(7, "OK", f"Equipamento '{eq}' é monofásico, isento de Modo Local (MA64).")
                        elif tem_apenas_sinalizacao:
                            print_regra(7, "OK", f"Equipamento '{eq}' possui apenas ação de Sinalização, isento de Modo Local (MA64).")
                        elif is_operacao_tecnico:
                            print_regra(7, "OK", f"Equipamento '{eq}' é operado pelo Técnico no campo, isento de Modo Local (MA64) via telecontrole.")
                        elif is_telecontrolado:
                            acao_ma64_encontrada = any(re.search(r'\b\d*MA64\b', mi['texto_linha'], re.IGNORECASE) for mi in manobra_items)
                            if acao_ma64_encontrada:
                                print_regra(7, "OK", f"Equipamento telecontrolado '{eq}' possui a macro MA64 (Modo Local).")
                            else:
                                print_regra(7, "ERRO", f"Equipamento '{eq}': Equipamento telecontrolado exige incluir a macro MA64 (Modo Local) antes da operação.")
                        else:
                            print_regra(7, "OK", f"Equipamento '{eq}' é manual, não exige Modo Local.")
                    else:
                        pass  # IGNORADA silenciosa

                    # REGRA 31 (Coerência de POSOPE: Abertura em NF, Fechamento em NA)
                    posope = str(eq_data.get('posope', eq_data.get('POSOPE', eq_data.get('estado', '')))).strip().upper()
                    if posope in ['ABERTO', 'ABERTA', 'A', 'DESLIGADO']:
                        posope = 'A'
                    elif posope in ['FECHADO', 'FECHADA', 'F', 'LIGADO']:
                        posope = 'F'
                    else:
                        posope = ''

                    # Identifica sequência cronológica de operações do equipamento
                    acoes_cronologicas = []
                    for mi in sorted(manobra_items, key=lambda x: x.get('cronologia', 0)):
                        t_lin = mi.get('texto_linha', '').upper()
                        if macros_abertura.search(t_lin) or re.search(r'\bABRIR\b', t_lin):
                            acoes_cronologicas.append('ABRIR')
                        elif macros_fechamento.search(t_lin) or re.search(r'\bFECHAR\b', t_lin):
                            acoes_cronologicas.append('FECHAR')

                    txt_eq_completo = ' '.join([
                        str(eq) + ' ' + 
                        str(mi.get('texto_linha', '')) + ' ' + 
                        str(mi.get('observacao', '')) + ' ' + 
                        str(mi.get('etapa_nome', '')) + ' ' + 
                        str(mi.get('etapa_texto_header', ''))
                        for mi in manobra_items
                    ]).upper()

                    tem_indicativo_na = any(w in txt_eq_completo for w in [
                        'GERADOR', 'UGTM', 'INTERLIG', 'SOCORRO', 'TRANSFERENCIA', 'PONTO DE SOCORRO'
                    ])

                    origem_cadastro = eq_data.get('origem', '')
                    alims_cad = [str(a).upper() for a in eq_data.get('alimentadores', [])]
                    divergencia_circuito = bool(alim_manobra and alims_cad and not any(alim_manobra.upper() in a for a in alims_cad))

                    # Regra de Ouro da Topologia Operacional:
                    # Se um equipamento é FECHADO no início da manobra e posteriormente ABERTO na recomposição,
                    # o seu estado operacional de repouso no campo é ABERTO (NA).
                    # Se o cadastro estático for antigo (ou tiver alimentador divergente/contexto de gerador),
                    # a lógica da manobra prevalece para evitar falso-positivo em chaves NA.
                    if acoes_cronologicas and acoes_cronologicas[0] == 'FECHAR' and 'ABRIR' in acoes_cronologicas[1:]:
                        if origem_cadastro != 'GDIS_AO_VIVO' or tem_indicativo_na or divergencia_circuito:
                            posope = 'A'
                    elif acoes_cronologicas and acoes_cronologicas[0] == 'ABRIR' and 'FECHAR' in acoes_cronologicas[1:]:
                        if origem_cadastro != 'GDIS_AO_VIVO' or divergencia_circuito:
                            posope = 'F'

                    # Inferência de POSOPE inicial caso ainda ausente no cadastro
                    if not posope:
                        # Termos explícitos de NA (Normal Aberto)
                        tags_na = ['(NA)', 'CHAVE NA', 'POSOPE NA', 'POSOPE: NA',
                                   'NORMAL ABERTO', 'NORMAL ABERTA',
                                   'NORMALMENTE ABERTO', 'NORMALMENTE ABERTA']
                        # Termos explícitos de NF (Normal Fechado)
                        tags_nf = ['(NF)', 'CHAVE NF', 'POSOPE NF', 'POSOPE: NF',
                                   'NORMAL FECHADO', 'NORMAL FECHADA',
                                   'NORMALMENTE FECHADO', 'NORMALMENTE FECHADA']

                        tem_na_explicito = (
                            any(k in txt_eq_completo for k in tags_na)
                            or bool(re.search(r'\bNA\b', txt_eq_completo))
                        )
                        tem_nf_explicito = (
                            any(k in txt_eq_completo for k in tags_nf)
                            or bool(re.search(r'\bNF\b', txt_eq_completo))
                        )

                        if tem_na_explicito and not tem_nf_explicito:
                            posope = 'A'
                        elif tem_nf_explicito and not tem_na_explicito:
                            posope = 'F'
                        elif acoes_cronologicas:
                            # Inferência de Engenharia Operacional CEMIG:
                            # Se a primeira ação é ABRIR (ex: para desligamento), seu estado sob carga era FECHADO (NF).
                            # Se a primeira ação é FECHAR (ex: socorro/transferência), seu estado sob repouso era ABERTO (NA).
                            if acoes_cronologicas[0] == 'ABRIR':
                                posope = 'F'
                                print_regra(31, "INFO", f"Estado de '{eq}' determinado como NF (Normalmente Fechado) a partir da ação inicial de ABERTURA.")
                            elif acoes_cronologicas[0] == 'FECHAR':
                                posope = 'A'
                                print_regra(31, "INFO", f"Estado de '{eq}' determinado como NA (Normalmente Aberto) a partir da ação inicial de FECHAMENTO.")
                        else:
                            # Equipamento sem ações de abertura/fechamento diretas (apenas bloqueio ou sinalização)
                            # Para Religadores (prefixo 22) e Disjuntores (prefixo 21): regime normal da rede é NF (Fechado).
                            tem_bloqueio_relig = any(re.search(r'\b\d*(MA14|MA15|MA16|MA17|MA21|MA28)\b', mi.get('texto_linha', ''), re.IGNORECASE) for mi in manobra_items)
                            if prefixo in ['21', '22'] or tem_bloqueio_relig:
                                posope = 'F'
                                print_regra(31, "INFO", f"Equipamento '{eq}' (Religador/Disjuntor): Regime operacional determinado como NF (Normalmente Fechado) por padrão de rede.")
                            elif (eq in sol_dict or any(_get_eq_id(k) == _get_eq_id(eq) for k in sol_dict)) and not tem_indicativo_na:
                                posope = 'F'
                                print_regra(31, "INFO", f"Equipamento '{eq}' (Alvo da Solicitação): Determinado como NF por delimitação da zona de trabalho.")
                            else:
                                posope = ''

                    estado_simulado = posope
                    primeira_acao = None
                    erro_31 = []
        
                    # Auxiliares para Regra de Sinalização Pré-Desligamento (Regra 42)
                    abriu_ate_desligamento = False
                    quem_abriu_ate_desligamento = ""
                    sinalizou_ate_desligamento = False

                    # Sincronização inicial por macros de supervisão em etapas de verificação (MA39/MA49)
                    for mi in manobra_items:
                        txt = mi['texto_linha'].upper()
                        if re.search(r'\b\d*MA39\b', txt) or "CONFIRMAR EQUIPAMENTO ABERTO" in txt:
                            if not estado_simulado:
                                estado_simulado = "A"
                        elif re.search(r'\b\d*MA49\b', txt) or "CONFIRMAR EQUIPAMENTO FECHADO" in txt:
                            if not estado_simulado:
                                estado_simulado = "F"

                    for mi in manobra_items:
                        etapa_txt = (mi.get('etapa_nome', '') + ' ' + mi.get('etapa_texto_header', '')).upper()
                        txt = mi['texto_linha'].upper()
                        executor = mi.get('executor', '').upper()
                        obs = mi.get('observacao', '').upper()
                        cron = mi.get('cronologia', 0)
            
                        # --- REGRA 41: MA63 (TROCA DE ELO FUSÍVEL) ---
                        if "MA63" in txt:
                            if not any(k in executor for k in ("REGIAO", "REGIÃO")):
                                print_regra(41, "ERRO", f"Equipamento '{eq}': Macro MA63 (Troca de Elo) executada por '{executor}'. Exige ser executada pela Região.")

                        # --- REGRA 31: Sincronização Explícita na Linha ---
                        if re.search(r'\b\d*MA39\b', txt):
                            estado_simulado = "A"
                            print_regra(31, "INFO", f"Sincronizando estado de '{eq}' para ABERTO via macro MA39.")
                        elif re.search(r'\b\d*MA49\b', txt):
                            estado_simulado = "F"
                            print_regra(31, "INFO", f"Sincronizando estado de '{eq}' para FECHADO via macro MA49.")

                        is_abertura = bool(macros_abertura.search(txt) or re.search(r'\bABRIR\b', txt))
                        is_fechamento = bool(macros_fechamento.search(txt) or re.search(r'\bFECHAR\b', txt))

                        # --- RASTREIO PARA REGRA DE SINALIZAÇÃO ---
                        if cron <= limite_cronologia_desligamento:
                            if is_abertura:
                                abriu_ate_desligamento = True
                                quem_abriu_ate_desligamento = executor
                            if any(m in txt for m in ["MA06", "MA31", "MA30", "MAA9", "MA54", "MA56", "MA88"]):
                                sinalizou_ate_desligamento = True

                        if is_abertura:
                            if not primeira_acao: primeira_acao = 'ABRIR'
                            # Só emite erro se há certeza de que estava ABERTO (posope=A confirmado)
                            if estado_simulado == 'A':
                                msg = f"Tentativa de Abertura em equipamento que já consta como Aberto (NA/POSOPE=A)"
                                erro_31.append(msg)
                            estado_simulado = 'A'
                        elif is_fechamento:
                            if not primeira_acao: primeira_acao = 'FECHAR'
                            # Só emite erro se há certeza de que estava FECHADO (posope=F confirmado).
                            # Quando o estado é desconhecido (''), fechar é operação válida (equipamento NA → NF).
                            if estado_simulado == 'F':
                                msg = f"Tentativa de Fechamento em equipamento que já consta como Fechado (NF/POSOPE=F)"
                                erro_31.append(msg)
                            estado_simulado = 'F'

                    # --- DETECÇÃO DE BATE-VOLTA / REVERSÃO PREMATURA NAS ETAPAS PRÉ-DESLIGAMENTO ---
                    historico_pre_desligamento = []
                    for mi in manobra_items:
                        etapa_raw = mi.get('etapa_texto_header') or mi.get('etapa_nome') or mi.get('grupo_id') or 'Etapa'
                        m_etapa = re.search(r'(\d{2,3}\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ]+)', etapa_raw, re.IGNORECASE)
                        etapa_nome_limpo = m_etapa.group(1).title() if m_etapa else etapa_raw.strip()
            
                        txt = mi['texto_linha'].upper()
                        cron = mi.get('cronologia', 0)
                        is_ab = bool(macros_abertura.search(txt) or re.search(r'\bABRIR\b', txt))
                        is_fe = bool(macros_fechamento.search(txt) or re.search(r'\bFECHAR\b', txt))
            
                        eh_pre_desligamento = (limite_cronologia_desligamento != -1) and (cron <= limite_cronologia_desligamento)
            
                        if eh_pre_desligamento:
                            if is_ab:
                                historico_pre_desligamento.append((etapa_nome_limpo, 'ABRIR'))
                            elif is_fe:
                                historico_pre_desligamento.append((etapa_nome_limpo, 'FECHAR'))

                    for idx in range(len(historico_pre_desligamento) - 1):
                        et_1, act_1 = historico_pre_desligamento[idx]
                        et_2, act_2 = historico_pre_desligamento[idx+1]
                        if act_1 != act_2:
                            msg = f"Reversão prematura pré-desligamento na {et_2} ({act_2} após {act_1} na {et_1}). Essa alteração desfaz o alívio prévio e pode provocar corte indevido de clientes."
                            erro_31.append(msg)

                    # --- REGRA 42: SINALIZAÇÃO PÓS-ABERTURA (ATÉ DESLIGAMENTO) ---
                    # Aplica-se apenas a equipamentos pertencentes ao escopo da Solicitação GDIS
                    if (eq in sol_dict) and abriu_ate_desligamento and not sinalizou_ate_desligamento:
                        if "COD" in quem_abriu_ate_desligamento:
                            print_regra(42, "ALERTA", f"Equipamento '{eq}': Abertura executada pelo COD até o desligamento sem a macro MA06 de sinalização.")
                        else:
                            print_regra(42, "ERRO", f"Equipamento '{eq}': Abertura executada por '{quem_abriu_ate_desligamento}' até o desligamento sem a macro MA06 (Sinalização). Insira a macro MA06.")

                    # --- CASO ESPECIAL: REGULADOR DE TENSÃO (RT - PREFIXO 02) ---
                    # Reguladores de Tensão não são chaves de abertura/fechamento (não possuem estado NA/NF).
                    # Seu ciclo operativo consiste em neutralização e desligamento de controle (MA35) 
                    # durante a transferência de carga e recolocação em serviço (MA36) na recomposição.
                    if prefixo == "02":
                        tem_ma35 = any(re.search(r'\b\d*MA35\b', mi['texto_linha'], re.IGNORECASE) for mi in manobra_items)
                        tem_ma36 = any(re.search(r'\b\d*MA36\b', mi['texto_linha'], re.IGNORECASE) for mi in manobra_items)
                        if tem_ma35 and tem_ma36:
                            print_regra(31, "OK", f"Equipamento '{eq}' (Regulador de Tensão): Ciclo operativo validado com sucesso (MA35 Neutro ➔ MA36 Em Serviço).")
                        elif tem_ma35:
                            print_regra(31, "OK", f"Equipamento '{eq}' (Regulador de Tensão): Neutralização e bloqueio de comando aplicados (MA35).")
                        elif tem_ma36:
                            print_regra(31, "OK", f"Equipamento '{eq}' (Regulador de Tensão): Recolocação em serviço aplicada (MA36).")
                        else:
                            print_regra(31, "OK", f"Equipamento '{eq}' (Regulador de Tensão): Mantido em regime normal de operação.")
                    elif posope in ['A', 'F'] or primeira_acao or erro_31:
                        if erro_31:
                            str_erros = " | ".join(sorted(set(erro_31)))
                            print_regra(31, "ERRO", f"Equipamento '{eq}': Incoerência no estado operacional ({str_erros}). Revise as ações de abertura/fechamento.")
                        elif primeira_acao:
                            if posope in ['A', 'F']:
                                print_regra(31, "OK", f"Ações coerentes com a evolução do estado POSOPE={posope} em '{eq}'.")
                            else:
                                print_regra(31, "ALERTA", f"Equipamento '{eq}': Não foi possível identificar o estado inicial do equipamento (sem tag NA/NF). Operação de {primeira_acao} permitida sem validação de redundância.")
                        else:
                            # Se não houve ação mas o estado final bate, pode ser sincronismo
                            tem_sinc = any(re.search(r'\b\d*(MA39|MA49)\b', mi['texto_linha'], re.IGNORECASE) for mi in manobra_items)
                            if tem_sinc:
                                print_regra(31, "INFO", f"Estado de '{eq}' sincronizado via macro de supervisão (MA39/MA49).")
                            elif posope in ['A', 'F']:
                                print_regra(31, "OK", f"Equipamento '{eq}' manteve estado estável POSOPE={posope}.")
                            else:
                                print_regra(31, "ALERTA", f"Equipamento '{eq}': Não foi possível identificar o estado do equipamento (POSOPE/NA/NF ausente).")
                    else:
                        print_regra(31, "ALERTA", f"Equipamento '{eq}': Não foi possível identificar o estado do equipamento (POSOPE/NA/NF ausente).")

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
                            print_regra(8, "ERRO", f"Equipamento '{eq}': Macros ({str_macros}) são exclusivas de Regulador de Tensão (Prefixos 02/Alimentador). Remova as macros indevidas.")
                        else:
                            print_regra(8, "OK", "Macros exclusivas de RT aplicadas corretamente.")
                    else:
                        pass  # IGNORADA silenciosa

                    # REGRA 9 (Macros de operação de Religador/Disjuntor)
                    macros_relig_disj = ["MA14", "MA15", "MA16", "MA17", "MA19", "MAA4", "MAA5"]
                    acoes_rd_encontradas = set()
                    for mi in manobra_items:
                        for m_rd in macros_relig_disj:
                            if re.search(r'\b\d*' + m_rd + r'\b', mi['texto_linha'], re.IGNORECASE):
                                acoes_rd_encontradas.add(m_rd.upper())
                    if acoes_rd_encontradas:
                        is_relig_disj = (prefixo in ["21", "22"])
                        if not (is_relig_disj or is_alim):
                            str_macros = ", ".join(sorted(acoes_rd_encontradas))
                            print_regra(9, "ERRO", f"Equipamento '{eq}': Macros ({str_macros}) são exclusivas de Religador/Disjuntor (Prefixos 21/22). Remova as macros indevidas.")
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
                            print_regra(10, "ERRO", f"Equipamento '{eq}': Macros ({str_macros_bloq}) de Chave Deslocada são inválidas. {motivo_falha_10}")
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
                            print_regra(11, "ERRO", f"Equipamento '{eq}': Macros de ajuste ({str_macros_ajustes}) são permitidas apenas para Religadores/Disjuntores (Prefixos 21, 22, 23). Remova as macros.")
                        else:
                            print_regra(11, "OK", "Macros de alteração de ajustes de proteção aplicadas corretamente.")
                    else:
                        pass  # IGNORADA silenciosa

                    # REGRA 12 (Posicionamento / POS. MANOBRAR obrigatório para operação local pela Região)
                    macros_operacao = ["MA01", "MA02", "MA31", "MA66", "MA30", "MA67"]
                    falhas_12 = set()
                    teve_operacao_regiao = False
                    tem_mab9 = any(re.search(r'\b\d*MAB9\b', mi['texto_linha'], re.IGNORECASE) for mi in manobra_items)
        
                    for mi in manobra_items:
                        etapa_nome = mi.get('etapa_nome', '').upper()
                        etapa_header = mi.get('etapa_texto_header', '').upper()
                        # Etapas de pique (MANOBRA COM PIQUE / MANOBRA C/ PIQUE RISCO SISTEMA) usam MA27 em vez de POS. MANOBRAR
                        if "PIQUE" in etapa_nome or "PIQUE" in etapa_header:
                            continue

                        execut = mi['executor'].upper()
                        posic = mi.get('posicionamento', '').upper()
                        pos_obrigatorio = (posic in ['SIM', 'S', 'TRUE', '1'])
            
                        # Executor deve ser especificamente Região / Regiao
                        is_execut_regiao = ('REGIAO' in execut or 'REGIÃO' in execut)
            
                        if is_execut_regiao:
                            for m_op in macros_operacao:
                                if re.search(r'\b\d*' + m_op + r'\b', mi['texto_linha'], re.IGNORECASE):
                                    teve_operacao_regiao = True
                                    if prefixo != "02" and not pos_obrigatorio and not tem_mab9:
                                        falhas_12.add(m_op.upper())
                    if falhas_12:
                        str_macros = ", ".join(sorted(falhas_12))
                        if is_manobra_terceiros:
                            print_regra(12, "ALERTA", f"Equipamento '{eq}': Operação pela Região ({str_macros}) em Manobra de Terceiros sem a coluna Posicionamento marcada como 'SIM'.")
                        else:
                            print_regra(12, "ERRO", f"Equipamento '{eq}': Operação pela Região ({str_macros}) exige marcar 'SIM' na coluna Posicionamento.")
                    elif teve_operacao_regiao:
                        if prefixo == "02":
                             print_regra(12, "OK", f"Equipamento '{eq}' (Regulador de Tensão) operado corretamente: telecontrole restrito aos TAPs.")
                        elif not tem_mab9:
                            print_regra(12, "OK", "Operação pela Região validada com POS. MANOBRAR / Posicionamento = SIM.")
                        elif tem_mab9:
                            print_regra(12, "OK", "Exceção validada: macro MAB9 justifica a ausência de telecontrole/posicionamento.")
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
                                txt_linha_obs = (str(mi.get('texto_linha', '')) + ' ' + str(mi.get('observacao', '')) + ' ' + str(mi.get('etapa_nome', '')) + ' ' + str(mi.get('etapa_texto_header', ''))).upper()
                                
                                is_na = (posope == 'A') or any(re.search(r'\b\d*MA39\b', item['texto_linha'], re.IGNORECASE) for item in manobra_items)
                                tem_corte_ou_alivio = any(kw in txt_linha_obs for kw in [
                                    'CORTE DE CARGA', 'CORTE DE CARGAS', 'SEM CARGA', 'CARGA ALIVIADA', 
                                    'ALIVIO', 'ALÍVIO', 'TRANSFERIDA', 'TRANSFERENCIA', 'TRANSFERÊNCIA', 
                                    'INTERLIGACAO', 'INTERLIGAÇÃO', 'ISOLAMENTO', 'SEM CORTE', 'CARGA ZERO', 'DESENERGIZADO', '0A', '0 A'
                                ])
                                
                                if is_telecontrolado and not tem_mab9 and not is_na:
                                    if not tem_corte_ou_alivio:
                                        falha_r13 = True
                    if falha_r13:
                        print_regra(13, "ALERTA", f"Equipamento '{eq}': Abertura (MA01) pela Região exige a indicação 'CORTE DE CARGA' ou 'CARGA ALIVIADA' na observação.")
                    elif teve_ma01_regiao:
                        if not is_telecontrolado or tem_mab9:
                            print_regra(13, "OK", f"Abertura de equipamento manual ou justificado por MAB9 validada para '{eq}'.")
                        else:
                            print_regra(13, "OK", f"Abertura local MA01 de '{eq}' confirmada com indicação de carga/alívio.")
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
                        print_regra(14, "ERRO", f"Equipamento '{eq}': Executor 'COD' não pode ter marcação de Posicionamento ('SIM'). Remova a marcação.")
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
                                    elif not is_telecontrolado:
                                        falhas_r15.add(m_op.upper())
                                        motivos_r15.add("Equipamento não possui telecontrole")
                                    elif prefixo == "02" and m_op.upper() in ["MA01", "MA02", "MA31", "MA30"]:
                                        falhas_r15.add(m_op.upper())
                                        motivos_r15.add("COD não realiza abertura/fechamento direto de Regulador de Tensão (02)")
                    if falhas_r15:
                        str_macros = ", ".join(sorted(falhas_r15))
                        str_motivos = " e ".join(sorted(motivos_r15))
                        print_regra(15, "ERRO", f"Equipamento '{eq}': Operação remota ({str_macros}) pelo COD é irregular ({str_motivos}). Ajuste a operação.")
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
                        print_regra(16, "ERRO", f"Equipamento '{eq}': Etapa 'VERIFICAÇÃO PELO COD' exige executor 'COD' (encontrado: '{str_executores}').")
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
                                motivo_r17 = f"Equipamento '{eq}': Macro MA09 (Anormalidade) deve ser atribuída ao Alimentador, não ao equipamento."
                            elif is_bypass and prefixo not in ["02", "22", "23"]:
                                falha_r17 = True
                                motivo_r17 = f"Equipamento '{eq}': Macro MA09 (By-pass) é permitida apenas em Reguladores e Religadores (Prefixos 02, 22, 23)."
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
                        print_regra(18, "ERRO", f"Equipamento '{eq}': Macros de By-pass ({str_bp}) são permitidas apenas para Reguladores/Religadores (Prefixos 02, 22, 23). Remova as macros.")
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
                        print_regra(19, "ERRO", f"Alimentador '{eq}': Macro MAC1 é permitida apenas em equipamentos físicos, não em alimentadores. Remova a macro.")
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
                
                            is_regiao = ('REGIAO' in execut or 'REGIÃO' in execut or 'SUPERVISOR' in execut or 'TECNICO' in execut or 'TÉCNICO' in execut or (execut != 'COD' and bool(execut)))
                
                            if not (is_abertura or is_fechamento):
                                falhas_r39.add(f"Ação não é Abertura/Fechamento (Ação detectada: {txt.strip()[:20]})")
                            if not is_regiao:
                                falhas_r39.add(f"Executor não é de campo/Região (Atual: {execut})")
                    
                    if falhas_r39:
                        str_falhas = ", ".join(sorted(falhas_r39))
                        print_regra(39, "ERRO", f"Equipamento '{eq}': Posicionamento marcado como 'SIM' sem atender aos critérios ({str_falhas}). Ajuste a marcação.")
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
                        print_regra(35, "ERRO", "Primeira Etapa: Executor 'Região' presente na manobra, porém a diretriz 'EQUIPES:X' não foi informada no cabeçalho. Insira 'EQUIPES:X'.")
                    elif tem_equipes_header and not tem_executor_regiao:
                        print_regra(35, "ALERTA", "Primeira Etapa: Diretriz 'EQUIPES:X' informada no cabeçalho, mas nenhuma etapa é executada pela Região.")
                    else:
                        if tem_equipes_header and tem_executor_regiao:
                            print_regra(35, "OK", "Equipes informadas no cabeçalho e confirmadas por ações da Região.")
                        else:
                            pass # Ninguém tem Região nem Equipes: OK silencioso

                print("\n=== FASE: Balanço e Cronologia (Fase 5) ===")
                if not manobra_map:
                    print("⚠️  Manobra vazia. Sem equipamentos manobrados.")
        
                limite_cronologia_desligamento = _obter_limite_pre_desligamento(manobra_dados)

                for eq, manobra_items in manobra_map.items():
                    print(f"\n🔹 Equipamento: {eq}")
        
                    # Obtém prefixo do equipamento para inverter MA77 corretamente (Regra 22)
                    alim_m_item = manobra_items[0].get('alim', '') if manobra_items else ''
                    eq_data_loop = _get_eq_data(dados_equipamentos, eq, alim_m_item)
                    prefixo_eq = _obter_prefixo_equipamento(eq, eq_data_loop)
        
                    # REGRA 2 (Ação Inicial de Abertura e Sinalização até o Desligamento) - Apenas para equipamentos da solicitação
                    eq_id_atual = _get_eq_id(eq)
                    is_sol_eq = (eq in sol_dict) or any(_get_eq_id(k) == eq_id_atual for k in sol_dict.keys())

                    if is_sol_eq:
                        itens_ate_deslig = [mi for mi in manobra_items if _item_pertence_fase_desligamento(mi, limite_cronologia_desligamento)]
            
                        tem_completa = any(
                            re.search(r'\b\d*(MA31|MA30|MA18|MAA9)\b', mi['texto_linha'], re.IGNORECASE) or
                            ("ABRIR" in mi['texto_linha'].upper() and any(w in mi['texto_linha'].upper() for w in ["SINALIZ", "PLACA"]))
                            for mi in itens_ate_deslig
                        )
                        tem_abertura = any(
                            re.search(r'\b\d*(MA01|MA18|MA19|MA30|MA31|MA58|MA60|MAA4|MAA5|MAA9|MAB0)\b', mi['texto_linha'], re.IGNORECASE) or 
                            re.search(r'\bABRIR\b', mi['texto_linha'], re.IGNORECASE) or
                            "ABERTURA" in mi['texto_linha'].upper()
                            for mi in itens_ate_deslig
                        )
                        tem_sinalizacao = any(
                            re.search(r'\b\d*(MA06|MA08|MA18|MA30|MA31|MA54|MA56|MA88|MAA6|MAA9)\b', mi['texto_linha'], re.IGNORECASE) or 
                            re.search(r'\b(sinalizar|sinalizado|sinalizacao|sinalização)\b', mi['texto_linha'], re.IGNORECASE) or
                            "PLACA" in mi['texto_linha'].upper()
                            for mi in itens_ate_deslig
                        )

                        if tem_completa or (tem_abertura and tem_sinalizacao):
                            print_regra(2, "OK", f"Equipamento '{eq}': Abertura e Sinalização confirmadas até a etapa de Desligamento.")
                        elif tem_sinalizacao and not tem_abertura:
                            print_regra(2, "OK", f"Equipamento '{eq}': Sinalização confirmada até a etapa de Desligamento (Equipamento de delimitação NA/NF).")
                        elif tem_abertura and not tem_sinalizacao:
                            print_regra(2, "ALERTA", f"Equipamento '{eq}': Abertura executada até o desligamento sem a macro MA06 (Sinalização). Insira a macro MA06.")
                        else:
                            print_regra(2, "ALERTA", f"Equipamento '{eq}': Ausência de ação de Abertura (MA01/MA31) ou Sinalização (MA06) até o desligamento. Insira a macro correspondente.")

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
                        print_regra(22, "ERRO", f"Equipamento '{eq}': Divergência na reversão/normalização de macros ({str_falhas}). Insira as macros inversas.")
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
                                        if nome_grupo not in ["Abertura Simples (MA01/MA02)", "Abertura (MA31/MA66)", "At/Sinaliz. (MA30/MA67)", "Disjuntor/Relig. (MA18/MA19)", "Subestação (MA22/MA23)", "Barramento (MA24/MA25)", "Rede BT (MA56/MA57)", "Rede MT (MA54/MA55)", "By-pass (MA09/MA10)"]:
                                            falhas_r30.add(f"'{m_fe}' sem '{'/'.join(aberturas)}' prévio")
                                    else:
                                        saldos_crono[nome_grupo] -= 1
                                    teve_acao_crono = True

                    if falhas_r30:
                        str_falhas = ", ".join(sorted(falhas_r30))
                        print_regra(30, "ERRO", f"Equipamento '{eq}': Sequência cronológica de macros invertida ({str_falhas}). Reordene as etapas.")
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
                            eq_info = _get_eq_data(dados_equipamentos, eq_map, mi.get('alim', ''))
                            fases_eq = _obter_fases_equipamento(eq_map, eq_info, mi)
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
                            print_regra(32, "ERRO", f"Etapa '{eh_grupo}' (Alim {alim_key}): Abertura trifásica ({str_tri}) e fechamento monofásico ({str_mono}) na mesma etapa. Separe em etapas distintas.")
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
                            print_regra(33, "ERRO", "Chave ASTA: Macro MA30 exige incluir a observação 'COM CARGA'.")
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
                        print_regra(35, "ALERTA", f"Primeira Etapa: Cabeçalho indica EQUIPES:{num_equipes_header}, mas nenhuma etapa é executada pela Região.")
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
                    for f in falhas_r36: print_regra(36, "ALERTA", f"Sincronismo de Horário: Divergência detectada ({f}). Alinhe os horários.")
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
                            falhas_r37.append(f"Equipamento '{eq_id}': Ação MA60 (Abertura sob Carga) exige executor 'COD' (encontrado: '{execut}').")

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
                                        falhas_r38.append(f"Etapa '{etapa_nome}': Equipamento manual '{eq_nome}' com executor '{execut}'. Exige ser executado pela REGIAO.")

                    if falhas_r38:
                        for f in falhas_r38: print_regra(38, "ERRO", f)
                    else:
                        print_regra(38, "OK", "Operações em equipamentos manuais executadas corretamente pela Região.")

                # REGRA 44 (Sequência de Manobra com Pique e Pique Risco Sistema, CP:xx, MA27 e MA79)
                print("\n=== FASE: Sequência Manobra com Pique (Regra 44) ===")
                falhas_r44 = []
    
                macros_abertura_pique = re.compile(r'\b(MA01|MA31|MA30)\b(?!\s*-\s*OUTROS)')
                macros_fechamento_pique = re.compile(r'\b(MA02|MA66|MA67)\b(?!\s*-\s*OUTROS)')
    
                def _is_eq_telecontrolado(eq_nome, mi=None):
                    return _verificar_telecontrole(eq_nome, manobra_items=[mi] if mi else None)

                # Agrupar itens por etapa para analisar a ordem
                etapas_pique = {} # key: grupo_id, value: list of items
    
                for mi in manobra_dados:
                    etapa_nome = mi.get('etapa_nome', '').upper()
                    etapa_header = mi.get('etapa_texto_header', '').upper()
                    if "PIQUE" in etapa_nome or "PIQUE" in etapa_header:
                        grupo_id = mi.get('grupo_id', etapa_nome)
                        if grupo_id not in etapas_pique:
                            etapas_pique[grupo_id] = []
                        etapas_pique[grupo_id].append(mi)
            
                if not etapas_pique:
                    print_regra(44, "OK", "Nenhuma etapa de Manobra com Pique detectada.")
                else:
                    for grupo_id, itens_etapa in etapas_pique.items():
                        etapa_nome_real = itens_etapa[0].get('etapa_nome', grupo_id)
                        etapa_header_real = itens_etapa[0].get('etapa_texto_header', '')
                        texto_cabecario = (etapa_header_real + " " + etapa_nome_real).upper()
            
                        # 1. VALIDAÇÃO DO CABEÇALHO: CP:xx - DADOS / VOZ / SATELITAL
                        match_cp = re.search(r'\bCP\s*:\s*(\d+)\s*(?:-\s*|\s+)(DADOS|VOZ|SATELITAL)\b', texto_cabecario)
                        if not match_cp:
                            match_parcial = re.search(r'\bCP\s*:\s*(\d+)', texto_cabecario)
                            if match_parcial:
                                cp_val_parcial = int(match_parcial.group(1))
                                falhas_r44.append(f"Etapa '{etapa_nome_real}': Formato do canal no cabeçalho incorreto (CP:{cp_val_parcial}). Esperado: 'CP:{cp_val_parcial} - DADOS' (< 500) ou 'CP:{cp_val_parcial} - VOZ/SATELITAL' (>= 500).")
                            else:
                                falhas_r44.append(f"Etapa '{etapa_nome_real}': Obrigatório constar 'CP:xx - DADOS/VOZ/SATELITAL' no cabeçalho.")
                        else:
                            cp_val = int(match_cp.group(1))
                            cp_tipo = match_cp.group(2).upper()
                
                            if cp_val < 500 and cp_tipo != "DADOS":
                                falhas_r44.append(f"Etapa '{etapa_nome_real}': CP:{cp_val} < 500 exige canal 'DADOS' (encontrado: '{cp_tipo}').")
                            elif cp_val >= 500 and cp_tipo not in ["VOZ", "SATELITAL"]:
                                falhas_r44.append(f"Etapa '{etapa_nome_real}': CP:{cp_val} >= 500 exige canal 'VOZ' ou 'SATELITAL' (encontrado: '{cp_tipo}').")
            
                        # 2. VALIDAÇÃO DAS MACROS MA27 e MA79 E DA SEQUÊNCIA DE MANOBRA
                        itens_com_carga = []
                        for mi in itens_etapa:
                            txt_alvo = (mi.get('acao_bruta', '') + " " + mi.get('texto_linha', '') + " " + mi.get('observacao', '')).upper()
                            eq_nome = mi.get('equipamento', '') or mi.get('alimentador', '')
                            is_tele = _is_eq_telecontrolado(eq_nome, mi)
                
                            is_abertura = bool(macros_abertura_pique.search(txt_alvo))
                            is_fechamento = bool(macros_fechamento_pique.search(txt_alvo))
                
                            if is_abertura or is_fechamento:
                                itens_com_carga.append({
                                    'mi': mi,
                                    'eq': eq_nome,
                                    'txt': txt_alvo,
                                    'is_abrir': is_abertura,
                                    'is_fechar': is_fechamento,
                                    'is_tele': is_tele
                                })
            
                        if not itens_com_carga:
                            falhas_r44.append(f"Etapa '{etapa_nome_real}': Manobra com Pique sem nenhuma ação com Carga (MA01, MA02, MA31, MA66, MA30, MA67).")
                        else:
                            primeiro = itens_com_carga[0]
                            if not primeiro['is_abrir']:
                                falhas_r44.append(f"Etapa '{etapa_nome_real}': Primeiro equipamento operado ({primeiro['eq']}) deve ABRIR (MA01/MA31/MA30).")
                
                            if len(itens_com_carga) > 1:
                                segundo = itens_com_carga[1]
                                if not segundo['is_fechar']:
                                    falhas_r44.append(f"Etapa '{etapa_nome_real}': Segundo equipamento operado ({segundo['eq']}) deve FECHAR (MA02/MA66/MA67).")
                            else:
                                falhas_r44.append(f"Etapa '{etapa_nome_real}': Encontrado apenas 1 equipamento com carga, exige o segundo para FECHAR.")

                        # Coletar todas as macros presentes em toda a etapa por equipamento
                        macros_por_eq = {}
                        for mi in itens_etapa:
                            eq_k = _norm_eqpto(mi.get('equipamento', ''))
                            if eq_k:
                                if eq_k not in macros_por_eq:
                                    macros_por_eq[eq_k] = []
                                txt_line = (mi.get('acao_bruta', '') + " " + mi.get('texto_linha', '') + " " + mi.get('observacao', '')).upper()
                                macros_por_eq[eq_k].append(txt_line)
            
                        for item in itens_com_carga:
                            eq_nome = item['eq']
                            eq_k = _norm_eqpto(eq_nome)
                            is_tele = item['is_tele']
                            txt = item['txt']
                
                            txt_todas_eq = " ".join(macros_por_eq.get(eq_k, [txt]))
                            tem_ma27 = bool(re.search(r'\bMA27\b', txt_todas_eq))
                            tem_ma79 = bool(re.search(r'\bMA79\b', txt_todas_eq)) or ("CONFIRMAR EQUIPAMENTO COMUNICANDO" in txt_todas_eq)
                
                            if not is_tele:
                                if any(re.search(r'\b' + m + r'\b', txt) for m in ["MA01", "MA31", "MA02", "MA66"]):
                                    if not tem_ma27:
                                        falhas_r44.append(f"Etapa '{etapa_nome_real}': Equipamento manual '{eq_nome}' exige a macro MA27.")
                            else:
                                if item['is_fechar'] and any(re.search(r'\b' + m + r'\b', txt) for m in ["MA02", "MA66"]):
                                    if not tem_ma27:
                                        falhas_r44.append(f"Etapa '{etapa_nome_real}': Fechamento do equipamento telecontrolado '{eq_nome}' exige a macro MA27 antes do fechamento.")
                    
                                if not tem_ma79:
                                    falhas_r44.append(f"Etapa '{etapa_nome_real}': Equipamento telecontrolado '{eq_nome}' exige a macro MA79 antes da manobra.")

                if falhas_r44:
                    for f in set(falhas_r44): print_regra(44, "ERRO", f)
                elif etapas_pique:
                    print_regra(44, "OK", "Cabeçalho CP:xx, macros MA27/MA79 e sequência de Manobra com Pique validados com sucesso.")


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
                
                            # Se for COD + PARA REFLETIR -> ALERTA
                            if "COD" in executor and "PARA REFLETIR" in obs:
                                alertas_r43.append(f"Etapa '{et_nome}': Equipamento '{eq_id}' executado pelo COD com observação 'PARA REFLETIR'. Confirmar supervisor.")
                            else:
                                falhas_r43.append(f"Etapa '{et_nome}': Equipamento '{eq_id}' com executor '{executor}'. Exige executor 'SUPERVISOR'.")

                if falhas_r43:
                    for f in falhas_r43: print_regra(43, "ERRO", f)
                if alertas_r43:
                    for a in alertas_r43: print_regra(43, "ALERTA", a)
                if not falhas_r43 and not alertas_r43:
                    print_regra(43, "OK", "Todas as etapas de Desligamento/Religamento executadas pelo Supervisor conforme norma.")

                # REGRA 31.B (Validação de Sequência da Transferência de Carga - Tronco x Socorro)
                print("\n=== FASE: Validação de Sequência da Transferência de Carga (Regra 31.B) ===")
                falhas_r31b = []
                fechamentos_tensao = []
                aberturas_tensao = []
    
                limite_cronologia_desligamento = _obter_limite_pre_desligamento(manobra_dados)
                for mi in manobra_dados:
                    cron = mi.get('cronologia', 0)
                    eh_pre = (limite_cronologia_desligamento == -1) or (cron <= limite_cronologia_desligamento)
                    if not eh_pre:
                        continue
            
                    eq = mi.get('equipamento') or mi.get('numeq') or ''
                    if not eq:
                        continue
            
                    txt = mi.get('texto_linha', '').upper()
                    obs = mi.get('observacao', '').upper()
        
                    etapa_raw = mi.get('etapa_texto_header') or mi.get('etapa_nome') or mi.get('grupo_id') or 'Etapa'
                    m_etapa = re.search(r'(\d{2,3}\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ]+)', etapa_raw, re.IGNORECASE)
                    etapa_nome_limpo = m_etapa.group(1).title() if m_etapa else etapa_raw.strip()
        
                    is_sem_tensao = any(k in (txt + " " + obs) for k in ["SEM TENSÃO", "SEM TENSAO", "DESENERGIZADO"])
                    is_ab = bool(macros_abertura.search(txt) or re.search(r'\bABRIR\b', txt))
                    is_fe = bool(macros_fechamento.search(txt) or re.search(r'\bFECHAR\b', txt))
        
                    if not is_sem_tensao:
                        if is_fe:
                            fechamentos_tensao.append({'eq': eq, 'cron': cron, 'etapa': etapa_nome_limpo, 'mi': mi})
                        elif is_ab:
                            aberturas_tensao.append({'eq': eq, 'cron': cron, 'etapa': etapa_nome_limpo, 'mi': mi})

                if aberturas_tensao:
                    for ab in aberturas_tensao:
                        eq_ab = ab['eq']
                        cron_ab = ab['cron']
                        et_ab = ab['etapa']
            
                        is_solicitacao_boundary = any(_norm_eqpto(eq_ab) == _norm_eqpto(sol_eq) for sol_eq in sol_dict.keys())
                        if not is_solicitacao_boundary:
                            digits_ab = set(re.findall(r'\b\d{5,7}\b', eq_ab))
                            if digits_ab:
                                for sol_eq in sol_dict.keys():
                                    digits_sol = set(re.findall(r'\b\d{5,7}\b', sol_eq))
                                    if digits_ab & digits_sol:
                                        is_solicitacao_boundary = True
                                        break
                        if not is_solicitacao_boundary and any(m in txt for m in ["MAB6", "MA88", "MAB7", "MA90"]):
                            is_solicitacao_boundary = True
            
                        fechamentos_previos = [fe for fe in fechamentos_tensao if fe['cron'] <= cron_ab]
            
                        if not is_solicitacao_boundary:
                            if not fechamentos_previos:
                                fechamento_posterior = [fe for fe in fechamentos_tensao if fe['cron'] > cron_ab]
                                if fechamento_posterior:
                                    fe_post = fechamento_posterior[0]
                                    falhas_r31b.append(
                                        f"Sequência de transferência invertida no equipamento '{eq_ab}': ABERTURA realizada na {et_ab} (cronologia {cron_ab}) ANTES do FECHAMENTO do socorro '{fe_post['eq']}' na {fe_post['etapa']} (cronologia {fe_post['cron']}). Isso provoca pique/corte não programado de clientes."
                                    )
                                else:
                                    falhas_r31b.append(
                                        f"Equipamento de tronco '{eq_ab}' foi ABERTO com tensão na {et_ab} sem nenhum FECHAMENTO prévio de chave de socorro/interligação. Risco de desenergização indevida da carga."
                                    )

                if falhas_r31b:
                    for f in set(falhas_r31b):
                        print_regra(31, "ERRO", f"REGRA 31.B: {f}")
                else:
                    print_regra(31, "OK", "REGRA 31.B: Sequência cronológica da transferência de carga (Tronco x Socorro) validada com sucesso.")

                # REGRA 45 (Bloqueio de ST - MA15 em Religadores Trifásicos na Operação em Anel/Paralelo com Tensão)
                print("\n=== FASE: Proteção e Seletividade em Anel (Regra 45) ===")
                falhas_r45 = []
                religadores_trifasicos = set()
                ma15_religadores = set()
    
                # 1. Mapeia Religadores Trifásicos e presença de MA15
                for mi in manobra_dados:
                    eq = mi.get('equipamento') or mi.get('numeq') or ''
                    alim = mi.get('alim', '')
                    txt = mi.get('texto_linha', '').upper()
        
                    if eq:
                        eq_info = _get_eq_data(dados_equipamentos, eq, alim)
                        eq_prefixo = _obter_prefixo_equipamento(eq, eq_info)
                        eq_items = manobra_map.get(eq, [mi])
                        sol_info = sol_dict.get(eq, {})
                        fases = _obter_fases_equipamento(eq, eq_info, eq_items, sol_info)
            
                        txt_busca_mono = (
                            str(eq) + ' ' + 
                            str(eq_info) + ' ' + 
                            str(sol_info) + ' ' + 
                            ' '.join([
                                str(m_i.get('texto_linha', '')) + ' ' + 
                                str(m_i.get('observacao', '')) + ' ' + 
                                str(m_i.get('etapa_nome', '')) + ' ' + 
                                str(m_i.get('etapa_texto_header', '')) 
                                for m_i in eq_items
                            ])
                        ).upper()
            
                        is_mono = (fases in ['A', 'B', 'C']) or any(w in txt_busca_mono for w in [
                            'MONOFASICO', 'MONOFÁSICO', 'MONOFASICA', 'MONOFÁSICA', 'MONOFA', 'MONO', 
                            'UNIPOLAR', 'UNIP', 'FASE A', 'FASE B', 'FASE C', 'FASE-A', 'FASE-B', 'FASE-C', 
                            'FASEA', 'FASEB', 'FASEC', '1FASE', '1-FASE', '1 FASE', '1PH'
                        ])
            
                        if eq_prefixo == "22" and not is_mono:
                            religadores_trifasicos.add(eq)
        
                    if re.search(r'\b\d*MA15\b', txt) or "BLOQUEAR ST" in txt:
                        if eq:
                            ma15_religadores.add(eq)

                # 2. Verifica se há operação em anel/paralelo com tensão
                # Requer etapa de MANOBRA (não desligamento/técnico) com sequência Fechamento (MA02/MA66) + Abertura (MA01/MA31) com tensão
                tem_fechamento_tensao = False
                tem_abertura_tensao = False
                etapa_anel = ""

                for mi in manobra_dados:
                    et_nome = (mi.get('etapa_nome', '') + " " + mi.get('etapa_texto_header', '')).upper()
                    txt = mi.get('texto_linha', '').upper()
                    obs = mi.get('observacao', '').upper()
        
                    # Ignora etapas de Desligamento, Religamento, Preparação ou Manobra pelo Técnico
                    is_etapa_desligada = any(x in et_nome for x in ["DESLIGAMENTO", "RELIGAMENTO", "PREPARACAO", "PREPARAÇÃO", "TECNICO", "TÉCNICO", "SEM TENSÃO", "SEM TENSAO"])
                    is_linha_desligada = any(x in (txt + " " + obs) for x in ["SEM TENSÃO", "SEM TENSAO", "DESENERGIZADO"])
        
                    if not is_etapa_desligada and not is_linha_desligada:
                        # Fechamento com tensão em anel/paralelo/interligação
                        if (re.search(r'\b\d*(MA02|MA66)\b', txt) or "FECHAR EM PARALELO" in txt or "FECHAR EM ANEL" in txt) and any(k in (txt + " " + obs + " " + et_nome) for k in ["PARALELO COM TENSÃO", "FECHAR EM PARALELO", "LOOP DE TENSÃO", "ANEL COM TENSÃO"]):
                            tem_fechamento_tensao = True
                            if not etapa_anel: etapa_anel = mi.get('etapa_nome', 'Itens')
            
                        # Abertura com tensão
                        if (re.search(r'\b\d*(MA01|MA31)\b', txt) or "ABRIR" in txt) and not any(k in (txt + " " + obs) for k in ["SEM TENSÃO", "SEM TENSAO"]):
                            tem_abertura_tensao = True

                operacao_anel_com_tensao = tem_fechamento_tensao and tem_abertura_tensao

                if operacao_anel_com_tensao and religadores_trifasicos:
                    for r_eq in religadores_trifasicos:
                        if r_eq not in ma15_religadores:
                            falhas_r45.append(f"Etapa '{etapa_anel}': Operação em anel/paralelo com tensão exige bloqueio prévio de ST (MA15) no Religador Trifásico '{r_eq}'. Insira a macro MA15.")

                if falhas_r45:
                    for f in set(falhas_r45): print_regra(45, "ERRO", f)
                elif operacao_anel_com_tensao and religadores_trifasicos:
                    print_regra(45, "OK", "Bloqueio de ST (MA15) validado em todos os religadores trifásicos envolvidos na operação em anel com tensão.")
                else:
                    print_regra(45, "OK", "Operação em anel/paralelo com tensão não identificada ou sem restrições de ST.")

                # ============================================================
                # FIM DA VERIFICAÇÃO
                # ============================================================

                print("\n" + f"{Colors.GREEN}{Colors.BOLD}" + "="*57)
                print(f"   VERIFICAÇÃO DA MANOBRA {manobra_num} CONCLUÍDA COM SUCESSO!   ")
                print("="*57 + f"{Colors.RESET}")
            except Exception as e_manobra:
                print(f"\n❌ [ERRO NO PROCESSAMENTO DA MANOBRA {manobra_num}]: {e_manobra}")
                try:
                    page.goto(URL_LOGIN)
                    page.wait_for_timeout(1000)
                except Exception:
                    pass
            finally:
                print(f"\n>>> MANOBRA_END: {manobra_num}\n")
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
    print("      LOTE DE MANOBRAS CONCLUÍDO COM SUCESSO!         ")
    print("="*57 + f"{Colors.RESET}")
    
    if not manobra_param:
        input("\nPressione Enter para encerrar...")

if __name__ == "__main__":
    main()