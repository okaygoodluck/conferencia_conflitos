import getpass
import os
import re
import time
import urllib.request
from http.cookiejar import CookieJar

from src.integration import gdis_http_extrator
from src.core import analisador_topologico


SITUACOES_LABEL = {
    "EB": "ELABORADA",
    "EN": "ENVIADA PARA O CONDIS",
    "CO": "COMPLETA",
    "EA": "EM ANALISE",
}


from datetime import date


def _parse_date_obj(d_str):
    """
    Converte string de data (ex: '10/09/2026', '10/09/2026 08:00', '2026-09-10') em datetime.date.
    """
    if not d_str or not isinstance(d_str, str):
        return None
    d_str = d_str.strip()
    if not d_str or d_str.lower() in ("undefined", "não definido", "null", "none"):
        return None

    parts = d_str.split()
    date_part = parts[0]

    if '/' in date_part:
        sub = date_part.split('/')
        if len(sub) == 3:
            try:
                return date(int(sub[2]), int(sub[1]), int(sub[0]))
            except (ValueError, TypeError):
                pass
    elif '-' in date_part:
        sub = date_part.split('-')
        if len(sub) == 3:
            try:
                return date(int(sub[0]), int(sub[1]), int(sub[2]))
            except (ValueError, TypeError):
                pass
    return None


def _datas_sobrepoem(ini1_str, fim1_str, ini2_str, fim2_str):
    """
    Verifica se dois intervalos de data se sobrepõem.
    Retorna False apenas se puder comprovar que as datas não se sobrepõem.
    """
    d1_start = _parse_date_obj(ini1_str)
    d1_end = _parse_date_obj(fim1_str) or d1_start
    d2_start = _parse_date_obj(ini2_str)
    d2_end = _parse_date_obj(fim2_str) or d2_start

    if not d1_start or not d2_start:
        return True  # Por segurança, assume sobreposição se não puder extrair a data

    if d1_start > d1_end:
        d1_start, d1_end = d1_end, d1_start
    if d2_start > d2_end:
        d2_start, d2_end = d2_end, d2_start

    return (d1_start <= d2_end) and (d2_start <= d1_end)



def _norm_spaces(s):
    return re.sub(r"\s+", " ", (s or "")).strip()


def _norm_eqpto(s):
    s = _norm_spaces(s)
    s = re.sub(r"\s*-\s*", " - ", s)
    return _norm_spaces(s)


def _get_eq_id(eq_name):
    """Extrai o ID do equipamento de forma robusta, preservando prefixos e sufixos únicos."""
    if not eq_name or not isinstance(eq_name, str):
        return eq_name
    
    # 1. Converte para maiúsculo e remove termos genéricos do início
    s = eq_name.upper().strip()
    s = re.sub(r"^(EQUIPAMENTO|EQPTO|EQP|CÓDIGO|CODIGO|TRAFO|TRANSFORMADOR|Nº|NUMERO|NUMBER)\s*[:\-]?\s*", "", s)
    
    # 2. Normaliza espaços e hífens para um padrão único colado (para comparação exata)
    # Isso garante que '62326 - 3 - 75' e '62326-3-75' sejam o mesmo ID interno.
    s = re.sub(r"\s*-\s*", "-", s)
    s = re.sub(r"\s+", " ", s).strip()
    
    return s


def _norm_alim(s):
    s = (s or "").upper()
    s = re.sub(r"[^A-Z0-9]", "", s)
    s = _norm_spaces(s)
    return s


def _is_alim_valido(s):
    return bool(re.fullmatch(r"[A-Z]{2,20}\d{0,6}", s or ""))


def _parse_date_range():
    d = (os.getenv("GDIS_DATA") or "").strip()
    if d:
        return d, d
    di = (os.getenv("GDIS_DATA_INICIO") or "").strip()
    df = (os.getenv("GDIS_DATA_FIM") or "").strip()
    if di and df:
        return di, df
    if di and not df:
        return di, di
    if df and not di:
        return df, df
    di = input("Data início (dd/mm/aaaa) [Opcional se houver Manobra/Sol]: ").strip()
    if not di:
        return "", ""
    df = input("Data fim (dd/mm/aaaa) [Deixe vazio para o mesmo dia]: ").strip()
    if not df:
        df = di
    return di, df


def _parse_base_manobra():
    v = (os.getenv("GDIS_MANOBRA_BASE") or "").strip()
    if v:
        return v
    return input("Manobra base: ").strip()


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


def _normalize_sets(eqptos, alims):
    eq_out = set()
    for e in eqptos or []:
        ne = _norm_eqpto(e)
        if ne and _is_eqpto_valido(ne):
            # Extrai o ID para garantir o cruzamento correto (especialmente para transformadores)
            eid = _get_eq_id(ne)
            if _is_eqpto_valido(eid):
                eq_out.add(eid)

    al_out = set()
    for a in alims or []:
        na = _norm_alim(a)
        if _is_alim_valido(na) and not na.startswith("ETAPA") and _is_eqpto_valido(na):
            al_out.add(na)

    return eq_out, al_out


def _fmt_seconds(seconds):
    try:
        s = int(round(float(seconds)))
    except:
        s = 0
    if s < 0:
        s = 0
    h = s // 3600
    m = (s % 3600) // 60
    ss = s % 60
    if h:
        return f"{h:02d}:{m:02d}:{ss:02d}"
    return f"{m:02d}:{ss:02d}"


def _parse_situacoes_env():
    raw = (os.getenv("GDIS_SITUACOES_PADRAO") or os.getenv("GDIS_SITUACOES") or "").strip()
    if not raw:
        return ["EB", "EN"]
    parts = re.split(r"[,\s;]+", raw)
    out = []
    seen = set()
    for p in parts:
        s = (p or "").strip().upper()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out or ["EB", "EN"]


def _normalize_situacoes(values):
    out = []
    seen = set()
    for v in values or []:
        s = (v or "").strip().upper()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def _normalize_malhas(values):
    out = []
    seen = set()
    for v in values or []:
        s = (v or "").strip().upper()
        if not s or s in seen:
            continue
        out.append(s)
    return out


def run_verificacao(base, data_inicio, data_fim, usuario, senha, progress_cb=None, situacoes=None, malhas=None, base_eq_manual=None, base_al_manual=None, log_func=print):

    try:
        opener, jsessionid, vs = gdis_http_extrator.obter_sessao_gdis(usuario, senha)
    except ValueError as e:
        raise RuntimeError(str(e))

    # Extrai lista de manobras base (seja string com vários IDs, lista ou id único)
    base_manobras_list = []
    if isinstance(base, list):
        base_manobras_list = [str(x).strip() for x in base if str(x).strip()]
    elif base and str(base).strip():
        found = re.findall(r"\b\d{6,10}\b", str(base))
        if found:
            seen = set()
            for m_id in found:
                if m_id not in seen:
                    seen.add(m_id)
                    base_manobras_list.append(m_id)
        else:
            base_manobras_list = [str(base).strip()]

    # Dicionário para armazenar dados de cada base
    bases_data = {}
    d_ini_list = []
    d_fim_list = []
    beq_total = set()
    bal_total = set()

    for m_base in base_manobras_list:
        log_func(f"[{time.strftime('%H:%M:%S')}] [INFO] Extraindo manobra base {m_base}...")
        d_ini_search = data_inicio if data_inicio and data_inicio != "undefined" else ""
        d_fim_search = data_fim if data_fim and data_fim != "undefined" else ""

        try:
            b_eq, b_al, vs, b_ini, b_fim = gdis_http_extrator.extrair_uma_manobra(opener, jsessionid, vs, m_base, malha="", data_inicio=d_ini_search, data_fim=d_fim_search)
            beq, bal = _normalize_sets(b_eq, b_al)
        except Exception as e:
            log_func(f"[{time.strftime('%H:%M:%S')}] [WARN] Erro ao extrair manobra base {m_base}: {e}")
            beq, bal = set(), set()
            b_ini, b_fim = "", ""

        if b_ini:
            d_ini_list.append(b_ini.split()[0])
        if b_fim:
            d_fim_list.append(b_fim.split()[0])

        bases_data[m_base] = {
            "eq": beq,
            "al": bal,
            "b_ini": b_ini,
            "b_fim": b_fim
        }
        beq_total.update(beq)
        bal_total.update(bal)

    # Se houver itens manuais, adicionamos ao conjunto de busca
    if base_eq_manual:
        manual_eq, _ = _normalize_sets(base_eq_manual, [])
        beq_total.update(manual_eq)
        bases_data["Itens Manuais"] = bases_data.get("Itens Manuais", {"eq": set(), "al": set()})
        bases_data["Itens Manuais"]["eq"].update(manual_eq)
    
    if base_al_manual:
        _, manual_al = _normalize_sets([], base_al_manual)
        bal_total.update(manual_al)
        bases_data["Itens Manuais"] = bases_data.get("Itens Manuais", {"eq": set(), "al": set()})
        bases_data["Itens Manuais"]["al"].update(manual_al)

    # Fallback de datas: se o usuário não forneceu, usa o intervalo min/max extraído das manobras base
    def _parse_d(d_str):
        parts = d_str.split('/')
        if len(parts) == 3:
            return f"{parts[2]}-{parts[1]}-{parts[0]}"
        return d_str

    if not data_inicio or data_inicio == "undefined":
        if d_ini_list:
            sorted_d_ini = sorted(d_ini_list, key=_parse_d)
            data_inicio = sorted_d_ini[0]
            log_func(f"[{time.strftime('%H:%M:%S')}] [INFO] Data início auto-consolidada: {data_inicio}")
        else:
            log_func(f"[{time.strftime('%H:%M:%S')}] [WARN] Não foi possível extrair a data de início da base.")

    if not data_fim or data_fim == "undefined":
        if d_fim_list:
            sorted_d_fim = sorted(d_fim_list, key=_parse_d)
            data_fim = sorted_d_fim[-1]
            log_func(f"[{time.strftime('%H:%M:%S')}] [INFO] Data fim auto-consolidada: {data_fim}")
        else:
             log_func(f"[{time.strftime('%H:%M:%S')}] [WARN] Não foi possível extrair a data de término da base.")

    # Log consolidado da Base (Telemetria Técnica)
    log_func(f"\n[{time.strftime('%H:%M:%S')}] [INFO] >>> CONSOLIDADO DE BUSCA (BASES) <<<")
    log_func(f"[{time.strftime('%H:%M:%S')}] [INFO] MANOBRAS BASE PROCESSADAS: {', '.join(base_manobras_list) if base_manobras_list else 'Nenhuma'}")
    log_func(f"[{time.strftime('%H:%M:%S')}] [INFO] EQUIPAMENTOS NA BASE (TOTAL): {', '.join(sorted(beq_total)) if beq_total else 'Nenhum'}")
    log_func(f"[{time.strftime('%H:%M:%S')}] [INFO] ALIMENTADORES NA BASE (TOTAL): {', '.join(sorted(bal_total)) if bal_total else 'Nenhum'}")
    log_func(f"[{time.strftime('%H:%M:%S')}] [INFO] PERÍODO PESQUISADO: {data_inicio or 'NÃO DEFINIDO'} até {data_fim or 'NÃO DEFINIDO'}\n")

    # VALIDAÇÃO FINAL DE DATAS: Só barramos se após a extração da base ainda estivermos sem datas.
    if not data_inicio or not data_fim or data_inicio == "undefined" or data_fim == "undefined":
        log_func(f"[{time.strftime('%H:%M:%S')}] [ERROR] Datas de busca não definidas. Informe as datas manualmente ou verifique a manobra base.")
        return {
            "status": "erro",
            "erro": "Datas de busca não definidas. Certifique-se de preenchê-las ou usar uma manobra base válida.",
            "conflitos": [],
            "resultado_por_base": {},
            "conflitos_internos": [],
            "total_unico_sem_base": 0,
            "situacoes_total": {},
            "situacoes_usadas": situacoes,
            "situacoes_label": SITUACOES_LABEL,
            "base": ", ".join(base_manobras_list) if base_manobras_list else (base or "Manual"),
            "bases_analisadas": base_manobras_list,
            "base_equipamentos": sorted(beq_total),
            "base_alimentadores": sorted(bal_total),
            "data_inicio": data_inicio or "NÃO DEFINIDO",
            "data_fim": data_fim or "NÃO DEFINIDO"
        }

    # Identificar conflitos ENTRE as manobras base coladas (Conflitos Internos)
    conflitos_internos = []
    base_names = sorted(bases_data.keys())
    for i in range(len(base_names)):
        for j in range(i + 1, len(base_names)):
            b1 = base_names[i]
            b2 = base_names[j]
            b1_data = bases_data[b1]
            b2_data = bases_data[b2]

            # Valida se as datas das duas manobras do lote se sobrepõem
            if not _datas_sobrepoem(b1_data.get("b_ini"), b1_data.get("b_fim"), b2_data.get("b_ini"), b2_data.get("b_fim")):
                log_func(f"[{time.strftime('%H:%M:%S')}] [INFO] {b1} ({b1_data.get('b_ini') or 'N/A'}) e {b2} ({b2_data.get('b_ini') or 'N/A'}): Datas distintas, descartado conflito interno.")
                continue

            eq_hit = sorted(b1_data["eq"].intersection(b2_data["eq"]))
            al_hit = sorted(b1_data["al"].intersection(b2_data["al"]))
            if eq_hit or al_hit:
                log_func(f"[{time.strftime('%H:%M:%S')}] [CONFLITO-INTERNO] {b1} vs {b2} possuem itens em comum e datas coincidentes!")
                conflitos_internos.append({
                    "origem": b1,
                    "destino": b2,
                    "equipamentos": eq_hit,
                    "alimentadores": al_hit,
                    "data_origem": b1_data.get("b_ini") or "NÃO DEFINIDO",
                    "data_destino": b2_data.get("b_ini") or "NÃO DEFINIDO"
                })

    situacoes = _normalize_situacoes(situacoes) if situacoes is not None else _parse_situacoes_env()
    if not situacoes:
        situacoes = ["EB", "EN"]
    
    malhas = _normalize_malhas(malhas)
    if not malhas or malhas == [""]:
        # Tenta extrair malhas automáticas dos alimentadores da base (ex: MAGU113 -> MAGU)
        auto_malhas = set()
        for a in bal_total:
            m = re.match(r"^([A-Za-z]{3,4})", a)
            if m:
                auto_malhas.add(m.group(1).upper())
        if auto_malhas:
            log_func(f"[{time.strftime('%H:%M:%S')}] [INFO] Malhas de busca auto-detectadas a partir dos alimentadores: {', '.join(sorted(auto_malhas))}")
            malhas = sorted(list(auto_malhas))
        else:
            malhas = [""]

    ids_por_situacao = {}
    situacoes_por_manobra = {}
    contagem_por_malha = {}
    malhas_por_manobra = {}
    
    for malha in malhas:
        malha_key = malha if malha else "Global"
        contagem_por_malha[malha_key] = {}

        for sit in situacoes:
            ids, vs = gdis_http_extrator.coletar_manobras(opener, jsessionid, vs, sit, data_inicio, data_fim, malha=malha)
            contagem_por_malha[malha_key][sit] = len(ids)

            if sit not in ids_por_situacao:
                ids_por_situacao[sit] = []
            ids_por_situacao[sit].extend(ids)

            for m in ids:
                if m not in situacoes_por_manobra:
                    situacoes_por_manobra[m] = set()
                situacoes_por_manobra[m].add(sit)
                malhas_por_manobra[m] = malha

    for sit in ids_por_situacao:
        ids_por_situacao[sit] = sorted(list(set(ids_por_situacao[sit])))

    todos_unico = sorted(set(situacoes_por_manobra.keys()))
    # Remove as próprias manobras base da lista de verificação se foram encontradas na busca
    if base_manobras_list:
        todos_unico = [x for x in todos_unico if x not in base_manobras_list]

    conflitos = []
    falhas = []
    processed = 0
    total = len(todos_unico)
    started_at = time.perf_counter()
    last_progress_at = started_at
    for numero in todos_unico:
        if progress_cb:
            progress_cb({
                "processed": processed,
                "total": total,
                "current": numero,
                "conflitos": len(conflitos),
                "falhas": len(falhas),
                "elapsed_seconds": time.perf_counter() - started_at,
                "eta_seconds": 0
            })
            
        item_started_at = time.perf_counter()
        m_malha = malhas_por_manobra.get(numero, "")
        try:
            eq, al, vs, m_ini, m_fim = gdis_http_extrator.extrair_uma_manobra(opener, jsessionid, vs, numero, malha=m_malha, data_inicio=data_inicio, data_fim=data_fim)
            eq, al = _normalize_sets(eq, al)
        except Exception as e:
            falhas.append({
                "manobra": numero,
                "erro": str(e),
                "situacoes": sorted(situacoes_por_manobra.get(numero) or []),
            })
            eq, al = set(), set()
            m_ini, m_fim = None, None

        eq_hit_total = sorted(beq_total.intersection(eq)) if beq_total else []
        al_hit_total = sorted(bal_total.intersection(al)) if bal_total else []

        if eq_hit_total or al_hit_total:
            # Para cada manobra base, verifica se há intersecção específica
            for m_base, b_data in bases_data.items():
                m_beq = b_data["eq"]
                m_bal = b_data["al"]
                b_ini_base = b_data.get("b_ini")
                b_fim_base = b_data.get("b_fim")

                # Valida se a manobra do GDIS (numero) tem sobreposição de datas com esta manobra base
                if not _datas_sobrepoem(b_ini_base, b_fim_base, m_ini, m_fim):
                    continue

                eq_hit = sorted(m_beq.intersection(eq)) if m_beq else []
                al_hit = sorted(m_bal.intersection(al)) if m_bal else []

                if eq_hit or al_hit:
                    tipo_conflito = "DIRETO_EQUIPAMENTO" if eq_hit else "ALIMENTADOR_COMPARTILHADO"
                    detalhes_topo = []

                    # Análise Topológica Elétrica com NetworkX quando houver alimentador em comum
                    if al_hit and m_beq and eq:
                        nos = [{"id": e, "numeq": e, "POSOPE": "F"} for e in m_beq.union(eq)]
                        arestas = []
                        dados_sim = {"nos": nos, "arestas": arestas}
                        G_sim = analisador_topologico.construir_grafo_topologico(dados_sim)
                        tem_caminho, conexoes = analisador_topologico.verificar_conectividade_eletrica(G_sim, m_beq, eq)
                        if tem_caminho:
                            tipo_conflito = "TOPOLOGICO_ENERGIZADO"
                            detalhes_topo = conexoes
                        elif not eq_hit:
                            tipo_conflito = "ALIMENTADOR_RAMAL_ISOLADO"

                    log_func(f"[{time.strftime('%H:%M:%S')}] [CONFLITO-{tipo_conflito}] Manobra {numero} ({m_ini or 'sem data'}) conflita com Manobra Base {m_base} ({b_ini_base or 'sem data'})!")
                    conflitos.append({
                        "base_origem": m_base,
                        "manobra": numero,
                        "data_manobra": m_ini or "NÃO DEFINIDO",
                        "equipamentos": eq_hit,
                        "alimentadores": al_hit,
                        "situacoes": sorted(situacoes_por_manobra.get(numero) or []),
                        "tipo_conflito": tipo_conflito,
                        "detalhes_topologia": detalhes_topo
                    })

        processed += 1

        now = time.perf_counter()
        if progress_cb and (processed == 1 or processed == total or (now - last_progress_at) >= 2):
            elapsed = now - started_at
            rate = processed / elapsed if elapsed > 0 else 0.0
            remaining = total - processed
            eta = (remaining / rate) if rate > 0 else 0.0
            progress_cb({
                "processed": processed,
                "total": total,
                "elapsed_seconds": elapsed,
                "eta_seconds": eta,
                "rate_per_min": rate * 60,
                "last_seconds": now - item_started_at,
                "conflitos": len(conflitos),
                "falhas": len(falhas),
                "current": numero,
            })
            last_progress_at = now

    finished_at = time.perf_counter()

    # Estruturação do resultado individualizado por manobra base
    resultado_por_base = {}
    for m_base in base_manobras_list:
        b_data = bases_data.get(m_base, {})
        c_list = [c for c in conflitos if c.get("base_origem") == m_base]

        # Anexa conflitos internos do lote pertencentes a esta manobra base
        for ci in conflitos_internos:
            other_m = None
            other_d = None
            if ci["origem"] == m_base:
                other_m = ci["destino"]
                other_d = ci.get("data_destino")
            elif ci["destino"] == m_base:
                other_m = ci["origem"]
                other_d = ci.get("data_origem")

            if other_m:
                c_list.append({
                    "base_origem": m_base,
                    "manobra": other_m,
                    "data_manobra": other_d or "NÃO DEFINIDO",
                    "equipamentos": ci["equipamentos"],
                    "alimentadores": ci["alimentadores"],
                    "situacoes": ["LOTE_INTERNO"],
                    "tipo_conflito": "CONFLITO INTERNO (LOTE)",
                    "is_interno": True
                })

        resultado_por_base[m_base] = {
            "manobra": m_base,
            "data_inicio": b_data.get("b_ini") or "",
            "data_fim": b_data.get("b_fim") or "",
            "equipamentos": sorted(b_data.get("eq") or []),
            "alimentadores": sorted(b_data.get("al") or []),
            "conflitos": c_list,
            "total_conflitos": len(c_list)
        }

    return {
        "base": ", ".join(base_manobras_list) if base_manobras_list else (base or "Manual"),
        "bases_analisadas": base_manobras_list,
        "data_inicio": data_inicio,
        "data_fim": data_fim,
        "base_equipamentos": sorted(beq_total),
        "base_alimentadores": sorted(bal_total),
        "resultado_por_base": resultado_por_base,
        "conflitos_internos": conflitos_internos,
        "malhas_usadas": malhas,
        "situacoes_usadas": situacoes,
        "situacoes_total": {k: len(v or []) for (k, v) in ids_por_situacao.items()},
        "contagem_por_malha": contagem_por_malha,
        "situacoes_label": {k: SITUACOES_LABEL.get(k, k) for k in situacoes},
        "total_unico_sem_base": len(todos_unico),
        "conflitos": conflitos,
        "falhas": falhas,
        "elapsed_seconds": finished_at - started_at,
    }


def _parse_malhas_input():
    raw_env = (os.getenv("GDIS_MALHAS_PADRAO") or os.getenv("GDIS_MALHAS") or "").strip()
    if raw_env:
        return _normalize_malhas(re.split(r"[,\s;]+", raw_env))
    
    print("\nMalhas disponíveis: CN, LE, MQ, NT, SU, TA")
    raw_input = input("Digite as malhas (separadas por vírgula, deixe em branco para buscar em todas): ").strip()
    if not raw_input:
        return [""] # String vazia representa "todas as malhas"
    return _normalize_malhas(re.split(r"[,\s;]+", raw_input))


def main():
    base = _parse_base_manobra()
    di, df = _parse_date_range()
    malhas = _parse_malhas_input()

    usuario = (os.getenv("GDIS_USUARIO") or "").strip() or input("Usuário: ").strip()
    senha = (os.getenv("GDIS_SENHA") or "").strip() or getpass.getpass("Senha: ")

    started_at = time.perf_counter()

    def cb(p):
        print(
            f"[PROGRESS] {p['processed']}/{p['total']} | "
            f"Analisando: {p['current']} | "
            f"ETA: {_fmt_seconds(p['eta_seconds'])} | "
            f"Cnf: {p['conflitos']}"
        )

    try:
        r = run_verificacao(base, di, df, usuario, senha, progress_cb=cb, malhas=malhas)
    except RuntimeError as e:
        print(str(e))
        return
    
    malhas_str = ", ".join(m for m in r["malhas_usadas"] if m) or "Todas"

    print(f"\nBASE {r['base']}")
    print(f"  Equipamentos: {'; '.join(r['base_equipamentos']) if r['base_equipamentos'] else '-'}")
    print(f"  Alimentadores/Subestações: {'; '.join(r['base_alimentadores']) if r['base_alimentadores'] else '-'}")
    print(f"PERÍODO {r['data_inicio']} a {r['data_fim']}")
    print(f"MALHAS: {malhas_str}")
    print(f"SITUAÇÕES: {', '.join(r['situacoes_usadas'])}")

    print("\n--- TOTAIS ---")
    for sit in r["situacoes_usadas"]:
        label = r["situacoes_label"].get(sit, sit)
        total = r["situacoes_total"].get(sit, 0)
        print(f"TOTAL {sit} ({label}): {total}")

    if r.get("contagem_por_malha"):
        contagens = r["contagem_por_malha"]
        # Só exibe a seção se houver múltiplas malhas ou uma busca global explícita
        if len(contagens) > 1 or "Global" in contagens:
            print("\n--- TOTAIS POR MALHA ---")
            for malha, sit_dict in sorted(contagens.items()):
                malha_str = f"Malha {malha}" if malha != "Global" else "Busca Geral (sem malha)"
                counts_str = []
                for sit in sorted(sit_dict.keys()):
                    count = sit_dict[sit]
                    if count > 0:
                        counts_str.append(f"{sit}: {count}")
                if counts_str:
                    print(f"  {malha_str}: {', '.join(counts_str)}")
    
    print(f"TOTAL ÚNICO (sem base): {r['total_unico_sem_base']}")
    print(f"CONFLITOS ENCONTRADOS: {len(r['conflitos'])}")
    if r.get("falhas"):
        print(f"FALHAS NA EXTRAÇÃO: {len(r['falhas'])}")
    
    print("\n--- DETALHES DOS CONFLITOS ---")
    for c in r["conflitos"]:
        sits_str = ", ".join(c.get("situacoes") or [])
        print(f"MANOBRA {c['manobra']} (Situações: {sits_str})")
        if c.get("equipamentos"):
            print(f"  Equipamentos em comum: {'; '.join(c['equipamentos'])}")
        if c.get("alimentadores"):
            print(f"  Alimentadores/Subestações em comum: {'; '.join(c['alimentadores'])}")
    
    if r.get("falhas"):
        print("\n--- DETALHES DAS FALHAS ---")
        for f in r["falhas"][:10]:
            print(f"FALHA {f.get('manobra')}: {f.get('erro')}")

    print(f"\nTEMPO TOTAL: {_fmt_seconds(time.perf_counter() - started_at)}")


if __name__ == "__main__":
    main()
