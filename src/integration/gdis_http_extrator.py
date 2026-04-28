import getpass
import html
import os
import re
import urllib.parse
import urllib.error
import urllib.request
import time
import socket
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


def _open_solicitacao_page(opener, jsessionid):
    urls = [
        f"{BASE_URL}/pages/solicitacao/pesquisaSolicitacao.jsf",
        f"{BASE_URL}/pages/solicitacao/detalhasolicitacao.jsf",
        f"{BASE_URL}/paginas/solicitacao/pesquisaSolicitacao.jsf",
        f"{BASE_URL}/paginas/solicitacao/detalhasolicitacao.jsf"
    ]
    
    last_error = None
    for url in urls:
        # print(f"[{time.strftime('%H:%M:%S')}] DEBUG GDIS: Tentando abrir: {url}")
        try:
            html_page = _get(opener, url)
            return html_page, _extract_viewstate(html_page), url
        except urllib.error.HTTPError as e:
            if e.code == 404:
                last_error = e
                continue 
            raise
            
    if last_error:
        raise last_error

def _pesquisar_solicitacao(opener, jsessionid, viewstate, numero=None, situacao=None, malha=None, data_inicio=None, data_fim=None, url=None, html_content=None):
    """
    Submete pesquisa de solicitação com payload extraído e filtros.
    Versão robusta seguindo o padrão da pesquisa de manobras.
    """
    actual_url = url or URL_PESQUISA_SOLICITACAO
    if jsessionid and ";jsessionid=" not in actual_url:
        actual_url = f"{actual_url};jsessionid={jsessionid}"
        
    # Se o conteúdo HTML da página não foi passado, busca agora para extrair ViewState e campos default
    if not html_content:
        html_content = _get(opener, actual_url)
        
    fields = _extract_form_fields(html_content, "formPesquisa")
    
    # Preenchimento de Filtros (IDs reais capturados via Browser)
    fields['AJAXREQUEST'] = '_viewRoot'
    fields['formPesquisa:solicitacao'] = str(numero) if numero else ""
    fields['formPesquisa:j_id52'] = 'true' # Flag crucial de ativação
    fields['formPesquisa:dataInicioPesquisaInputDate'] = data_inicio or ""
    fields['formPesquisa:dataFimPesquisaInputDate'] = data_fim or ""
    
    # Flags adicionais presentes no payload real
    fields['formPesquisa:consultaManobras2'] = "true" 
    
    # ViewState obrigatório do formulário específico
    fields['javax.faces.ViewState'] = viewstate or _extract_viewstate(html_content) or ""
    
    # Botão de pesquisa
    btn_id = "formPesquisa:j_id108"
    fields[btn_id] = btn_id
    fields['formPesquisa'] = 'formPesquisa'
    
    # Remover campos de eventos se existirem (para evitar confusão do JSF)
    if "AJAX:EVENTS_COUNT" in fields: del fields["AJAX:EVENTS_COUNT"]
        
    headers = {
        "Referer": actual_url,
        "X-Requested-With": "XMLHttpRequest",
        "Faces-Request": "partial/ajax"
    }
    
    try:
        resp = _post(opener, actual_url, fields, headers=headers)
        new_vs = _extract_viewstate(resp) or fields.get('javax.faces.ViewState')
        return resp, new_vs
    except urllib.error.HTTPError as e:
        if e.code != 500: raise
        # AUTO-RECOVERY: Se der 500 (sessão/viewstate expirado), recarrega a página e tenta de novo uma vez
        # print(f"[{time.strftime('%H:%M:%S')}] DEBUG GDIS: Erro 500 na pesquisa de solicitação. Tentando recuperar...")
        fresh_html, fresh_vs, _ = _open_solicitacao_page_simple(opener, actual_url)
        fields["javax.faces.ViewState"] = fresh_vs or viewstate or ""
        resp = _post(opener, actual_url, fields, headers=headers)
        return resp, _extract_viewstate(resp) or fresh_vs

def _datascroller_page_solicitacao(opener, jsessionid, viewstate, page_value, url=None):
    """Lida com a paginação na tela de resultados de solicitações."""
    actual_url = url or URL_PESQUISA_SOLICITACAO
    if jsessionid and ";jsessionid=" not in actual_url:
        actual_url = f"{actual_url};jsessionid={jsessionid}"
        
    payload = {
        "AJAXREQUEST": "_viewRoot",
        "formPesquisa": "formPesquisa",
        "autoScroll": "",
        "ajaxSingle": "formPesquisa:resulPesqSolicitacaoScroll",
        "formPesquisa:resulPesqSolicitacaoScroll": str(page_value),
        "javax.faces.ViewState": viewstate or "",
    }
    try:
        resp = _post(opener, actual_url, payload)
        new_vs = _extract_viewstate(resp) or viewstate
        return resp, new_vs
    except urllib.error.HTTPError as e:
        if e.code != 500: raise
        _, fresh_vs, _ = _open_solicitacao_page_simple(opener, actual_url)
        payload["javax.faces.ViewState"] = fresh_vs or viewstate or ""
        resp = _post(opener, actual_url, payload)
        return resp, _extract_viewstate(resp) or fresh_vs

def _open_solicitacao_page_simple(opener, url):
    html_page = _get(opener, url)
    return html_page, _extract_viewstate(html_page), url

def coletar_solicitacoes(opener, jsessionid, viewstate, situacao, data_inicio, data_fim, malha=None):
    """
    Coleta todas as solicitações para uma determinada situação e período.
    Espelha a lógica de coletar_manobras.
    """
    url_alvo = URL_PESQUISA_SOLICITACAO
    try:
        init_html, fresh_vs, _ = _open_solicitacao_page_simple(opener, url_alvo)
    except Exception as e:
        raise RuntimeError(f"Falha ao abrir página de solicitações: {e}")

    try:
        resp, vs = _pesquisar_solicitacao(opener, jsessionid, fresh_vs, 
                                        situacao=situacao, malha=malha, 
                                        data_inicio=data_inicio, data_fim=data_fim, 
                                        url=url_alvo, html_content=init_html)
    except Exception as e:
        raise RuntimeError(f"Falha na pesquisa inicial de solicitações: {e}")

    # find_sol_links deve ser capaz de extrair os números das solicitações nos resultados
    # Reutilizaremos ou adaptaremos a regex de manobra
    def _extract_ids(h):
        return set(m.group(3) for m in re.finditer(r'<a[^>]+id="([^"]+)"[^>]+name="([^"]+)"[^>]*>(\d{5,9})<', h or "", re.I))

    ids = _extract_ids(resp)
    if not ids:
        return [], vs

    # Loop de Paginação (Até 500 páginas como segurança)
    for page in range(2, 501):
        try:
            resp2, vs = _datascroller_page_solicitacao(opener, jsessionid, vs, page, url=url_alvo)
            page_ids = _extract_ids(resp2)
            active_page = _extract_active_page(resp2)
            
            if not page_ids or (active_page and active_page < page):
                break
                
            new_ids = page_ids - ids
            if not new_ids:
                break # Nenhuma novidade nesta página
                
            ids.update(page_ids)
        except Exception as e:
            print(f"[{time.strftime('%H:%M:%S')}] AVISO: Falha ao paginar solicitações (página {page}): {e}")
            break

    return sorted(list(ids)), vs

def _abrir_detalhe_solicitacao(opener, jsessionid, viewstate, anchor_id, numero, url, form_id="formList", param_id="idSolicitacaoManobra"):
    payload = {
        "AJAXREQUEST": "_viewRoot",
        form_id: form_id,
        "autoScroll": "",
        param_id: str(numero),
        anchor_id: anchor_id,
        "javax.faces.ViewState": viewstate or "",
    }
    
    try:
        resp = _post(opener, url, payload)
        # Se for um redirecionamento AJAX do JSF
        m_redir = re.search(r'<redirect url="([^"]+)"', resp)
        if m_redir:
            redir_url = m_redir.group(1).replace("&amp;", "&")
            if redir_url.startswith("/"):
                # Se for caminho relativo, reconstrói baseado na raiz do GDIS
                m_base = re.match(r"(https?://[^/]+)", url)
                base = m_base.group(1) if m_base else BASE_URL
                redir_url = base + redir_url
            # print(f"[{time.strftime('%H:%M:%S')}] DEBUG GDIS: Redirecionamento AJAX detectado para: {redir_url}")
            resp = _get(opener, redir_url)
            
        return resp, _extract_viewstate(resp) or viewstate
    except urllib.error.HTTPError as e:
        if e.code != 500: raise
        _, fresh_vs, _ = _open_solicitacao_page_simple(opener, url)
        payload["javax.faces.ViewState"] = fresh_vs or viewstate or ""
        resp = _post(opener, url, payload)
        return resp, _extract_viewstate(resp) or fresh_vs

def extrair_uma_solicitacao(opener, jsessionid, viewstate, numero, data_inicio="", data_fim="", use_browser_fallback=True, usuario=None, senha=None):
    """
    Busca uma solicitação prioritariamente no módulo de solicitações.
    Se falhar ou retornar dados vazios, tenta via Playwright (fallback).
    """
    usuario = usuario or os.getenv("GDIS_USUARIO")
    senha = senha or os.getenv("GDIS_SENHA")
    # print(f"[{time.strftime('%H:%M:%S')}] DEBUG GDIS: Iniciando busca da Solicitação {numero}...")
    
    # --- ETAPA DE INICIALIZAÇÃO: Navegação de Menu ---
    # Simulando clique em Consultas -> Solicitação para garantir que o estado do servidor esteja pronto
    html_detalhe = None
    vs_atual = viewstate
    def _find_sol_links(html_text):
        found = []
        if not html_text: return found
        start = 0
        while True:
            idx = html_text.find(str(numero), start)
            if idx == -1: break
            
            a_idx = html_text.rfind('<a ', 0, idx)
            if a_idx != -1:
                close_idx = html_text.find('</a>', a_idx, idx)
                if close_idx == -1:
                    tag_end = html_text.find('>', a_idx)
                    if tag_end != -1 and tag_end < idx:
                        tag_attrs = html_text[a_idx:tag_end]
                        id_match = re.search(r'id=["\']([^"\']+)["\']', tag_attrs, re.I)
                        if id_match:
                            found.append((str(numero), id_match.group(1)))
            start = idx + 1
        return list(dict.fromkeys(found))
        
    try:
        # print(f"[{time.strftime('%H:%M:%S')}] DEBUG GDIS: Inicializando estado via navegação de menu...")
        init_content, vs_menu, actual_url = _open_solicitacao_page_simple(opener, URL_PESQUISA_SOLICITACAO)
        
        # Simular clique em "Consultas" (j_id18:j_id26)
        # IDs extraídos de debug_1_search_page.html: j_id18:j_id26 (Consultas), j_id18:j_id27 (Solicitação)
        menu_payload = {
            "AJAXREQUEST": "_viewRoot",
            "j_id18:j_id26": "j_id18:j_id26",
            "j_id18": "j_id18",
            "javax.faces.ViewState": vs_menu or ""
        }
        resp_menu1 = _post(opener, actual_url, menu_payload)
        
        # Simular clique em "Solicitação" (j_id18:j_id27)
        vs_menu2 = _extract_viewstate(resp_menu1) or vs_menu
        item_payload = {
            "AJAXREQUEST": "_viewRoot",
            "j_id18:j_id27": "j_id18:j_id27",
            "j_id18": "j_id18",
            "javax.faces.ViewState": vs_menu2 or ""
        }
        search_html = _post(opener, actual_url, item_payload)
        vs_atual = _extract_viewstate(search_html) or vs_menu2
        
        # Agora tentamos a pesquisa na página inicializada
        print(f"[{time.strftime('%H:%M:%S')}] DEBUG GDIS: Buscando solicitação na página inicializada pelo menu...")
        resp_pesq, vs_pesq = _pesquisar_solicitacao(opener, jsessionid, vs_atual, numero=numero, url=actual_url, html_content=search_html, data_inicio=data_inicio, data_fim=data_fim)

        links = _find_sol_links(resp_pesq)
        if links:
            # Tática: Sempre simular o clique (AJAX) conforme pedido pelo usuário
            # O acesso direto GET pode retornar skeletons vazios.
            print(f"[{time.strftime('%H:%M:%S')}] DEBUG GDIS: Simulando clique (AJAX) na solicitação {numero}...")
            anchor_id = links[0][1]
            html_detalhe, vs_final = _abrir_detalhe_solicitacao(opener, jsessionid, vs_pesq, anchor_id, numero, actual_url)
            vs_atual = vs_final
            
            # Se ainda assim o AJAX falhou em trazer dados (raro), tenta o GET como último recurso
            if 'eqpsList:tb"></tbody>' in html_detalhe or 'inputDetalhe"></span>' in html_detalhe:
                url_direta = f"{BASE_URL}/pages/solicitacao/detalhasolicitacao.jsf?idSolicitacaoParam={numero}"
                try:
                    html_det = _get(opener, url_direta)
                    if 'eqpsList:tb"></tbody>' not in html_det:
                        html_detalhe = html_det
                        vs_atual = _extract_viewstate(html_det) or vs_atual
                except: pass

    except Exception as e:
        print(f"[{time.strftime('%H:%M:%S')}] DEBUG GDIS: Falha na inicialização via menu: {e}")

    # Se a inicialização via menu falhou ou não achou nada, tenta as URLs de fallback
    if not html_detalhe:
        urls_tentar = [
            URL_PESQUISA_SOLICITACAO,
            f"{BASE_URL}/pages/solicitacao/solicitacaoGeral.jsf",
            URL_MANOBRA 
        ]
        
        for url_alvo in urls_tentar:
            try:
                print(f"[{time.strftime('%H:%M:%S')}] DEBUG GDIS: Tentando buscar em: {url_alvo}")
                content, vs_pagi, actual_url = _open_solicitacao_page_simple(opener, url_alvo)
                
                if "manobraGeral" in url_alvo:
                    resp_pesq, vs_pesq = _pesquisar(opener, jsessionid, vs_pagi, situacao="", numero_solicitacao=numero, data_inicio=data_inicio, data_fim=data_fim)
                else:
                    resp_pesq, vs_pesq = _pesquisar_solicitacao(opener, jsessionid, vs_pagi, numero=numero, url=url_alvo, html_content=content, data_inicio=data_inicio, data_fim=data_fim)
                
                links = _find_sol_links(resp_pesq)
                
                if links:
                    url_direta = f"{BASE_URL}/pages/solicitacao/detalhasolicitacao.jsf?idSolicitacaoParam={numero}"
                    print(f"[{time.strftime('%H:%M:%S')}] DEBUG GDIS: Tentando acesso direto...")
                    try:
                        html_det = _get(opener, url_direta)
                        if "Solicitação" in html_det and 'eqpsList:tb"></tbody>' not in html_det:
                            html_detalhe = html_det
                            vs_atual = _extract_viewstate(html_detalhe) or vs_pesq
                            break
                    except:
                        pass

                    anchor_id = links[0][1]
                    f_id = "formPesquisa"
                    p_id = "idSolicitacaoParam"
                    if "manobra" in url_alvo:
                        f_id = "formManobra"
                        p_id = "idManobraParam" 
                    
                    html_detalhe, vs_final = _abrir_detalhe_solicitacao(opener, jsessionid, vs_pesq, anchor_id, numero, url_alvo, form_id=f_id, param_id=p_id)
                    vs_atual = vs_final
                    if html_detalhe and "Solicitação" in html_detalhe:
                        break
            except Exception as e:
                print(f"[{time.strftime('%H:%M:%S')}] DEBUG GDIS: Erro ao tentar {url_alvo}: {e}")
                continue

    # --- ESTRATÉGIA HÍBRIDA: Fallback para Browser se não achou via HTTP ---
    if not html_detalhe and use_browser_fallback and usuario and senha:
        print(f"[{time.strftime('%H:%M:%S')}] AVISO: HTTP não encontrou a solicitação. Tentando fallback via Browser para {numero}...")
        try:
            with GDISBrowserExtrator(headless=True) as browser:
                if browser.login(usuario, senha):
                    html_detalhe = browser.extrair_detalhes_solicitacao(numero)
                    if html_detalhe:
                        print(f"[{time.strftime('%H:%M:%S')}] SUCESSO: Detalhes recuperados via Browser (após falha na busca HTTP)!")
        except Exception as e:
            print(f"[{time.strftime('%H:%M:%S')}] ERRO no Fallback Browser (Busca): {str(e)}")

    if not html_detalhe:
        print(f"[{time.strftime('%H:%M:%S')}] ERRO: Solicitação {numero} não encontrada em nenhum módulo.")
        return [], [], vs_atual, "", ""

    # Debug: Salva sempre o HTML de detalhe para análise se a extração falhar drasticamente
    try:
        os.makedirs("temp", exist_ok=True)
        fname = f"temp/debug_solicitacao_detalhe_{numero}.html"
        with open(fname, "w", encoding="utf-8") as f:
            f.write(html_detalhe)
    except:
        pass

    eq1, al1 = _parse_itens_tables(html_detalhe)
    eq2, al2 = _parse_eventos(html_detalhe)
    eq = sorted(set(eq1) | set(eq2))
    al = sorted(set(al1) | set(al2))

    eq3 = _super_fallback_equipamentos(html_detalhe)
    eq = sorted(set(eq) | set(eq3))

    d_ini, d_fim = _parse_datas(html_detalhe)
    
    # --- Fallback secundário: Re-extração se dados vierem vazios (já coberto acima se veio do browser) ---
    if use_browser_fallback and not eq and not d_ini and usuario and senha:
        # Se chegamos aqui e ainda está vazio, mas o html_detalhe EXISTE (veio do HTTP), o HTTP pode ter falhado no detalhe
        print(f"[{time.strftime('%H:%M:%S')}] AVISO: Dados vazios no HTML HTTP. Tentando fallback via Browser...")
        try:
            with GDISBrowserExtrator(headless=True) as browser:
                if browser.login(usuario, senha):
                    html_b = browser.extrair_detalhes_solicitacao(numero)
                    if html_b:
                        eq1_b, al1_b = _parse_itens_tables(html_b)
                        eq2_b, al2_b = _parse_eventos(html_b)
                        eq = sorted(set(eq1_b) | set(eq2_b))
                        al = sorted(set(al1_b) | set(al2_b))
                        d_ini, d_fim = _parse_datas(html_b)
                        print(f"[{time.strftime('%H:%M:%S')}] SUCESSO: Dados recuperados via Browser (após dados vazios no HTTP)!")
        except Exception as e:
            print(f"[{time.strftime('%H:%M:%S')}] ERRO no Fallback Browser (Dados): {str(e)}")

    if not eq and not d_ini:
         print(f"[{time.strftime('%H:%M:%S')}] AVISO: Falha total ao extrair dados da Solicitação {numero}. HTML salvo em temp/debug_solicitacao_detalhe_{numero}.html")
         
    return eq, al, vs_atual, d_ini, d_fim


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
