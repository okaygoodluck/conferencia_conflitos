import getpass
import os
import re
import time
import urllib.request
from http.cookiejar import CookieJar

from src.integration import gdis_http_extrator


SITUACOES_LABEL = {
    "EB": "ELABORADA",
    "EN": "ENVIADA PARA O CONDIS",
    "CO": "COMPLETA",
    "EA": "EM ANALISE",
}


def _norm_spaces(s):
    return re.sub(r"\s+", " ", (s or "")).strip()


def _norm_eqpto(s):
    s = _norm_spaces(s)
    s = re.sub(r"\s*-\s*", " - ", s)
    return _norm_spaces(s)


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
    di = input("Data início (dd/mm/aaaa): ").strip()
    df = input("Data fim (dd/mm/aaaa): ").strip()
    if not df:
        df = di
    return di, df


def _parse_base_manobra():
    v = (os.getenv("GDIS_MANOBRA_BASE") or "").strip()
    if v:
        return v
    return input("Manobra base: ").strip()


def _normalize_sets(eqptos, alims):
    eq_out = set()
    for e in eqptos or []:
        ne = _norm_eqpto(e)
        if ne and ne != "-" and ne != " - ":
            eq_out.add(ne)

    al_out = set()
    for a in alims or []:
        na = _norm_alim(a)
        if _is_alim_valido(na):
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
        seen.add(s)
        out.append(s)
    return out


def run_verificacao(base, data_inicio, data_fim, usuario, senha, progress_cb=None, situacoes=None, malhas=None, base_eq_manual=None, base_al_manual=None):
    gdis_http_extrator.DATA_INICIO = data_inicio
    gdis_http_extrator.DATA_FIM = data_fim

    jar = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    try:
        jsessionid, _ = gdis_http_extrator._login(opener, usuario, senha)
        _, vs = gdis_http_extrator._open_manobra_page(opener, jsessionid)
    except ValueError as e:
        raise RuntimeError(str(e))

    # Se uma manobra base for fornecida, extraímos seus dados.
    if base and str(base).strip():
        base_eq, base_al, vs = gdis_http_extrator.extrair_uma_manobra(opener, jsessionid, vs, base, malha="")
        base_eq, base_al = _normalize_sets(base_eq, base_al)
    else:
        base_eq, base_al = set(), set()
    
    # Se houver itens manuais, adicionamos ao conjunto de busca
    if base_eq_manual:
        manual_eq, _ = _normalize_sets(base_eq_manual, [])
        base_eq.update(manual_eq)
    
    if base_al_manual:
        _, manual_al = _normalize_sets([], base_al_manual)
        base_al.update(manual_al)

    situacoes = _normalize_situacoes(situacoes) if situacoes is not None else _parse_situacoes_env()
    if not situacoes:
        situacoes = ["EB", "EN"]
    
    malhas = _normalize_malhas(malhas)
    if not malhas:
        # Se nenhuma malha for fornecida, busca em todas (representado por string vazia)
        malhas = [""]
    
    ids_por_situacao = {}
    situacoes_por_manobra = {}
    contagem_por_malha = {}
    malhas_por_manobra = {}
    
    # Loop principal por malha, depois por situação
    for malha in malhas:
        malha_key = malha if malha else "Global"
        contagem_por_malha[malha_key] = {}

        for sit in situacoes:
            ids, vs = gdis_http_extrator.coletar_manobras(opener, jsessionid, vs, sit, malha=malha)
            
            contagem_por_malha[malha_key][sit] = len(ids)

            # Acumula os IDs por situação (considerando a malha)
            if sit not in ids_por_situacao:
                ids_por_situacao[sit] = []
            ids_por_situacao[sit].extend(ids)

            for m in ids:
                if m not in situacoes_por_manobra:
                    situacoes_por_manobra[m] = set()
                situacoes_por_manobra[m].add(sit)
                # Store the malha associated with this manobra. If multiple, any valid one works.
                malhas_por_manobra[m] = malha

    # Garante que os IDs em cada situação são únicos
    for sit in ids_por_situacao:
        ids_por_situacao[sit] = sorted(list(set(ids_por_situacao[sit])))

    todos_unico = sorted(set(situacoes_por_manobra.keys()))
    if base in todos_unico:
        todos_unico = [x for x in todos_unico if x != base]

    conflitos = []
    falhas = []
    processed = 0
    total = len(todos_unico)
    started_at = time.perf_counter()
    last_progress_at = started_at
    for numero in todos_unico:
        item_started_at = time.perf_counter()
        m_malha = malhas_por_manobra.get(numero, "")
        try:
            eq, al, vs = gdis_http_extrator.extrair_uma_manobra(opener, jsessionid, vs, numero, malha=m_malha)
            eq, al = _normalize_sets(eq, al)
        except Exception as e:
            falhas.append(
                {
                    "manobra": numero,
                    "erro": str(e),
                    "situacoes": sorted(situacoes_por_manobra.get(numero) or []),
                }
            )
            eq = set()
            al = set()

        eq_hit = sorted(base_eq.intersection(eq)) if base_eq else []
        al_hit = sorted(base_al.intersection(al)) if base_al else []
        if eq_hit or al_hit:
            conflitos.append((numero, eq_hit, al_hit, sorted(situacoes_por_manobra.get(numero) or [])))
        processed += 1

        now = time.perf_counter()
        if progress_cb and (processed == 1 or processed == total or (now - last_progress_at) >= 2):
            elapsed = now - started_at
            rate = processed / elapsed if elapsed > 0 else 0.0
            remaining = total - processed
            eta = (remaining / rate) if rate > 0 else 0.0
            last_ms = now - item_started_at
            progress_cb(
                {
                    "processed": processed,
                    "total": total,
                    "elapsed_seconds": elapsed,
                    "eta_seconds": eta,
                    "rate_per_min": rate * 60,
                    "last_seconds": last_ms,
                    "conflitos": len(conflitos),
                    "falhas": len(falhas),
                    "current": numero,
                }
            )
            last_progress_at = now

    finished_at = time.perf_counter()
    return {
        "base": base,
        "data_inicio": data_inicio,
        "data_fim": data_fim,
        "base_equipamentos": sorted(base_eq),
        "base_alimentadores": sorted(base_al),
        "malhas_usadas": malhas,
        "situacoes_usadas": situacoes,
        "situacoes_total": {k: len(v or []) for (k, v) in ids_por_situacao.items()},
        "contagem_por_malha": contagem_por_malha,
        "situacoes_label": {k: SITUACOES_LABEL.get(k, k) for k in situacoes},
        "total_eb": len(ids_por_situacao.get("EB") or []),
        "total_en": len(ids_por_situacao.get("EN") or []),
        "total_unico_sem_base": len(todos_unico),
        "conflitos": [
            {
                "manobra": numero,
                "equipamentos": eq_hit,
                "alimentadores": al_hit,
                "situacoes": sits,
            }
            for (numero, eq_hit, al_hit, sits) in conflitos
        ],
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
            f"PROGRESSO {p['processed']}/{p['total']} | "
            f"tempo={_fmt_seconds(p['elapsed_seconds'])} | "
            f"média={p['rate_per_min']:.1f} manobras/min | "
            f"ETA={_fmt_seconds(p['eta_seconds'])} | "
            f"última={p['last_seconds']:.2f}s"
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
