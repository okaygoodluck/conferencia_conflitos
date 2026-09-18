import os
import re
import sys

base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

from src.core.conferidor_manobras import (
    _norm_eqpto,
    _norm_str,
    _obter_prefixo_equipamento,
    _re_macro,
)


def test_prefixo_disjuntor_virtual():
    """Verifica se entidade virtual 'DISJUNTOR <ALIM>' recebe prefixo 21 (Disjuntor)."""
    assert _obter_prefixo_equipamento("DISJUNTOR MTZ 007") == "21"
    assert _obter_prefixo_equipamento("DISJUNTOR MTZ 009") == "21"
    assert _obter_prefixo_equipamento("RELIGADOR MTZ 006") == "22"


def test_indexacao_disjuntor_manobra_map():
    """Verifica se itens de SE sem equipamento físico são indexados como DISJUNTOR <ALIM> no manobra_map."""
    manobra_dados = [
        {
            'equipamento': '-',
            'alimentador': 'MTZ 007',
            'texto_linha': '40 MA18 - ABRIR E SINALIZAR DISJUNTOR/RELIGADOR MTZ 007 - - - COM TENSAO COD NÃO',
            'acao_bruta': '40 MA18 - ABRIR E SINALIZAR DISJUNTOR/RELIGADOR MTZ 007',
            'executor': 'COD',
            'posicionamento': 'Não',
            'etapa_nome': '20 MANOBRA MTZ 007',
            'etapa_texto_header': '20 MANOBRA MTZ 007 22/09/2026 06:30'
        },
        {
            'equipamento': '-',
            'alimentador': 'MTZ 007',
            'texto_linha': '20 MA06 - BLOQUEAR RN/ST E SINALIZAR MTZ 007 - - - COM TENSAO COD NÃO',
            'acao_bruta': '20 MA06 - BLOQUEAR RN/ST E SINALIZAR MTZ 007',
            'executor': 'COD',
            'posicionamento': 'Não',
            'etapa_nome': '20 MANOBRA MTZ 007',
            'etapa_texto_header': '20 MANOBRA MTZ 007 22/09/2026 06:30'
        },
        {
            'equipamento': '-',
            'alimentador': 'MTZ 006',
            'texto_linha': '10 MA09 - VERIFICAR SE HA ANORMALIDADE NO ALIMENTADOR MTZ 006 - - - - COD NÃO',
            'acao_bruta': '10 MA09 - VERIFICAR SE HA ANORMALIDADE NO ALIMENTADOR MTZ 006',
            'executor': 'COD',
            'posicionamento': 'Não',
            'etapa_nome': '10 VERIFICACAO PELO COD',
            'etapa_texto_header': '10 VERIFICACAO PELO COD MTZ 007 22/09/2026 06:00'
        }
    ]

    manobra_map = {}
    for idx, item in enumerate(manobra_dados, start=1):
        if 'cronologia' not in item or not item['cronologia']:
            item['cronologia'] = idx
        eq = _norm_eqpto(item.get('equipamento'))
        alim = _norm_str(item.get('alimentador'))

        if (not eq or eq == '-') and alim and alim != '-':
            txt_alvo = (str(item.get('texto_linha', '')) + " " + str(item.get('acao_bruta', ''))).upper()
            m_eq_campo = re.search(r'\b(\d{2}\s*-\s*\d{4,8})\b', txt_alvo)
            if m_eq_campo and not any(w in txt_alvo for w in ["DISJUNTOR", "RELIGADOR"]):
                eq = _norm_eqpto(m_eq_campo.group(1))
            else:
                macros_se = [
                    "MA18", "MA19", "MA06", "MA07", "MA80", "MA81", "MAA6",
                    "MA14", "MA15", "MA16", "MA17", "MA77", "MA78",
                    "MAC2", "MA26", "MA96", "MA97"
                ]
                tem_macro_se = any(re.search(r'\b\d*' + m + r'\b', txt_alvo, re.IGNORECASE) for m in macros_se)
                tem_texto_se = any(w in txt_alvo for w in ["DISJUNTOR", "RELIGADOR", "DISJ", "RELIG", "RN/ST", "SUBESTACAO", "SUBESTAÇÃO"])
                if tem_macro_se or tem_texto_se:
                    eq = f"DISJUNTOR {alim}"

        if not eq or eq == '-':
            continue
        if eq not in manobra_map:
            manobra_map[eq] = []
        manobra_map[eq].append(item)

    # MA18 e MA06 no MTZ 007 devem estar sob DISJUNTOR MTZ 007
    assert "DISJUNTOR MTZ 007" in manobra_map
    assert len(manobra_map["DISJUNTOR MTZ 007"]) == 2

    # MA09 puro de verificação de alimentador não deve criar DISJUNTOR MTZ 006
    assert "DISJUNTOR MTZ 006" not in manobra_map


def test_disjuntor_se_falha_inversao_e_abertura_duplicada():
    """
    Simula o cenário exato do log:
    - Etapa 20: MA18 (Abertura do Disjuntor MTZ 007)
    - Etapa 40: MA81 (Entrega disjuntor sem retorno)
    - Etapa 50: MAA6 (Autorização para normalizar)
    - Etapa 70: MA18 (Repetição errônea de abertura em vez de MA19)
    Deve falhar na Regra 22 (saldo MA18 > MA19) e na Regra 31 (tentativa de abertura em disjuntor já aberto).
    """
    eq = "DISJUNTOR MTZ 007"
    manobra_items = [
        {
            'texto_linha': '40 MA18 - ABRIR E SINALIZAR DISJUNTOR/RELIGADOR MTZ 007 - - - COM TENSAO COD NÃO',
            'etapa_nome': '20 MANOBRA MTZ 007',
            'cronologia': 1
        },
        {
            'texto_linha': '10 MA81 - ENTREGAR COD/AT DISJ/RELIG ABERTO S TENSAO RETORNO MTZ 007 - - - - COD NÃO',
            'etapa_nome': '40 AUTORIZACAO DO PLE/BI',
            'cronologia': 2
        },
        {
            'texto_linha': '20 MAA6 - RECEBER COD/AT AUTORIZACAO P NORMALIZAR DISJ/RELIG MTZ 007 - - - - COD NÃO',
            'etapa_nome': '50 DISPENSA DO PLE/BI',
            'cronologia': 3
        },
        {
            'texto_linha': '40 MA18 - ABRIR E SINALIZAR DISJUNTOR/RELIGADOR MTZ 007 - - - COM TENSAO COD NÃO',
            'etapa_nome': '70 MANOBRA MTZ 007',
            'cronologia': 4
        }
    ]

    # --- SIMULAÇÃO REGRA 31 ---
    macros_abertura = re.compile(r'\b\d*(MA01|MA31|MA30|MA18|MA22|MA24|MA54|MA56|MAA9)\b(?!\s*-\s*OUTROS)')
    macros_fechamento = re.compile(r'\b\d*(MA02|MA66|MA67|MA19|MA23|MA25|MA55|MA57|MAB1)\b(?!\s*-\s*OUTROS)')

    posope = 'F' if str(eq).startswith("DISJUNTOR ") else 'A'
    estado_simulado = posope
    erro_31 = []

    for mi in manobra_items:
        txt = mi['texto_linha'].upper()
        is_abertura = bool(macros_abertura.search(txt) or re.search(r'\bABRIR\b', txt))
        is_fechamento = bool(macros_fechamento.search(txt) or re.search(r'\bFECHAR\b', txt))

        if is_abertura:
            if estado_simulado == 'A':
                if str(eq).startswith("DISJUNTOR "):
                    msg = "Tentativa de Abertura (MA18) em disjuntor que já se encontra aberto (POSOPE=A)"
                else:
                    msg = "Tentativa de Abertura em equipamento que já consta como Aberto (NA/POSOPE=A)"
                erro_31.append(msg)
            estado_simulado = 'A'
        elif is_fechamento:
            if estado_simulado == 'F':
                erro_31.append("Tentativa de Fechamento")
            estado_simulado = 'F'

    # Regra 31 deve ter detectado a tentativa de abertura consecutiva
    assert len(erro_31) == 1
    assert "Tentativa de Abertura (MA18) em disjuntor que já se encontra aberto (POSOPE=A)" in erro_31[0]

    # --- SIMULAÇÃO REGRA 22 ---
    rastreamento_inversas = {
        "Disjuntor/Relig. (MA18/MA19)": (["MA18"], ["MA19"]),
        "Entrega/Liberação PLE (MA80/MA81 -> MAA6)": (["MA80", "MA81"], ["MAA6"])
    }
    saldos = {k: 0 for k in rastreamento_inversas}

    for mi in manobra_items:
        txt = mi['texto_linha'].upper()
        for nome_grupo, (aberturas, fechamentos) in rastreamento_inversas.items():
            for m_ab in aberturas:
                if re.search(_re_macro(m_ab), txt):
                    saldos[nome_grupo] += 1
            for m_fe in fechamentos:
                if re.search(_re_macro(m_fe), txt):
                    saldos[nome_grupo] -= 1

    # Disjuntor MA18/MA19 deve ter saldo 2 (duas aberturas e nenhum fechamento)
    assert saldos["Disjuntor/Relig. (MA18/MA19)"] == 2
    # PLE MA81/MAA6 deve estar equilibrado (1 entrega, 1 autorização para normalizar)
    assert saldos["Entrega/Liberação PLE (MA80/MA81 -> MAA6)"] == 0


def test_disjuntor_se_inversao_correta_ma19():
    """
    Simula a manobra devidamente corrigida:
    - Etapa 20: MA18 (Abertura do Disjuntor MTZ 007)
    - Etapa 40: MA81 (Entrega disjuntor sem retorno)
    - Etapa 50: MAA6 (Autorização para normalizar)
    - Etapa 70: MA19 (Recomposição / Fechamento do Disjuntor MTZ 007)
    Deve passar com OK nas Regras 22 e 31.
    """
    eq = "DISJUNTOR MTZ 007"
    manobra_items = [
        {
            'texto_linha': '40 MA18 - ABRIR E SINALIZAR DISJUNTOR/RELIGADOR MTZ 007 - - - COM TENSAO COD NÃO',
            'cronologia': 1
        },
        {
            'texto_linha': '10 MA81 - ENTREGAR COD/AT DISJ/RELIG ABERTO S TENSAO RETORNO MTZ 007 - - - - COD NÃO',
            'cronologia': 2
        },
        {
            'texto_linha': '20 MAA6 - RECEBER COD/AT AUTORIZACAO P NORMALIZAR DISJ/RELIG MTZ 007 - - - - COD NÃO',
            'cronologia': 3
        },
        {
            'texto_linha': '40 MA19 - RETIRAR SINALIZACAO E FECHAR DISJUNTOR/RELIGADOR MTZ 007 - - - COM TENSAO COD NÃO',
            'cronologia': 4
        }
    ]

    # Regra 31
    macros_abertura = re.compile(r'\b\d*(MA01|MA31|MA30|MA18|MA22|MA24|MA54|MA56|MAA9)\b(?!\s*-\s*OUTROS)')
    macros_fechamento = re.compile(r'\b\d*(MA02|MA66|MA67|MA19|MA23|MA25|MA55|MA57|MAB1)\b(?!\s*-\s*OUTROS)')

    posope = 'F'
    estado_simulado = posope
    erro_31 = []

    for mi in manobra_items:
        txt = mi['texto_linha'].upper()
        is_abertura = bool(macros_abertura.search(txt) or re.search(r'\bABRIR\b', txt))
        is_fechamento = bool(macros_fechamento.search(txt) or re.search(r'\bFECHAR\b', txt))

        if is_abertura:
            if estado_simulado == 'A':
                erro_31.append("Tentativa de Abertura")
            estado_simulado = 'A'
        elif is_fechamento:
            if estado_simulado == 'F':
                erro_31.append("Tentativa de Fechamento")
            estado_simulado = 'F'

    assert len(erro_31) == 0, f"Não deve haver erro de estado, encontrado: {erro_31}"
    assert estado_simulado == 'F', "O estado final do disjuntor deve ser FECHADO (F)"

    # Regra 22
    rastreamento_inversas = {
        "Disjuntor/Relig. (MA18/MA19)": (["MA18"], ["MA19"]),
        "Entrega/Liberação PLE (MA80/MA81 -> MAA6)": (["MA80", "MA81"], ["MAA6"])
    }
    saldos = {k: 0 for k in rastreamento_inversas}

    for mi in manobra_items:
        txt = mi['texto_linha'].upper()
        for nome_grupo, (aberturas, fechamentos) in rastreamento_inversas.items():
            for m_ab in aberturas:
                if re.search(_re_macro(m_ab), txt):
                    saldos[nome_grupo] += 1
            for m_fe in fechamentos:
                if re.search(_re_macro(m_fe), txt):
                    saldos[nome_grupo] -= 1

    assert saldos["Disjuntor/Relig. (MA18/MA19)"] == 0
    assert saldos["Entrega/Liberação PLE (MA80/MA81 -> MAA6)"] == 0


def test_manobra_245592175_completa_detecta_erro_disjuntores():
    """
    Reproduz o lote completo da manobra 245592175 fornecido no log do usuário.
    Garante que:
    1. DISJUNTOR MTZ 007 e DISJUNTOR MTZ 009 são gerados no manobra_map.
    2. Ambos apresentam falha na Regra 22 (saldo de MA18 sem MA19).
    3. Ambos apresentam falha na Regra 31 (tentativa de abertura em disjuntor já aberto).
    """
    # Dados extraídos exatamente do log do usuário
    manobra_dados = [
        # Etapa 10: Verificação COD
        {'equipamento': '-', 'alimentador': 'MTZ 006', 'texto_linha': '10 MA09 - VERIFICAR SE HA ANORMALIDADE NO ALIMENTADOR MTZ 006 - - - - COD NÃO', 'acao_bruta': '10 MA09'},
        {'equipamento': '-', 'alimentador': 'MTZ 007', 'texto_linha': '20 MA09 - VERIFICAR SE HA ANORMALIDADE NO ALIMENTADOR MTZ 007 - - - - COD NÃO', 'acao_bruta': '20 MA09'},
        {'equipamento': '-', 'alimentador': 'MTZ 009', 'texto_linha': '30 MA09 - VERIFICAR SE HA ANORMALIDADE NO ALIMENTADOR MTZ 009 - - - - COD NÃO', 'acao_bruta': '30 MA09'},
        {'equipamento': '-', 'alimentador': 'MTZ 012', 'texto_linha': '40 MA09 - VERIFICAR SE HA ANORMALIDADE NO ALIMENTADOR MTZ 012 - - - - COD NÃO', 'acao_bruta': '40 MA09'},
        # Etapa 20: Manobra MTZ 007 06:30
        {'equipamento': '-', 'alimentador': 'MTZ 006', 'texto_linha': '10 MA06 - BLOQUEAR RN/ST E SINALIZAR MTZ 006 - - - COM TENSAO COD NÃO', 'acao_bruta': '10 MA06'},
        {'equipamento': '-', 'alimentador': 'MTZ 007', 'texto_linha': '20 MA06 - BLOQUEAR RN/ST E SINALIZAR MTZ 007 - - - COM TENSAO COD NÃO', 'acao_bruta': '20 MA06'},
        {'equipamento': '28 - 296767', 'alimentador': 'MTZ 007', 'texto_linha': '30 MA02 - FECHAR EQUIPAMENTO 28 - 296767 MTZ 007 COM TENSAO REGIAO SIM', 'acao_bruta': '30 MA02'},
        {'equipamento': '-', 'alimentador': 'MTZ 007', 'texto_linha': '40 MA18 - ABRIR E SINALIZAR DISJUNTOR/RELIGADOR MTZ 007 - - - COM TENSAO COD NÃO', 'acao_bruta': '40 MA18'},
        {'equipamento': '-', 'alimentador': 'MTZ 007', 'texto_linha': '50 MA07 - RETIRAR SINALIZACAO E NORMALIZAR RN/ST MTZ 007 - - - COM TENSAO COD NÃO', 'acao_bruta': '50 MA07'},
        {'equipamento': '-', 'alimentador': 'MTZ 006', 'texto_linha': '60 MA07 - RETIRAR SINALIZACAO E NORMALIZAR RN/ST MTZ 006 - - - COM TENSAO COD NÃO', 'acao_bruta': '60 MA07'},
        {'equipamento': '28 - 296761', 'alimentador': 'MTZ 007', 'texto_linha': '70 MA31 - ABRIR E SINALIZAR EQUIPAMENTO 28 - 296761 MTZ 007 COM CARGA REGIAO SIM', 'acao_bruta': '70 MA31'},
        # Etapa 30: Manobra MTZ 007 07:30
        {'equipamento': '-', 'alimentador': 'MTZ 012', 'texto_linha': '10 MA06 - BLOQUEAR RN/ST E SINALIZAR MTZ 012 - - - COM TENSAO COD NÃO', 'acao_bruta': '10 MA06'},
        {'equipamento': '-', 'alimentador': 'MTZ 009', 'texto_linha': '20 MA06 - BLOQUEAR RN/ST E SINALIZAR MTZ 009 - - - COM TENSAO COD NÃO', 'acao_bruta': '20 MA06'},
        {'equipamento': '28 - 296763', 'alimentador': 'MTZ 009', 'texto_linha': '30 MA02 - FECHAR EQUIPAMENTO 28 - 296763 MTZ 009 COM TENSAO REGIAO SIM', 'acao_bruta': '30 MA02'},
        {'equipamento': '-', 'alimentador': 'MTZ 009', 'texto_linha': '40 MA18 - ABRIR E SINALIZAR DISJUNTOR/RELIGADOR MTZ 009 - - - COM TENSAO COD NÃO', 'acao_bruta': '40 MA18'},
        {'equipamento': '-', 'alimentador': 'MTZ 009', 'texto_linha': '50 MA07 - RETIRAR SINALIZACAO E NORMALIZAR RN/ST MTZ 009 - - - COM TENSAO COD NÃO', 'acao_bruta': '50 MA07'},
        {'equipamento': '-', 'alimentador': 'MTZ 012', 'texto_linha': '60 MA07 - RETIRAR SINALIZACAO E NORMALIZAR RN/ST MTZ 012 - - - COM TENSAO COD NÃO', 'acao_bruta': '60 MA07'},
        {'equipamento': '28 - 296760', 'alimentador': 'MTZ 009', 'texto_linha': '70 MA31 - ABRIR E SINALIZAR EQUIPAMENTO 28 - 296760 MTZ 009 COM CARGA REGIAO SIM', 'acao_bruta': '70 MA31'},
        # Etapa 40: Autorização PLE
        {'equipamento': '-', 'alimentador': 'MTZ 007', 'texto_linha': '10 MA81 - ENTREGAR COD/AT DISJ/RELIG ABERTO S TENSAO RETORNO MTZ 007 - - - - COD NÃO', 'acao_bruta': '10 MA81'},
        {'equipamento': '-', 'alimentador': 'MTZ 009', 'texto_linha': '20 MA81 - ENTREGAR COD/AT DISJ/RELIG ABERTO S TENSAO RETORNO MTZ 009 - - - - COD NÃO', 'acao_bruta': '20 MA81'},
        # Etapa 50: Dispensa PLE
        {'equipamento': '-', 'alimentador': 'MTZ 009', 'texto_linha': '10 MAA6 - RECEBER COD/AT AUTORIZACAO P NORMALIZAR DISJ/RELIG MTZ 009 - - - - COD NÃO', 'acao_bruta': '10 MAA6'},
        {'equipamento': '-', 'alimentador': 'MTZ 007', 'texto_linha': '20 MAA6 - RECEBER COD/AT AUTORIZACAO P NORMALIZAR DISJ/RELIG MTZ 007 - - - - COD NÃO', 'acao_bruta': '20 MAA6'},
        # Etapa 60: Manobra MTZ 007 15:30 (Recomposição MTZ 009)
        {'equipamento': '28 - 296760', 'alimentador': 'MTZ 009', 'texto_linha': '10 MA66 - RETIRAR SINALIZACAO E FECHAR EQUIPAMENTO 28 - 296760 MTZ 009 COM CARGA REGIAO SIM', 'acao_bruta': '10 MA66'},
        {'equipamento': '-', 'alimentador': 'MTZ 012', 'texto_linha': '20 MA06 - BLOQUEAR RN/ST E SINALIZAR MTZ 012 - - - COM TENSAO COD NÃO', 'acao_bruta': '20 MA06'},
        {'equipamento': '-', 'alimentador': 'MTZ 009', 'texto_linha': '30 MA06 - BLOQUEAR RN/ST E SINALIZAR MTZ 009 - - - COM TENSAO COD NÃO', 'acao_bruta': '30 MA06'},
        {'equipamento': '-', 'alimentador': 'MTZ 009', 'texto_linha': '40 MA18 - ABRIR E SINALIZAR DISJUNTOR/RELIGADOR MTZ 009 - - - COM TENSAO COD NÃO', 'acao_bruta': '40 MA18'},  # ERRO: MA18 repetido!
        {'equipamento': '28 - 296763', 'alimentador': 'MTZ 009', 'texto_linha': '50 MA01 - ABRIR EQUIPAMENTO 28 - 296763 MTZ 009 COM TENSAO REGIAO SIM', 'acao_bruta': '50 MA01'},
        {'equipamento': '-', 'alimentador': 'MTZ 009', 'texto_linha': '60 MA07 - RETIRAR SINALIZACAO E NORMALIZAR RN/ST MTZ 009 - - - COM TENSAO COD NÃO', 'acao_bruta': '60 MA07'},
        {'equipamento': '-', 'alimentador': 'MTZ 012', 'texto_linha': '70 MA07 - RETIRAR SINALIZACAO E NORMALIZAR RN/ST MTZ 012 - - - COM TENSAO COD NÃO', 'acao_bruta': '70 MA07'},
        # Etapa 70: Manobra MTZ 007 15:30 (Recomposição MTZ 007)
        {'equipamento': '28 - 296761', 'alimentador': 'MTZ 007', 'texto_linha': '10 MA66 - RETIRAR SINALIZACAO E FECHAR EQUIPAMENTO 28 - 296761 MTZ 007 COM CARGA REGIAO SIM', 'acao_bruta': '10 MA66'},
        {'equipamento': '-', 'alimentador': 'MTZ 006', 'texto_linha': '20 MA06 - BLOQUEAR RN/ST E SINALIZAR MTZ 006 - - - COM TENSAO COD NÃO', 'acao_bruta': '20 MA06'},
        {'equipamento': '-', 'alimentador': 'MTZ 007', 'texto_linha': '30 MA06 - BLOQUEAR RN/ST E SINALIZAR MTZ 007 - - - COM TENSAO COD NÃO', 'acao_bruta': '30 MA06'},
        {'equipamento': '-', 'alimentador': 'MTZ 007', 'texto_linha': '40 MA18 - ABRIR E SINALIZAR DISJUNTOR/RELIGADOR MTZ 007 - - - COM TENSAO COD NÃO', 'acao_bruta': '40 MA18'},  # ERRO: MA18 repetido!
        {'equipamento': '28 - 296767', 'alimentador': 'MTZ 007', 'texto_linha': '50 MA01 - ABRIR EQUIPAMENTO 28 - 296767 MTZ 007 COM TENSAO REGIAO SIM', 'acao_bruta': '50 MA01'},
        {'equipamento': '-', 'alimentador': 'MTZ 007', 'texto_linha': '60 MA07 - RETIRAR SINALIZACAO E NORMALIZAR RN/ST MTZ 007 - - - COM TENSAO COD NÃO', 'acao_bruta': '60 MA07'},
        {'equipamento': '-', 'alimentador': 'MTZ 006', 'texto_linha': '70 MA07 - RETIRAR SINALIZACAO E NORMALIZAR RN/ST MTZ 006 - - - COM TENSAO COD NÃO', 'acao_bruta': '70 MA07'},
    ]

    manobra_map = {}
    for idx, item in enumerate(manobra_dados, start=1):
        if 'cronologia' not in item or not item['cronologia']:
            item['cronologia'] = idx
        eq = _norm_eqpto(item.get('equipamento'))
        alim = _norm_str(item.get('alimentador'))

        if (not eq or eq == '-') and alim and alim != '-':
            txt_alvo = (str(item.get('texto_linha', '')) + " " + str(item.get('acao_bruta', ''))).upper()
            m_eq_campo = re.search(r'\b(\d{2}\s*-\s*\d{4,8})\b', txt_alvo)
            if m_eq_campo and not any(w in txt_alvo for w in ["DISJUNTOR", "RELIGADOR"]):
                eq = _norm_eqpto(m_eq_campo.group(1))
            else:
                macros_se = [
                    "MA18", "MA19", "MA06", "MA07", "MA80", "MA81", "MAA6",
                    "MA14", "MA15", "MA16", "MA17", "MA77", "MA78",
                    "MAC2", "MA26", "MA96", "MA97"
                ]
                tem_macro_se = any(re.search(r'\b\d*' + m + r'\b', txt_alvo, re.IGNORECASE) for m in macros_se)
                tem_texto_se = any(w in txt_alvo for w in ["DISJUNTOR", "RELIGADOR", "DISJ", "RELIG", "RN/ST", "SUBESTACAO", "SUBESTAÇÃO"])
                if tem_macro_se or tem_texto_se:
                    eq = f"DISJUNTOR {alim}"

        if not eq or eq == '-':
            continue
        if eq not in manobra_map:
            manobra_map[eq] = []
        manobra_map[eq].append(item)

    # Verifica indexação dos dois disjuntores da SE
    assert "DISJUNTOR MTZ 007" in manobra_map
    assert "DISJUNTOR MTZ 009" in manobra_map

    # Avalia ambos os disjuntores
    macros_abertura = re.compile(r'\b\d*(MA01|MA31|MA30|MA18|MA22|MA24|MA54|MA56|MAA9)\b(?!\s*-\s*OUTROS)')
    macros_fechamento = re.compile(r'\b\d*(MA02|MA66|MA67|MA19|MA23|MA25|MA55|MA57|MAB1)\b(?!\s*-\s*OUTROS)')

    for eq_disj in ["DISJUNTOR MTZ 007", "DISJUNTOR MTZ 009"]:
        items = manobra_map[eq_disj]
        
        # Regra 31
        posope = 'F'
        estado_simulado = posope
        erros_31 = []
        for mi in items:
            txt = mi['texto_linha'].upper()
            is_ab = bool(macros_abertura.search(txt) or re.search(r'\bABRIR\b', txt))
            is_fe = bool(macros_fechamento.search(txt) or re.search(r'\bFECHAR\b', txt))
            if is_ab:
                if estado_simulado == 'A':
                    erros_31.append("Tentativa de Abertura (MA18) em disjuntor que já se encontra aberto (POSOPE=A)")
                estado_simulado = 'A'
            elif is_fe:
                estado_simulado = 'F'

        assert len(erros_31) == 1, f"Esperava erro de abertura duplicada para {eq_disj}, obteve {erros_31}"

        # Regra 22
        rastreio = {
            "Disjuntor/Relig. (MA18/MA19)": (["MA18"], ["MA19"]),
            "Entrega/Liberação PLE (MA80/MA81 -> MAA6)": (["MA80", "MA81"], ["MAA6"]),
            "Sinalização/RN/ST (MA06/MA07)": (["MA06"], ["MA07"])
        }
        saldos = {k: 0 for k in rastreio}
        for mi in items:
            txt = mi['texto_linha'].upper()
            for g, (abs_m, fes_m) in rastreio.items():
                for a in abs_m:
                    if re.search(_re_macro(a), txt): saldos[g] += 1
                for f in fes_m:
                    if re.search(_re_macro(f), txt): saldos[g] -= 1

        # Saldo MA18 deve ser 2 (duas aberturas, 0 fechamentos)
        assert saldos["Disjuntor/Relig. (MA18/MA19)"] == 2
        # PLE deve estar zerado
        assert saldos["Entrega/Liberação PLE (MA80/MA81 -> MAA6)"] == 0
        # RN/ST deve estar zerado
        assert saldos["Sinalização/RN/ST (MA06/MA07)"] == 0


def test_procedimentos_etapa_nao_criam_disjuntor_virtual():
    """
    Verifica se macros procedimentais de etapa (MA40, MA41, MA42, MA43) e siglas de SE pura (JQU)
    NÃO são convertidas em entidade virtual 'DISJUNTOR <ALIM>' nem disparam falsos erros nas Regras 22 e 30.
    Cenário real da Manobra 246043309.
    """
    from src.core.conferidor_manobras import (
        _norm_eqpto,
        _norm_str,
    )

    manobra_dados = [
        {
            'equipamento': '-',
            'alimentador': 'JQU',
            'texto_linha': '10 MA40 - SOLICITAR AO COD AUTORIZACAO PARA DESLIGAMENTO JQU - - - - SUPERVISOR NÃO',
            'acao_bruta': '10 MA40 - SOLICITAR AO COD AUTORIZACAO PARA DESLIGAMENTO JQU',
            'executor': 'SUPERVISOR',
            'posicionamento': 'Não',
            'etapa_nome': '40 DESLIGAMENTO JQU 002',
            'cronologia': 1
        },
        {
            'equipamento': '-',
            'alimentador': 'JQU',
            'texto_linha': '40 MA42 - TESTAR E ATERRAR OS CIRCUITOS JQU - - - - SUPERVISOR NÃO',
            'acao_bruta': '40 MA42 - TESTAR E ATERRAR OS CIRCUITOS JQU',
            'executor': 'SUPERVISOR',
            'posicionamento': 'Não',
            'etapa_nome': '40 DESLIGAMENTO JQU 002',
            'cronologia': 2
        },
        {
            'equipamento': '-',
            'alimentador': 'JQU',
            'texto_linha': '10 MA43 - RETIRAR ATERRAMENTO DOS CIRCUITOS JQU - - - - SUPERVISOR NÃO',
            'acao_bruta': '10 MA43 - RETIRAR ATERRAMENTO DOS CIRCUITOS JQU',
            'executor': 'SUPERVISOR',
            'posicionamento': 'Não',
            'etapa_nome': '50 RELIGAMENTO JQU 002',
            'cronologia': 3
        },
        {
            'equipamento': '-',
            'alimentador': 'JQU',
            'texto_linha': '40 MA41 - INFORMAR AO COD RELIGAMENTO COM HORARIO JQU - - - - SUPERVISOR NÃO',
            'acao_bruta': '40 MA41 - INFORMAR AO COD RELIGAMENTO COM HORARIO JQU',
            'executor': 'SUPERVISOR',
            'posicionamento': 'Não',
            'etapa_nome': '50 RELIGAMENTO JQU 002',
            'cronologia': 4
        }
    ]

    manobra_map = {}
    for idx, item in enumerate(manobra_dados, start=1):
        if 'cronologia' not in item or not item['cronologia']:
            item['cronologia'] = idx
        eq = _norm_eqpto(item.get('equipamento'))
        alim = _norm_str(item.get('alimentador'))

        if (not eq or eq == '-') and alim and alim != '-':
            txt_alvo = (str(item.get('texto_linha', '')) + " " + str(item.get('acao_bruta', ''))).upper()
            is_procedimento = bool(re.search(r'\b\d*(MA40|MA41|MA42|MA43|MAA7|MAA8|MA09|MA10|MA11|MA12|MA13)\b', txt_alvo))
            if not is_procedimento:
                m_eq_campo = re.search(r'\b(\d{2}\s*-\s*\d{4,8})\b', txt_alvo)
                tem_texto_se = bool(re.search(r'\b(DISJUNTOR|RELIGADOR|DISJ\b|RN/ST|SUBESTA[CÇ][AÃ]O)\b', txt_alvo))
                if m_eq_campo and not tem_texto_se:
                    eq = _norm_eqpto(m_eq_campo.group(1))
                else:
                    macros_se = [
                        "MA18", "MA19", "MA06", "MA07", "MA80", "MA81", "MAA6",
                        "MA14", "MA15", "MA16", "MA17", "MA77", "MA78",
                        "MAC2", "MA26", "MA96", "MA97"
                    ]
                    tem_macro_se = any(re.search(r'\b\d*' + m + r'\b', txt_alvo, re.IGNORECASE) for m in macros_se)
                    tem_digito_alim = bool(re.search(r'\d', alim))
                    is_op_disj = bool(re.search(r'\b\d*(MA18|MA19)\b', txt_alvo)) or ("DISJUNTOR" in txt_alvo)
                    if (tem_macro_se or tem_texto_se) and (tem_digito_alim or is_op_disj):
                        eq = f"DISJUNTOR {alim}"

        if not eq or eq == '-':
            continue
        if eq not in manobra_map:
            manobra_map[eq] = []
        manobra_map[eq].append(item)

    # Nenhuma entidade 'DISJUNTOR JQU' deve existir
    assert "DISJUNTOR JQU" not in manobra_map
    assert len(manobra_map) == 0


def test_regra46_banco_regulador_parceiro():
    """
    Verifica se a Regra 46 reconhece a proteção em banco de RT:
    Se a chave invertida é 120858, mas o operador aplicou MA35 e MA36 na unidade 120857
    (do mesmo banco/local 2121), não deve haver falha na Regra 46.
    """
    from src.core.rede_grafo import RedeGrafoAlimentador

    dados_rede = {
        "alimentador": "JQU 002",
        "root": {"id": "SE_JQU", "refalm": "JQU 002"},
        "nos": [
            {"id": "SE_JQU", "numeq": "SE_JQU", "posope": "F"},
            {"id": "RT_1", "numeq": "02 - 120857", "tipoeq": "02", "idblococ": "BLOCO_RT_2121", "local": "2121", "posope": "F"},
            {"id": "RT_2", "numeq": "120858", "tipoeq": "02", "idblococ": "BLOCO_RT_2121", "local": "2121", "posope": "F"},
            {"id": "N_CARGA", "numeq": "N_CARGA", "posope": "F"},
            {"id": "CH_SOC", "numeq": "22 - 382500", "tipoeq": "22", "posope": "A"},
            {"id": "SE_EXT", "numeq": "SE_EXT", "posope": "F"}
        ],
        "arestas": [
            {"id": "SE_JQU*RT_1"},
            {"id": "RT_1*RT_2"},
            {"id": "RT_2*N_CARGA"},
            {"id": "N_CARGA*CH_SOC"},
            {"id": "CH_SOC*SE_EXT"}
        ]
    }

    grafo = RedeGrafoAlimentador(dados_rede)

    # Simula manobra com MA35 para 02 - 120857, fechamento de 22 - 382500, e MA36 para 02 - 120857
    manobra = [
        {
            "equipamento": "02 - 120857",
            "texto_linha": "60 MA35 - COLOCAR RT NO NEUTRO 02 - 120857 LOCAL 2121",
            "etapa_nome": "20 MANOBRA",
            "local": "2121"
        },
        {
            "equipamento": "22 - 382500",
            "texto_linha": "20 MA02 - FECHAR EQUIPAMENTO 22 - 382500",
            "etapa_nome": "30 MANOBRA",
            "local": "2124"
        },
        {
            "equipamento": "02 - 120857",
            "texto_linha": "60 MA36 - COLOCAR RT EM SERVICO 02 - 120857 LOCAL 2121",
            "etapa_nome": "70 MANOBRA",
            "local": "2121"
        }
    ]

    res = grafo.simular_manobra(manobra)

    # Não deve apontar ausência de MA35/MA77 nem ausência de MA36 para 120858
    assert len(res["rt_sem_ma35_ou_ma77"]) == 0
    assert len(res["rt_sem_ma36_retorno"]) == 0


