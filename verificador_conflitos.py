import getpass
import os
import re
import time
import urllib.request
from http.cookiejar import CookieJar

import gdis_http_extrator


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
    return bool(re.fullmatch(r"[A-Z]{3,6}\d{2,4}", s or ""))


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


def run_verificacao(base, data_inicio, data_fim, usuario, senha, progress_cb=None):
    gdis_http_extrator.DATA_INICIO = data_inicio
    gdis_http_extrator.DATA_FIM = data_fim

    jar = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    try:
        jsessionid, _ = gdis_http_extrator._login(opener, usuario, senha)
        _, vs = gdis_http_extrator._open_manobra_page(opener, jsessionid)
    except ValueError as e:
        raise RuntimeError(str(e))

    base_eq, base_al, vs = gdis_http_extrator.extrair_uma_manobra(opener, jsessionid, vs, base)
    base_eq, base_al = _normalize_sets(base_eq, base_al)

    elaborada, vs = gdis_http_extrator.coletar_manobras(opener, jsessionid, vs, "EB")
    enviada, vs = gdis_http_extrator.coletar_manobras(opener, jsessionid, vs, "EN")
    todos = sorted(set(elaborada) | set(enviada))
    if base in todos:
        todos = [x for x in todos if x != base]

    conflitos = []
    falhas = []
    processed = 0
    total = len(todos)
    started_at = time.perf_counter()
    last_progress_at = started_at
    for numero in todos:
        item_started_at = time.perf_counter()
        try:
            eq, al, vs = gdis_http_extrator.extrair_uma_manobra(opener, jsessionid, vs, numero)
            eq, al = _normalize_sets(eq, al)
        except Exception as e:
            falhas.append({"manobra": numero, "erro": str(e)})
            eq = set()
            al = set()

        eq_hit = sorted(base_eq.intersection(eq)) if base_eq else []
        al_hit = sorted(base_al.intersection(al)) if base_al else []
        if eq_hit or al_hit:
            conflitos.append((numero, eq_hit, al_hit))
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
        "total_eb": len(elaborada),
        "total_en": len(enviada),
        "total_unico_sem_base": len(todos),
        "conflitos": [
            {
                "manobra": numero,
                "equipamentos": eq_hit,
                "alimentadores": al_hit,
            }
            for (numero, eq_hit, al_hit) in conflitos
        ],
        "falhas": falhas,
        "elapsed_seconds": finished_at - started_at,
    }


def main():
    base = _parse_base_manobra()
    di, df = _parse_date_range()

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
        r = run_verificacao(base, di, df, usuario, senha, progress_cb=cb)
    except RuntimeError as e:
        print(str(e))
        return

    print(f"BASE {r['base']}")
    print(f"  Equipamentos: {'; '.join(r['base_equipamentos']) if r['base_equipamentos'] else '-'}")
    print(f"  Alimentadores/Subestações: {'; '.join(r['base_alimentadores']) if r['base_alimentadores'] else '-'}")
    print(f"PERÍODO {r['data_inicio']} a {r['data_fim']}")
    print(f"TOTAL EB: {r['total_eb']}")
    print(f"TOTAL EN: {r['total_en']}")
    print(f"TOTAL ÚNICO (sem base): {r['total_unico_sem_base']}")
    print(f"CONFLITOS: {len(r['conflitos'])}")
    if r.get("falhas"):
        print(f"FALHAS: {len(r['falhas'])}")
    for c in r["conflitos"]:
        print(f"MANOBRA {c['manobra']}")
        print(f"  Equipamentos em comum: {'; '.join(c['equipamentos']) if c['equipamentos'] else '-'}")
        print(f"  Alimentadores/Subestações em comum: {'; '.join(c['alimentadores']) if c['alimentadores'] else '-'}")
    if r.get("falhas"):
        for f in r["falhas"][:10]:
            print(f"FALHA {f.get('manobra')}: {f.get('erro')}")
    print(f"TEMPO TOTAL: {_fmt_seconds(time.perf_counter() - started_at)}")


if __name__ == "__main__":
    main()
