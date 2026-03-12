import getpass
import html
import os
import re
import urllib.parse
import urllib.error
import urllib.request
from http.cookiejar import CookieJar


BASE_URL = "http://gdis-pm/gdispm"

URL_HOME = f"{BASE_URL}/"
URL_LOGIN = f"{BASE_URL}/login.jsf"
URL_MANOBRA = f"{BASE_URL}/pages/manobra/manobraGeral.jsf"

DATA_INICIO = "18/03/2026"
DATA_FIM = "18/03/2026"

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
    req.add_header("X-Requested-With", "XMLHttpRequest")
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    with opener.open(req, timeout=_http_timeout()) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _get(opener, url, headers=None):
    req = urllib.request.Request(url, method="GET")
    req.add_header("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    with opener.open(req, timeout=_http_timeout()) as resp:
        return resp.read().decode("utf-8", errors="replace")


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
    for t in re.finditer(
        r'<table[^>]+id="([^"]*:itensCadastrados)"[^>]*>([\s\S]*?)</table>',
        html_text or "",
        flags=re.IGNORECASE,
    ):
        table_html = t.group(2)
        ths = re.findall(r"<th[^>]*>([\s\S]*?)</th>", table_html, flags=re.IGNORECASE)
        headers = [_strip_tags(x).lower() for x in ths]
        idx_eq = next((i for i, h in enumerate(headers) if "eqpto" in h or "trafo" in h), -1)
        idx_al = next((i for i, h in enumerate(headers) if "alimen" in h or "subes" in h), -1)
        if idx_eq < 0 and idx_al < 0:
            continue
        tbody_m = re.search(r"<tbody[^>]*>([\s\S]*?)</tbody>", table_html, flags=re.IGNORECASE)
        tbody = tbody_m.group(1) if tbody_m else table_html
        for rm in re.finditer(r"<tr[^>]*>([\s\S]*?)</tr>", tbody, flags=re.IGNORECASE):
            row_html = rm.group(1)
            tds = re.findall(r"<td[^>]*>([\s\S]*?)</td>", row_html, flags=re.IGNORECASE)
            if idx_eq >= 0 and len(tds) > idx_eq:
                v = _strip_tags(tds[idx_eq])
                if v and v != "-" and v != " - ":
                    eqptos.add(v)
            if idx_al >= 0 and len(tds) > idx_al:
                v = _strip_tags(tds[idx_al])
                if v and v != "-" and v != " - ":
                    alim.add(v)
    return sorted(eqptos), sorted(alim)


def _parse_eventos(html_text):
    text = html.unescape(html_text or "")
    eq = set()
    al = set()
    for m in re.finditer(r"\b\d{3,7}\s*-\s*\d+\s*-\s*\d+\b", text):
        eq.add(re.sub(r"\s*-\s*", " - ", m.group(0).strip()))
    for m in re.finditer(r"\b\d{2}\s*-\s*\d{5,7}\b", text):
        eq.add(re.sub(r"\s*-\s*", " - ", m.group(0).strip()))
    for m in re.finditer(r"Subesta(?:ç|c)ão\s+([A-Z]{3,6}\d{0,3})", text, flags=re.IGNORECASE):
        al.add(m.group(1).upper())
    for m in re.finditer(r"Alimentador\s+([A-Z]{3,6}\d{0,3})", text, flags=re.IGNORECASE):
        al.add(m.group(1).upper())
    return sorted(eq), sorted(al)


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


def _pesquisar(opener, jsessionid, viewstate, situacao, numero_manobra=None, data_inicio=None, data_fim=None):
    url = URL_MANOBRA
    if jsessionid:
        url = f"{URL_MANOBRA};jsessionid={jsessionid}"
    payload = {
        "AJAXREQUEST": "_viewRoot",
        "formPesquisa": "formPesquisa",
        "autoScroll": "",
        "formPesquisa:consultaManobras2": "true",
        "formPesquisa:numeroManobra": numero_manobra or "",
        "formPesquisa:numeroSolicitacao": "",
        "formPesquisa:numeroManobraCondis": "",
        "formPesquisa:dataInicioInputDate": data_inicio or "",
        "formPesquisa:dataTerminioInputDate": data_fim or "",
        "formPesquisa:situacao": situacao or "",
        "formPesquisa:malha": "",
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


def coletar_manobras(opener, jsessionid, viewstate, situacao):
    resp, vs = _pesquisar(opener, jsessionid, viewstate, situacao, data_inicio=DATA_INICIO, data_fim=DATA_FIM)
    ids = set(x[0] for x in _find_manobra_links(resp))
    current_page = _extract_active_page(resp) or 1

    for page in range(current_page + 1, 501):
        advanced = False
        empty_reads = 0
        for _ in range(3):
            resp2, vs = _datascroller_page(opener, jsessionid, vs, page)
            page_ids = set(x[0] for x in _find_manobra_links(resp2))
            active = _extract_active_page(resp2)

            if not page_ids:
                empty_reads += 1
            else:
                empty_reads = 0

            if page_ids and (active == page or (page_ids - ids)):
                ids |= page_ids
                advanced = True
                break

            if empty_reads >= 2:
                break

            resp, vs = _pesquisar(
                opener,
                jsessionid,
                vs,
                situacao,
                data_inicio=DATA_INICIO,
                data_fim=DATA_FIM,
            )
            ids |= set(x[0] for x in _find_manobra_links(resp))

        if not advanced:
            break

    return sorted(ids), vs


def extrair_uma_manobra(opener, jsessionid, viewstate, numero):
    resp, vs = _pesquisar(opener, jsessionid, viewstate, situacao="", numero_manobra=numero, data_inicio="", data_fim="")
    links = _find_manobra_links(resp)
    link = next((x for x in links if x[0] == str(numero)), None)
    if not link:
        return [], [], vs
    _, anchor_id, _ = link
    detalhe = _abrir_detalhe(opener, jsessionid, vs, anchor_id, numero)
    eq1, al1 = _parse_itens_tables(detalhe)
    eq2, al2 = _parse_eventos(detalhe)
    eq = sorted(set(eq1) | set(eq2))
    al = sorted(set(al1) | set(al2))
    return eq, al, vs


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

    elaborada, vs = coletar_manobras(opener, jsessionid, vs, "EB")
    enviada, vs = coletar_manobras(opener, jsessionid, vs, "EN")
    todos = sorted(set(elaborada) | set(enviada))
    print(f"TOTAL EB: {len(elaborada)}")
    print(f"TOTAL EN: {len(enviada)}")
    print(f"TOTAL ÚNICO: {len(todos)}")

    for numero in todos:
        eq, al, vs = extrair_uma_manobra(opener, jsessionid, vs, numero)
        print(f"MANOBRA {numero}")
        print(f"  Equipamentos: {'; '.join(eq) if eq else '-'}")
        print(f"  Alimentadores/Subestações: {'; '.join(al) if al else '-'}")


if __name__ == "__main__":
    main()

