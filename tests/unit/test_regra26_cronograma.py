import re
from datetime import datetime, timedelta


def simular_regra_26(manobra_map, dt_sol_ini_str, dt_sol_fim_str, sol_dict=None):
    """Função utilitária que replica fielmente a lógica da Regra 26 de conferidor_manobras.py."""
    if sol_dict is None:
        sol_dict = {}

    def parse_dt(s):
        if not s:
            return None
        m = re.search(r'(\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2})', str(s))
        if m:
            return datetime.strptime(m.group(1), "%d/%m/%Y %H:%M")
        return None

    dt_sol_ini = parse_dt(dt_sol_ini_str)
    dt_sol_fim = parse_dt(dt_sol_fim_str)

    resultados = {}

    for eq, items in manobra_map.items():
        todos_horarios_validos = []
        horarios_deslig = []

        for mi in items:
            dt_str = mi.get('etapa_texto_header', '')
            etapa_full = (mi.get('etapa_nome', '') + ' ' + dt_str).upper()

            is_preparacao = any(x in etapa_full for x in ["PREPARACAO", "PREPARAÇÃO", "COMUNICACAO", "COMUNICAÇÃO", "REGISTRO", "OBSERVACAO", "OBSERVAÇÃO"])
            m_dt = re.search(r'(\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2})', dt_str)
            if m_dt:
                dt_obj = parse_dt(m_dt.group(1))
                if dt_obj and not is_preparacao:
                    todos_horarios_validos.append(dt_obj)
                    if "DESLIGAMENTO" in etapa_full:
                        horarios_deslig.append(dt_obj)

        if not todos_horarios_validos:
            continue

        ini_man_real = min(horarios_deslig) if horarios_deslig else None
        fim_man = max(todos_horarios_validos)

        lim_ini = dt_sol_ini
        lim_fim = dt_sol_fim

        info_sol = sol_dict.get(eq)
        if info_sol:
            dt_indiv_ini = parse_dt(info_sol.get('inicio', ''))
            dt_indiv_fim = parse_dt(info_sol.get('termino', ''))
            if dt_indiv_ini:
                lim_ini = dt_indiv_ini
            if dt_indiv_fim:
                lim_fim = dt_indiv_fim

        falhas_r26 = []
        alertas_r26 = []

        if lim_ini and ini_man_real and lim_fim and fim_man:
            data_ref = ini_man_real.date()
            sol_ini_ref = datetime.combine(data_ref, lim_ini.time())

            if lim_fim.time() < lim_ini.time():
                sol_fim_ref = datetime.combine(data_ref + timedelta(days=1), lim_fim.time())
            else:
                sol_fim_ref = datetime.combine(data_ref, lim_fim.time())

            ini_man_ref = datetime.combine(data_ref, ini_man_real.time())
            if fim_man.time() < ini_man_real.time():
                fim_man_ref = datetime.combine(data_ref + timedelta(days=1), fim_man.time())
            else:
                fim_man_ref = datetime.combine(data_ref, fim_man.time())

            if ini_man_ref < sol_ini_ref:
                falhas_r26.append(f"Início antecipado ({ini_man_real.strftime('%H:%M')}) vs Autorizado ({lim_ini.strftime('%H:%M')})")

            if fim_man_ref > sol_fim_ref:
                falhas_r26.append(f"Término tardio ({fim_man.strftime('%H:%M')}) vs Autorizado ({lim_fim.strftime('%H:%M')})")

            if ini_man_real.date() != lim_ini.date():
                alertas_r26.append(f"Data programada ({ini_man_real.strftime('%d/%m/%Y')}) difere da data da solicitação ({lim_ini.strftime('%d/%m/%Y')})")

        resultados[eq] = {"falhas": falhas_r26, "alertas": alertas_r26}

    return resultados


def test_regra26_cenario_manobra_246074289():
    """
    Cenário real da Manobra 246074289:
    - Solicitação: 25/09/2026 11:00 às 25/09/2026 17:00
    - Manobra: 23/09/2026 11:00 (Desligamento) às 23/09/2026 17:00 (Religamento)
    Deve aprovar sem falhas (horários 11:00 às 17:00 idênticos), gerando apenas alerta de data diferente.
    """
    manobra_map = {
        "24 - 1313": [
            {
                "etapa_nome": "40 DESLIGAMENTO PTHD217",
                "etapa_texto_header": "40 DESLIGAMENTO PTHD217 23/09/2026 11:00"
            },
            {
                "etapa_nome": "50 RELIGAMENTO PTHD217",
                "etapa_texto_header": "50 RELIGAMENTO PTHD217 23/09/2026 17:00"
            }
        ]
    }

    res = simular_regra_26(manobra_map, "25/09/2026 11:00", "25/09/2026 17:00")
    assert len(res["24 - 1313"]["falhas"]) == 0
    assert len(res["24 - 1313"]["alertas"]) == 1
    assert "23/09/2026" in res["24 - 1313"]["alertas"][0]
    assert "25/09/2026" in res["24 - 1313"]["alertas"][0]


def test_regra26_detecta_inicio_antecipado_real():
    """Detecta início antecipado quando o desligamento começa antes do horário autorizado."""
    manobra_map = {
        "24 - 1313": [
            {
                "etapa_nome": "40 DESLIGAMENTO",
                "etapa_texto_header": "40 DESLIGAMENTO 23/09/2026 10:30"
            },
            {
                "etapa_nome": "50 RELIGAMENTO",
                "etapa_texto_header": "50 RELIGAMENTO 23/09/2026 17:00"
            }
        ]
    }

    res = simular_regra_26(manobra_map, "23/09/2026 11:00", "23/09/2026 17:00")
    assert len(res["24 - 1313"]["falhas"]) == 1
    assert "Início antecipado (10:30) vs Autorizado (11:00)" in res["24 - 1313"]["falhas"][0]


def test_regra26_detecta_termino_tardio_real():
    """Detecta término tardio quando o religamento ultrapassa o horário autorizado."""
    manobra_map = {
        "24 - 1313": [
            {
                "etapa_nome": "40 DESLIGAMENTO",
                "etapa_texto_header": "40 DESLIGAMENTO 23/09/2026 11:00"
            },
            {
                "etapa_nome": "50 RELIGAMENTO",
                "etapa_texto_header": "50 RELIGAMENTO 23/09/2026 17:30"
            }
        ]
    }

    res = simular_regra_26(manobra_map, "23/09/2026 11:00", "23/09/2026 17:00")
    assert len(res["24 - 1313"]["falhas"]) == 1
    assert "Término tardio (17:30) vs Autorizado (17:00)" in res["24 - 1313"]["falhas"][0]


def test_regra26_manobra_noturna():
    """Valida janela noturna que vira a meia-noite (ex: 22:00 às 04:00 do dia seguinte)."""
    manobra_map = {
        "24 - 1313": [
            {
                "etapa_nome": "40 DESLIGAMENTO",
                "etapa_texto_header": "40 DESLIGAMENTO 23/09/2026 22:00"
            },
            {
                "etapa_nome": "50 RELIGAMENTO",
                "etapa_texto_header": "50 RELIGAMENTO 24/09/2026 04:00"
            }
        ]
    }

    res = simular_regra_26(manobra_map, "23/09/2026 22:00", "24/09/2026 04:00")
    assert len(res["24 - 1313"]["falhas"]) == 0
