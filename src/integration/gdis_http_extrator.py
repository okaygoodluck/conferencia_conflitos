import getpass
import html
import os
import re
import urllib.parse
import urllib.error
import urllib.request
import time
from http.cookiejar import CookieJar


BASE_URL = "http://gdis-pm/gdispm"
# IP do servidor para fallback em caso de falha DNS (Errno 11001)
SERVER_IP = "10.30.41.140"

URL_HOME = f"{BASE_URL}/"
URL_LOGIN = f"{BASE_URL}/login.jsf"
URL_MANOBRA = f"{BASE_URL}/pages/manobra/manobraGeral.jsf"

# DATA_INICIO e DATA_FIM foram removidos como variáveis globais para permitir execução multithread segura.
# Devem ser passados como argumentos para as funções que os utilizam.

def _http_timeout():
    try:
        return float((os.getenv("GDIS_HTTP_TIMEOUT") or "60").strip())
    except:
        return 60.0


def _norm(s):
    return re.sub(r"\s+", " ", (s or "")).strip()


def _extract_viewstate(text):
    matches = re.findall(
        r'name="javax\.faces\.ViewState"[^>]*value="([^"]+)"',
        text or "",
        flags=re.IGNORECASE,
    )
    if matches:
        return matches[-1]
    matches = re.findall(
        r'id="javax\.faces\.ViewState"[^>]*value="([^"]+)"',
        text or "",
        flags=re.IGNORECASE,
    )
    if matches:
        return matches[-1]
    return None


def _extract_jsessionid_from_html(text):
    m = re.search(r";jsessionid=([A-Z0-9\.]+)", text or "", flags=re.IGNORECASE)
    return m.group(1) if m else None

def _extract_form_fields(html_text, form_id):
    """Extrai todos os campos (input e select) de um formulário JSF/RichFaces."""
    fields = {}
    # Localiza o formulário específico
    form_pattern = r'<form[^>]+id="' + re.escape(form_id) + r'"[\s\S]*?</form>'
    form_match = re.search(form_pattern, html_text, re.IGNORECASE)
    if not form_match: return fields
    
    form_content = form_match.group(0)
    
    # Busca inputs
    for input_tag in re.findall(r'<input[^>]+>', form_content):
        name_match = re.search(r'name="([^"]+)"', input_tag)
        if name_match:
            name = name_match.group(1)
            value_match = re.search(r'value="([^"]*)"', input_tag)
            value = value_match.group(1) if value_match else ""
            fields[name] = value
            
    # Busca selects
    select_matches = re.findall(r'<select[^>]+name="([^"]+)"([\s\S]*?)</select>', form_content)
    for name, select_content in select_matches:
        opt_match = re.search(r'<option[^>]+value="([^"]+)"[^>]*selected="selected"', select_content)
        if not opt_match:
            opt_match = re.search(r'<option[^>]+value="([^"]+)"', select_content)
        fields[name] = opt_match.group(1) if opt_match else ""
        
    return fields


def _strip_tags(s):
    return _norm(re.sub(r"<[^>]+>", "", html.unescape(s or "")))


def _is_login_page(html_text):
    t = html_text or ""
    return ("id=\"formLogin:userid\"" in t) or ("<form id=\"formLogin\"" in t) or ("name=\"formLogin\"" in t)


def _is_manobra_page(html_text):
    t = html_text or ""
    return ("id=\"formPesquisa\"" in t) and ("Consultar Manobras" in t or "consultaManobras2" in t)


def _post(opener, url, data, headers=None):
    encoded = urllib.parse.urlencode(data, doseq=True).encode("utf-8")
    req = urllib.request.Request(url, data=encoded, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    req.add_header("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
    req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36")
    req.add_header("X-Requested-With", "XMLHttpRequest")
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
            
    try:
        with opener.open(req, timeout=_http_timeout()) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as e:
        # Se for erro de DNS (11001) e estivermos usando o hostname, tenta via IP
        if "11001" in str(e) and "gdis-pm" in url:
            new_url = url.replace("gdis-pm.cemig.ad.corp", SERVER_IP).replace("gdis-pm", SERVER_IP)
            req_ip = urllib.request.Request(new_url, data=encoded, method="POST")
            for k, v in req.headers.items(): req_ip.add_header(k, v)
            req_ip.add_header("Host", "gdis-pm") # Preserva o Host header para o JBoss
            with opener.open(req_ip, timeout=_http_timeout()) as resp:
                return resp.read().decode("utf-8", errors="replace")
        raise


def _get(opener, url, headers=None):
    req = urllib.request.Request(url, method="GET")
    req.add_header("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
    req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36")
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
            
    try:
        with opener.open(req, timeout=_http_timeout()) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as e:
        if "11001" in str(e) and "gdis-pm" in url:
            new_url = url.replace("gdis-pm.cemig.ad.corp", SERVER_IP).replace("gdis-pm", SERVER_IP)
            req_ip = urllib.request.Request(new_url, method="GET")
            for k, v in req.headers.items(): req_ip.add_header(k, v)
            req_ip.add_header("Host", "gdis-pm")
            with opener.open(req_ip, timeout=_http_timeout()) as resp:
                return resp.read().decode("utf-8", errors="replace")
        raise


def _find_manobra_links(html_text):
    out = []
    for m in re.finditer(
        r'<a[^>]+id="([^"]+)"[^>]+name="([^"]+)"[^>]*>(\d{9})<',
        html_text or "",
        flags=re.IGNORECASE,
    ):
        anchor_id, anchor_name, numero = m.group(1), m.group(2), m.group(3)
        out.append((numero, anchor_id, anchor_name))
    return out


def _extract_active_page(html_text):
    m = re.search(r'rich-datascr-act[^>]*>\s*(\d+)\s*<', html_text or "", flags=re.IGNORECASE)
    if not m:
        return None
    try:
        return int(m.group(1))
    except:
        return None


def _parse_itens_tables(html_text):
    eqptos = set()
    alim = set()
    # No GDIS, as tabelas podem ter IDs variados dependendo se é Solicitação pura ou via Manobra
    # Exemplos: 'formPesquisa:itensCadastrados', 'j_id338:eqpsList', 'j_id299:documentosList'
    # DEBUG: Logar todos os IDs de tabela para encontrar o correto se falhar
    # all_tables = re.findall(r'<table[^>]+id="([^"]+)"', html_text or "", re.I)
    # if all_tables:
    #     print(f"[{time.strftime('%H:%M:%S')}] DEBUG GDIS: Tabelas encontradas: {', '.join(all_tables[:10])}")

    for t in re.finditer(
        r'<table[^>]+id="([^"]*(?::itensCadastrados|:eqpsList|:solicitacaoList|:listaEquipamentos|:idTabelaItens|statusModalContentTable|etapasCadastradas))"[^>]*>([\s\S]*?)</table>',
        html_text or "",
        flags=re.IGNORECASE,
    ):
        table_html = t.group(2)
        ths = re.findall(r"<th[^>]*>([\s\S]*?)</th>", table_html, flags=re.IGNORECASE)
        headers = [_strip_tags(x).lower() for x in ths]
        # Prioridade para nomes de colunas que são claramente equipamentos
        eq_keywords_high = ["equip", "eqp", "trafo", "transformador"]
        eq_keywords_low = ["número", "númer", "numer", "nº", "código", "codigo"]
        
        idx_eq = next((i for i, h in enumerate(headers) if any(k in h for k in eq_keywords_high)), -1)
        if idx_eq < 0:
            idx_eq = next((i for i, h in enumerate(headers) if any(k in h for k in eq_keywords_low)), -1)
        
        # Alimentador pode ser 'Alimentador', 'Subestação', 'Alim.' ou 'Sub.'
        idx_al = next((i for i, h in enumerate(headers) if any(k in h for k in ["alimen", "subes", "alim", "sub"])), -1)
        if idx_eq < 0 and idx_al < 0:
            continue
        tbody_m = re.search(r"<tbody[^>]*>([\s\S]*?)</tbody>", table_html, flags=re.IGNORECASE)
        tbody = tbody_m.group(1) if tbody_m else table_html
        for rm in re.finditer(r"<tr[^>]*>([\s\S]*?)</tr>", tbody, flags=re.IGNORECASE):
            row_html = rm.group(1)
            tds = re.findall(r"<td[^>]*>([\s\S]*?)</td>", row_html, flags=re.IGNORECASE)
            if idx_eq >= 0 and len(tds) > idx_eq:
                v = _strip_tags(tds[idx_eq]).strip()
                if v and v != "-" and v != " - ":
                    # Falso positivo: colunas como 'Número' ou 'Nº' contendo índices da tabela (10, 20, 30) ou o texto 'Etapa: 10'
                    if not re.fullmatch(r"\d{1,3}", v) and not v.lower().startswith("etapa"):
                        eqptos.add(v)
            if idx_al >= 0 and len(tds) > idx_al:
                v = _strip_tags(tds[idx_al])
                if v and v != "-" and v != " - ":
                    alim.add(v)
    return sorted(eqptos), sorted(alim)

# --- Novos auxiliares de extração robusta ---

def _parse_eventos(html_text):
    """Extrai equipamentos e alimentadores da sequência de eventos do GDIS."""
    eq = set()
    al = set()
    txt = html_text or ""
    # Padrão capturado por tags explícitas
    for m in re.finditer(r"\[EQP:\s*([^\]]+)\]", txt):
        eq.add(m.group(1).strip())
    for m in re.finditer(r"\[ALIM:\s*([^\]]+)\]", txt):
        al.add(m.group(1).strip())
    
    # Fallback para menções diretas em texto (caso não usem as tags [])
    # Ex: "EQUIPAMENTO: 24-12345" ou "OPERAR EQPTO 24-12345" ou "TRAFO 62326-3-75"
    # Padrão Transformador: XXXXX-X-XXX (ex: 62326-3-75)
    trafo_regex = r"\d{4,8}\s*-\s*\d+\s*-\s*\d+"
    classico_regex = r"\d{2}\s*-\s*\d{5,8}"
    combined_regex = f"(?:{classico_regex}|{trafo_regex})"
    
    for m in re.finditer(r"(?:EQUIPAMENTO|EQPTO|EQP|CÓDIGO|CODIGO|TRAFO|TRANSFORMADOR)\s*[:\-]?\s*(" + combined_regex + ")", txt, re.IGNORECASE):
        eq.add(m.group(1).strip())
        
    return sorted(eq), sorted(al)

def _super_fallback_equipamentos(html_text):
    """Busca agressiva por padrões de equipamentos no HTML bruto se nada for achado."""
    eqpts = set()
    # Padrão GDIS clássico: "24-12345" ou "24 - 12345"
    # Padrão Transformador: "62326 - 3 - 75" ou "254366 - 3 - 150"
    trafo_regex = r"\d{4,8}\s*-\s*\d+\s*-\s*\d+"
    classico_regex = r"\d{2}\s*-\s*\d{5,8}"
    
    for m in re.finditer(r"\b(" + classico_regex + "|" + trafo_regex + r")\b", html_text or ""):
        eqpts.add(m.group(1).strip())
    return sorted(eqpts)


def _parse_datas(html_text):
    """Extrai Data de Início e Data de Término do HTML com foco no painel principal e tabelas."""
    # Lista de IDs que representam tabelas de eventos ou históricos a serem ignoradas
    blacklist_ids = ["eventosList", "historico", "scroller", "j_id181"]
    
    # Pré-filtra o HTML para focar nos containers de 'Negócio' (execução)
    # Procuramos primeiro no painel de elaboração, que é o mais confiável
    elaboracao_pattern = r'<div[^>]+id="[^"]*(?:tooglePanelElaboracaoManobra|panelPrincipal)[^"]*"[^>]*>([\s\S]*?)</div>\s*(?:<div|<!--)'
    m_elaboracao = re.search(elaboracao_pattern, html_text, re.I)
    
    # Se não achou no painel específico, tenta containers maiores, mas excluindo eventos se possível
    main_ids = ["formPrincipal", "statusModalContentTable", "etapasItensForm", "tooglePanelSolicitacao"]
    main_pattern = r'<div[^>]+id="(?:' + "|".join(main_ids) + r')[^"]*"[^>]*>([\s\S]*?)</div>\s*(?:<div|<!--|<form)'
    m_main = re.search(main_pattern, html_text, re.I)
    
    # Ordem de preferência: Elaboração > Geral > Full HTML
    search_areas = []
    if m_elaboracao: search_areas.append(m_elaboracao.group(1))
    if m_main: search_areas.append(m_main.group(1))
    search_areas.append(html_text)
    
    d_ini = ""
    d_fim = ""
    date_regex = r"(\d{2}/\d{2}/\d{4}(?:\s+\d{2}:\d{2})?)"

    # Estratégia 1: Busca baseada nos rótulos específicos em áreas prioritárias
    labels_ini = [r"Data\s+(?:de\s+)?In[íi]cio", r"In[íi]cio"]
    labels_fim = [r"Data\s+(?:de\s+)?T[ée]rmino", r"T[ée]rmino"]

    for area in search_areas:
        for labels, target in [(labels_ini, "d_ini"), (labels_fim, "d_fim")]:
            current_val = d_ini if target == "d_ini" else d_fim
            if current_val: continue
            
            for label in labels:
                pattern = label + r"[:]?[\s\S]{1,500}?" + date_regex
                m = re.search(pattern, area, re.I)
                if m:
                    val = m.group(1).strip()
                    if target == "d_ini": d_ini = val
                    else: d_fim = val
                    if val: break
        if d_ini and d_fim: break

    # Estratégia 2: Busca direta por IDs de input (JSF rendering)
    if not d_ini:
        m_id_ini = re.search(r'id="[^"]*dataInicioInputDate"[^>]*value="([^"]+)"', html_text, re.I)
        if m_id_ini: d_ini = m_id_ini.group(1).strip()
    if not d_fim:
        m_id_fim = re.search(r'id="[^"]*(?:dataFimInputDate|dataTerminioInputDate)"[^>]*value="([^"]+)"', html_text, re.I)
        if m_id_fim: d_fim = m_id_fim.group(1).strip()

    # Estratégia 3: Raspagem de tabelas (Fallback agressivo, mas filtrado)
    if not d_ini or not d_fim:
        # Busca todas as tabelas e tenta encontrar colunas de data
        table_matches = re.finditer(r'<table([^>]*)>([\s\S]*?)</table>', html_text, re.I)
        all_found_dates = []
        
        for tm in table_matches:
            table_attrs = tm.group(1)
            table_html = tm.group(2)
            
            # Pula tabelas na blacklist
            if any(bid in table_attrs for bid in blacklist_ids):
                continue
                
            ths = re.findall(r"<th[^>]*>([\s\S]*?)</th>", table_html, re.I)
            headers = [_strip_tags(h).lower() for h in ths]
            
            # Identifica colunas de data (Início/Término/Prazo são mais confiáveis que apenas 'Data')
            idxs = [i for i, h in enumerate(headers) if any(k in h for k in ["início", "término", "inicio", "termino", "prazo", "data"])]
            if not idxs: continue
            
            # Extrai datas de todas as linhas
            for row in re.finditer(r"<tr[^>]*>([\s\S]*?)</tr>", table_html, re.I):
                row_html = row.group(1)
                
                # IGNORA linhas que parecem ser de histórico ou cadastro (Ex: Manobra Cadastrada)
                row_text = _strip_tags(row_html).lower()
                if any(k in row_text for k in ["cadastrada", "criada", "log", "histórico", "historico", "emissão"]):
                    continue
                    
                tds = re.findall(r"<td[^>]*>([\s\S]*?)</td>", row_html, re.I)
                for idx in idxs:
                    if idx < len(tds):
                        val = _strip_tags(tds[idx])
                        m_date = re.search(date_regex, val)
                        if m_date:
                            all_found_dates.append(m_date.group(1).strip())
        
        if all_found_dates:
            def to_sortable(d):
                try:
                    d_part = d.split()[0]
                    day, month, year = d_part.split('/')
                    return f"{year}-{month}-{day}"
                except: return "9999-99-99"
            
            sorted_dates = sorted(all_found_dates, key=to_sortable)
            if not d_ini: d_ini = sorted_dates[0]
            if not d_fim: d_fim = sorted_dates[-1]

    # Limpeza final
    if d_ini and " " in d_ini: d_ini = d_ini.split()[0]
    if d_fim and " " in d_fim: d_fim = d_fim.split()[0]

    return d_ini, d_fim


def _login(opener, usuario, senha):
    html_login = _get(opener, URL_HOME)
    jsessionid = _extract_jsessionid_from_html(html_login)
    viewstate = _extract_viewstate(html_login) or "j_id1"
    action = URL_LOGIN
    if jsessionid:
        action = f"{URL_LOGIN};jsessionid={jsessionid}"

    resp = _post(
        opener,
        action,
        {
            "AJAXREQUEST": "_viewRoot",
            "formLogin": "formLogin",
            "autoScroll": "",
            "formLogin:userid": usuario,
            "formLogin:password": senha,
            "formLogin:botao": "formLogin:botao",
            "javax.faces.ViewState": viewstate,
        },
    )
    if _is_login_page(resp):
        raise ValueError("Login inválido (usuário/senha incorretos ou sessão não criada).")
    new_vs = _extract_viewstate(resp) or viewstate
    return jsessionid, new_vs


def _open_manobra_page(opener, jsessionid):
    url = URL_MANOBRA
    if jsessionid:
        url = f"{URL_MANOBRA};jsessionid={jsessionid}"
    html_page = _get(opener, url)
    if _is_login_page(html_page) or not _is_manobra_page(html_page):
        raise ValueError("Sessão não autenticada ao abrir Manobra (login expirou ou falhou).")
    return html_page, _extract_viewstate(html_page)


def _pesquisar(opener, jsessionid, viewstate, situacao, malha=None, numero_manobra=None, data_inicio=None, data_fim=None, numero_solicitacao=None):
    url = URL_MANOBRA
    if jsessionid:
        url = f"{URL_MANOBRA};jsessionid={jsessionid}"
    payload = {
        "AJAXREQUEST": "_viewRoot",
        "formPesquisa": "formPesquisa",
        "autoScroll": "",
        "formPesquisa:consultaManobras2": "true",
        "formPesquisa:numeroManobra": numero_manobra or "",
        "formPesquisa:numeroSolicitacao": numero_solicitacao or "",
        "formPesquisa:numeroManobraCondis": "",
        "formPesquisa:dataInicioInputDate": data_inicio or "",
        "formPesquisa:dataTerminioInputDate": data_fim or "",
        "formPesquisa:situacao": situacao or "",
        "formPesquisa:malha": malha or "",
        "formPesquisa:area": "",
        "formPesquisa:contratada": "",
        "formPesquisa:grupoCausa": "02",
        "formPesquisa:tipoCausa": "",
        "formPesquisa:urgenciaPesquisa": "",
        "formPesquisa:projeto": "",
        "formPesquisa:usuElaboracao": "",
        "formPesquisa:solicitantePesquisa": "",
        "formPesquisa:j_id109": "formPesquisa:j_id109",
        "javax.faces.ViewState": viewstate or "",
    }
    try:
        resp = _post(opener, url, payload)
        new_vs = _extract_viewstate(resp) or viewstate
        return resp, new_vs
    except urllib.error.HTTPError as e:
        if e.code != 500:
            raise
        _, fresh_vs = _open_manobra_page(opener, jsessionid)
        payload["javax.faces.ViewState"] = fresh_vs or viewstate or ""
        resp = _post(opener, url, payload)
        new_vs = _extract_viewstate(resp) or fresh_vs or viewstate
        return resp, new_vs


def _datascroller_page(opener, jsessionid, viewstate, page_value):
    url = URL_MANOBRA
    if jsessionid:
        url = f"{URL_MANOBRA};jsessionid={jsessionid}"
    payload = {
        "AJAXREQUEST": "_viewRoot",
        "formManobra": "formManobra",
        "autoScroll": "",
        "ajaxSingle": "formManobra:resulPesManobraScroll",
        "formManobra:resulPesManobraScroll": str(page_value),
        "javax.faces.ViewState": viewstate or "",
    }
    try:
        resp = _post(opener, url, payload)
        new_vs = _extract_viewstate(resp) or viewstate
        return resp, new_vs
    except urllib.error.HTTPError as e:
        if e.code != 500:
            raise
        _, fresh_vs = _open_manobra_page(opener, jsessionid)
        payload["javax.faces.ViewState"] = fresh_vs or viewstate or ""
        resp = _post(opener, url, payload)
        new_vs = _extract_viewstate(resp) or fresh_vs or viewstate
        return resp, new_vs


def _abrir_detalhe(opener, jsessionid, viewstate, anchor_id, id_manobra_param):
    url = URL_MANOBRA
    if jsessionid:
        url = f"{URL_MANOBRA};jsessionid={jsessionid}"
    payload = {
        "AJAXREQUEST": "_viewRoot",
        "formManobra": "formManobra",
        "autoScroll": "",
        "idManobraParam": str(id_manobra_param),
        anchor_id: anchor_id,
        "javax.faces.ViewState": viewstate or "",
    }
    try:
        resp = _post(opener, url, payload)
        return resp
    except urllib.error.HTTPError as e:
        if e.code != 500:
            raise
        _, fresh_vs = _open_manobra_page(opener, jsessionid)
        payload["javax.faces.ViewState"] = fresh_vs or viewstate or ""
        resp = _post(opener, url, payload)
        return resp


def coletar_manobras(opener, jsessionid, viewstate, situacao, data_inicio, data_fim, malha=None):
    """
    Coleta todas as manobras para uma determinada situação, lidando com paginação.
    Esta função agora é autônoma e sempre inicia a partir de um estado limpo
    para garantir que a pesquisa não seja contaminada por estados anteriores.
    """
    try:
        _, fresh_vs = _open_manobra_page(opener, jsessionid)
    except Exception as e:
        raise RuntimeError(f"Falha ao recarregar a página de manobras antes da coleta: {e}")

    try:
        resp, vs = _pesquisar(opener, jsessionid, fresh_vs, situacao, malha=malha, data_inicio=data_inicio, data_fim=data_fim)
    except Exception as e:
        raise RuntimeError(f"Falha ao pesquisar manobras para situação '{situacao}' e malha '{malha}': {e}")

    ids = set(x[0] for x in _find_manobra_links(resp))
    if not ids:
        return [], vs

    for page in range(2, 501): 
        advanced = False
        for attempt in range(3):
            try:
                resp2, vs = _datascroller_page(opener, jsessionid, vs, page)
                page_ids = set(x[0] for x in _find_manobra_links(resp2))
                active_page_after_scroll = _extract_active_page(resp2)
                if not page_ids or (active_page_after_scroll and active_page_after_scroll < page):
                    advanced = False 
                    break 

                if page_ids - ids:
                    ids.update(page_ids)
                    advanced = True 
                    break 
                else: 
                    advanced = False
                    break

            except urllib.error.HTTPError as e:
                if e.code != 500: raise
                _, vs = _open_manobra_page(opener, jsessionid)
        
        if not advanced:
            break

    return sorted(ids), vs


def extrair_uma_manobra(opener, jsessionid, viewstate, numero, malha="", data_inicio="", data_fim=""):
    try:
        _, fresh_vs = _open_manobra_page(opener, jsessionid)
    except Exception as e:
        raise RuntimeError(f"Falha ao recarregar a página de manobras para extrair a manobra {numero}: {e}")

    resp, vs = _pesquisar(opener, jsessionid, fresh_vs, situacao="", malha=malha, numero_manobra=numero, data_inicio=data_inicio, data_fim=data_fim)
    links = _find_manobra_links(resp)
    
    if not any(x[0] == str(numero) for x in links):
        try:
            _, fresh_vs2 = _open_manobra_page(opener, jsessionid)
            resp, vs = _pesquisar(opener, jsessionid, fresh_vs2, situacao="", malha="", numero_manobra=numero, data_inicio="01/01/2020", data_fim="31/12/2035")
            links = _find_manobra_links(resp)
        except Exception:
            pass 

    link = next((x for x in links if x[0] == str(numero)), None)
    if not link:
        return [], [], vs, "", ""
    _, anchor_id, _ = link
    detalhe = _abrir_detalhe(opener, jsessionid, vs, anchor_id, numero)
    eq1, al1 = _parse_itens_tables(detalhe)
    eq2, al2 = _parse_eventos(detalhe)
    eq = sorted(set(eq1) | set(eq2))
    al = sorted(set(al1) | set(al2))

    eq3 = _super_fallback_equipamentos(detalhe)
    eq = sorted(set(eq) | set(eq3))

    d_ini, d_fim = _parse_datas(detalhe)
    return eq, al, vs, d_ini, d_fim




def main():
    usuario = (os.getenv("GDIS_USUARIO") or "").strip() or input("Usuário: ").strip()
    senha = (os.getenv("GDIS_SENHA") or "").strip() or getpass.getpass("Senha: ")

    jar = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    try:
        jsessionid, _ = _login(opener, usuario, senha)
        _, vs = _open_manobra_page(opener, jsessionid)
    except ValueError as e:
        print(str(e))
        return

    print("Coletando manobras 'Em Elaboração' (EB)...")
    elaborada, vs = coletar_manobras(opener, jsessionid, vs, "EB", "", "")
    print("Coletando manobras 'Enviadas' (EN)...")
    enviada, vs = coletar_manobras(opener, jsessionid, vs, "EN", "", "")
    print("Coletando manobras 'Autorizadas/Aprovadas' (EA)...")
    aprovada, vs = coletar_manobras(opener, jsessionid, vs, "EA", "", "")
    print("Coletando manobras 'Concluídas' (CO)...")
    concluida, vs = coletar_manobras(opener, jsessionid, vs, "CO", "", "")

    todos = sorted(set(elaborada) | set(enviada) | set(aprovada) | set(concluida))
    print("\n--- TOTAIS ---")
    print(f"TOTAL EB: {len(elaborada)}")
    print(f"TOTAL EN: {len(enviada)}")
    print(f"TOTAL EA: {len(aprovada)}")
    print(f"TOTAL CO: {len(concluida)}")
    print(f"TOTAL ÚNICO: {len(todos)}")
    print("----------------\n")

    for numero in todos:
        eq, al, vs, d_ini, d_fim = extrair_uma_manobra(opener, jsessionid, vs, numero)
        print(f"MANOBRA {numero} ({d_ini} a {d_fim})")
        print(f"  Equipamentos: {'; '.join(eq) if eq else '-'}")
        print(f"  Alimentadores/Subestações: {'; '.join(al) if al else '-'}")


if __name__ == "__main__":
    main()
