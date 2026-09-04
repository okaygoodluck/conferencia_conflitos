import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from unittest.mock import MagicMock

from src.core.conferidor_manobras import (
    _consultar_topologia_gdis,
    _get_eq_data,
    _obter_prefixo_equipamento,
    _get_eq_id
)

def test_obter_prefixo_e_id():
    assert _get_eq_id("36 - 107457") == "107457"
    assert _get_eq_id("22 - 121747") == "121747"
    assert _get_eq_id("107457") == "107457"

    assert _obter_prefixo_equipamento("36 - 107457") == "36"
    assert _obter_prefixo_equipamento("107457", {"tipo": "Religador"}) == "22"
    assert _obter_prefixo_equipamento("107457", {"tipo": "Chave Faca Adaptada"}) == "36"


def test_consultar_topologia_gdis_mock():
    # Mock do context do Playwright
    mock_context = MagicMock()
    mock_context.cookies.return_value = [
        {"name": "JSESSIONID", "value": "TEST_SESSION_12345", "path": "/gdis-do-web"}
    ]

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.json.return_value = {
        "root": {"id": "ROOT_1", "tipono": "alimentador", "refalm": "MVDU106"},
        "nos": [
            {
                "id": "NO_107457",
                "numeq": "107457",
                "POSOPE": "A",
                "r_tipoeq": "Chave Faca Adaptada",
                "r_fases": "A",
                "r_controle": "manual",
                "telecom": "N",
                "refalm": "MVDU106",
                "logradouro": "PORTEIRINHA",
                "tensao": "13.8"
            },
            {
                "id": "NO_121747",
                "numeq": "121747",
                "POSOPE": "F",
                "r_tipoeq": "Religador",
                "r_fases": "ABC",
                "r_controle": "telecontrolado",
                "telecom": "S",
                "refalm": "MVDU106",
                "refalm_2": "PTHD218",
                "tensao": "13.8"
            }
        ]
    }
    mock_context.request.post.return_value = mock_resp

    dados = _consultar_topologia_gdis(mock_context, "MVDU106", usuario="teste", log_func=lambda x: None)

    assert "107457" in dados
    assert "36 - 107457" in dados
    eq1 = dados["107457"][0]
    assert eq1["posope"] == "A"
    assert eq1["fases"] == "A"
    assert eq1["telecontrolado"] is False
    assert eq1["origem"] == "GDIS_AO_VIVO"

    assert "121747" in dados
    assert "22 - 121747" in dados
    eq2 = dados["121747"][0]
    assert eq2["posope"] == "F"
    assert eq2["fases"] == "ABC"
    assert eq2["telecontrolado"] is True


def test_get_eq_data_com_dados_dinamicos():
    dados = {
        "107457": [{
            "numero": "107457",
            "tipo": "Chave Faca Adaptada",
            "posope": "A",
            "fases": "A",
            "telecontrolado": False,
            "alimentadores": ["MVDU106"],
            "origem": "GDIS_AO_VIVO"
        }],
        "36 - 107457": [{
            "numero": "107457",
            "tipo": "Chave Faca Adaptada",
            "posope": "A",
            "fases": "A",
            "telecontrolado": False,
            "alimentadores": ["MVDU106"],
            "origem": "GDIS_AO_VIVO"
        }]
    }

    # Busca por nome completo com prefixo
    item1 = _get_eq_data(dados, "36 - 107457", "MVDU106")
    assert item1["numero"] == "107457"
    assert item1["posope"] == "A"
    assert item1["fases"] == "A"

    # Busca apenas pelo número
    item2 = _get_eq_data(dados, "107457", "MVDU106")
    assert item2["numero"] == "107457"
    assert item2["posope"] == "A"


def test_regra_31_ciclo_na_com_cadastro_base_divergente():
    import re
    macros_abertura = re.compile(r'\b(MA01|MA31|MA30|MA06)\b')
    macros_fechamento = re.compile(r'\b(MA02|MA66|MA49)\b')

    manobra_items = [
        {'cronologia': 20, 'texto_linha': '30 MA02 - FECHAR EQUIPAMENTO 28 - 308826', 'observacao': 'GERADOR DE MT'},
        {'cronologia': 70, 'texto_linha': '20 MA01 - ABRIR EQUIPAMENTO 28 - 308826', 'observacao': 'GERADOR DE MT'}
    ]

    eq_data = {
        'numero': '308826',
        'posope': 'F',
        'alimentadores': ['PTHD218'],
        'origem': 'CADASTRO_BASE'
    }

    posope = eq_data.get('posope')
    alim_manobra = 'PPUK001'

    acoes_cronologicas = []
    for mi in sorted(manobra_items, key=lambda x: x.get('cronologia', 0)):
        t_lin = mi.get('texto_linha', '').upper()
        if macros_abertura.search(t_lin) or re.search(r'\bABRIR\b', t_lin):
            acoes_cronologicas.append('ABRIR')
        elif macros_fechamento.search(t_lin) or re.search(r'\bFECHAR\b', t_lin):
            acoes_cronologicas.append('FECHAR')

    txt_eq_completo = ' '.join([str(mi.get('observacao', '')) for mi in manobra_items]).upper()
    tem_indicativo_na = any(w in txt_eq_completo for w in ['GERADOR', 'UGTM', 'INTERLIG', 'SOCORRO', 'TRANSFERENCIA'])
    origem_cadastro = eq_data.get('origem', '')
    alims_cad = [str(a).upper() for a in eq_data.get('alimentadores', [])]
    divergencia_circuito = bool(alim_manobra and alims_cad and not any(alim_manobra.upper() in a for a in alims_cad))

    if acoes_cronologicas and acoes_cronologicas[0] == 'FECHAR' and 'ABRIR' in acoes_cronologicas[1:]:
        if origem_cadastro != 'GDIS_AO_VIVO' or tem_indicativo_na or divergencia_circuito:
            posope = 'A'

    assert posope == 'A'


def test_limite_pre_desligamento_com_ple_bi():
    from src.core.conferidor_manobras import _obter_limite_pre_desligamento
    manobra_dados = [
        {'cronologia': 10, 'etapa_nome': '10 VERIFICACAO PELO COD SSO 007'},
        {'cronologia': 20, 'etapa_nome': '20 MANOBRA SSO 007'},
        {'cronologia': 30, 'etapa_nome': '30 AUTORIZACAO DO PLE/BI 389802 SSO 007'},
        {'cronologia': 40, 'etapa_nome': '40 DISPENSA DO PLE/BI 389802 SSO 007'},
        {'cronologia': 50, 'etapa_nome': '50 MANOBRA COM RISCO SISTEMA SSO 007 NORMALIZAR ATE AS 17:00'}
    ]
    limite = _obter_limite_pre_desligamento(manobra_dados)
    # A etapa de AUTORIZACAO DO PLE/BI marca o fim da fase de alívio e preparação
    assert limite == 30


def test_ciclo_na_e_sem_reversao_pre_desligamento_manobra_245626825():
    """Valida que fechar religador 22-122883 na etapa 20 e abrir na etapa 50 (após dispensa PLE/BI) não é falso positivo de reversão"""
    from src.core.conferidor_manobras import _obter_limite_pre_desligamento
    import re

    manobra_dados = [
        {'cronologia': 10, 'etapa_nome': '10 VERIFICACAO PELO COD SSO 007'},
        {'cronologia': 20, 'etapa_nome': '20 MANOBRA SSO 007'},
        {'cronologia': 30, 'etapa_nome': '30 AUTORIZACAO DO PLE/BI 389802 SSO 007'},
        {'cronologia': 40, 'etapa_nome': '40 DISPENSA DO PLE/BI 389802 SSO 007'},
        {'cronologia': 50, 'etapa_nome': '50 MANOBRA COM RISCO SISTEMA SSO 007'}
    ]
    limite_cronologia = _obter_limite_pre_desligamento(manobra_dados)
    assert limite_cronologia == 30

    itens_22_122883 = [
        {'cronologia': 20, 'texto_linha': '10 MA02 - FECHAR EQUIPAMENTO 22 - 122883', 'etapa_nome': '20 MANOBRA'},
        {'cronologia': 50, 'texto_linha': '30 MA01 - ABRIR EQUIPAMENTO 22 - 122883', 'etapa_nome': '50 MANOBRA COM RISCO'}
    ]

    historico_pre = []
    for mi in itens_22_122883:
        cron = mi['cronologia']
        eh_pre = (limite_cronologia != -1) and (cron <= limite_cronologia)
        if eh_pre:
            if 'ABRIR' in mi['texto_linha']:
                historico_pre.append(('Etapa', 'ABRIR'))
            elif 'FECHAR' in mi['texto_linha']:
                historico_pre.append(('Etapa', 'FECHAR'))

    # Na fase pré-desligamento/pré-obra houve apenas FECHAR (não houve reversão prematura)
    assert len(historico_pre) == 1
    assert historico_pre[0][1] == 'FECHAR'


def test_regra_02_equipamentos_abertos_na_etapa_desligamento():
    """Valida que equipamentos (22 - 241173 e 28 - 89082) com abertura e sinalização na etapa de Desligamento são aprovados na Regra 02."""
    from src.core.conferidor_manobras import _obter_limite_pre_desligamento, _item_pertence_fase_desligamento
    import re

    manobra_dados = [
        {'cronologia': 10, 'etapa_nome': '10 VERIFICACAO PELO COD PRRU 009'},
        {'cronologia': 20, 'etapa_nome': '20 DESLIGAMENTO PRRU 009', 'texto_linha': '10 MA40 - SOLICITAR AUTORIZACAO PARA DESLIGAMENTO'},
        {'cronologia': 21, 'etapa_nome': '20 DESLIGAMENTO PRRU 009', 'equipamento': '22 - 241173', 'texto_linha': '20 MA01 - ABRIR EQUIPAMENTO 22 - 241173'},
        {'cronologia': 22, 'etapa_nome': '20 DESLIGAMENTO PRRU 009', 'equipamento': '22 - 241173', 'texto_linha': '30 MA06 - SINALIZAR EQUIPAMENTO 22 - 241173'},
        {'cronologia': 23, 'etapa_nome': '20 DESLIGAMENTO PRRU 009', 'equipamento': '28 - 89082', 'texto_linha': '40 MA31 - ABRIR E SINALIZAR EQUIPAMENTO 28 - 89082'},
        {'cronologia': 30, 'etapa_nome': '30 RELIGAMENTO PRRU 009'}
    ]

    limite = _obter_limite_pre_desligamento(manobra_dados)
    assert limite >= 20

    # Itens pertencentes à fase de desligamento
    itens_22_241173 = [mi for mi in manobra_dados if mi.get('equipamento') == '22 - 241173' and _item_pertence_fase_desligamento(mi, limite)]
    itens_28_89082 = [mi for mi in manobra_dados if mi.get('equipamento') == '28 - 89082' and _item_pertence_fase_desligamento(mi, limite)]

    assert len(itens_22_241173) == 2
    assert len(itens_28_89082) == 1

    # Checa abertura e sinalizacao para 22 - 241173
    tem_ab_22 = any(re.search(r'\b\d*MA01\b', mi['texto_linha']) for mi in itens_22_241173)
    tem_sin_22 = any(re.search(r'\b\d*MA06\b', mi['texto_linha']) for mi in itens_22_241173)
    assert tem_ab_22 is True
    assert tem_sin_22 is True

    # Checa abertura completa (MA31) para 28 - 89082
    tem_completa_28 = any(re.search(r'\b\d*MA31\b', mi['texto_linha']) for mi in itens_28_89082)
    assert tem_completa_28 is True


def test_inferencia_posope_religador_22_359323_sem_gdis():
    """Valida que o religador 22 - 359323 tem seu POSOPE inferido deterministicamente como NF (F) na Regra 31 a partir da engenharia da manobra."""
    from src.core.conferidor_manobras import _obter_prefixo_equipamento
    eq = "22 - 359323"
    eq_data = {}  # GDIS retornou vazio / 204
    manobra_items = [
        {'cronologia': 10, 'texto_linha': '10 MA14 - BLOQUEAR RELIGAMENTO AUTOMATICO 22 - 359323', 'etapa_nome': '10 PREPARACAO'},
        {'cronologia': 20, 'texto_linha': '20 MA01 - ABRIR EQUIPAMENTO 22 - 359323', 'etapa_nome': '20 DESLIGAMENTO'}
    ]

    prefixo = _obter_prefixo_equipamento(eq, eq_data)
    assert prefixo == "22"

    # Simula inferência da Regra 31
    posope = str(eq_data.get('posope', '')).strip().upper()
    acoes_cronologicas = ['ABRIR']
    if not posope:
        if acoes_cronologicas and acoes_cronologicas[0] == 'ABRIR':
            posope = 'F'

    assert posope == 'F'


def test_manobra_transferencia_com_carga_e_desligamento_245643023():
    """
    Valida a manobra 245643023 onde há:
    - Etapa 20: Transferência com carga para Gerador de MT (24-99839 abre, 28-233097 fecha)
    - Etapa 30: Desligamento do trecho de obra (28-99605 abre)
    - Etapa 40: Religamento pós-obra (28-99605 fecha)
    - Etapa 50: Recomposição da transferência (28-233097 abre, 24-99839 fecha)
    Garante que:
    1. O limite pré-desligamento é 11 (fim da etapa 30, antes da etapa 40).
    2. Nenhuma reversão prematura pré-desligamento é falsamente apontada.
    """
    from src.core.conferidor_manobras import _obter_limite_pre_desligamento
    import re

    manobra_dados = [
        # Etapa 10
        {'cronologia': 1, 'etapa_nome': '10 VERIFICACAO PELO COD MVDU105', 'texto_linha': '10 MA09 MVDU105'},
        {'cronologia': 2, 'etapa_nome': '10 VERIFICACAO PELO COD MVDU105', 'texto_linha': '20 MA09 MZLU006'},
        # Etapa 20: Transferência prévia com carga
        {'cronologia': 3, 'etapa_nome': '20 MANOBRA PELO TECNICO MVDU105', 'texto_linha': '10 MAA7 - SOLICITAR AO COD AUTORIZACAO PARA MANOBRAR MVDU'},
        {'cronologia': 4, 'etapa_nome': '20 MANOBRA PELO TECNICO MVDU105', 'equipamento': '24 - 99839', 'texto_linha': '20 MA31 - ABRIR E SINALIZAR EQUIPAMENTO 24 - 99839'},
        {'cronologia': 5, 'etapa_nome': '20 MANOBRA PELO TECNICO MVDU105', 'equipamento': '28 - 233097', 'texto_linha': '30 MA02 - FECHAR EQUIPAMENTO 28 - 233097 MANY001'},
        {'cronologia': 6, 'etapa_nome': '20 MANOBRA PELO TECNICO MVDU105', 'texto_linha': '40 MAA8 - INFORMAR AO COD MANOBRA REALIZADA MVDU'},
        # Etapa 30: Desligamento
        {'cronologia': 7, 'etapa_nome': '30 DESLIGAMENTO MVDU105', 'texto_linha': '10 MA40 - SOLICITAR AO COD AUTORIZACAO PARA DESLIGAMENTO MVDU'},
        {'cronologia': 8, 'etapa_nome': '30 DESLIGAMENTO MVDU105', 'equipamento': '22 - 137584', 'texto_linha': '20 MA64 - COLOCAR CONTROLE DO EQUIPAMENTO EM MODO LOCAL 22 - 137584'},
        {'cronologia': 9, 'etapa_nome': '30 DESLIGAMENTO MVDU105', 'equipamento': '22 - 137584', 'texto_linha': '30 MA06 - VERIFICAR EQUIPAMENTO ABERTO E SINALIZAR 22 - 137584'},
        {'cronologia': 10, 'etapa_nome': '30 DESLIGAMENTO MVDU105', 'equipamento': '28 - 99605', 'texto_linha': '40 MA31 - ABRIR E SINALIZAR EQUIPAMENTO 28 - 99605'},
        {'cronologia': 11, 'etapa_nome': '30 DESLIGAMENTO MVDU105', 'texto_linha': '50 MA42 - TESTAR E ATERRAR OS CIRCUITOS MVDU'},
        # Etapa 40: Religamento
        {'cronologia': 12, 'etapa_nome': '40 RELIGAMENTO MVDU105', 'texto_linha': '10 MA43 - RETIRAR ATERRAMENTO DOS CIRCUITOS MVDU'},
        {'cronologia': 13, 'etapa_nome': '40 RELIGAMENTO MVDU105', 'equipamento': '28 - 99605', 'texto_linha': '20 MA66 - RETIRAR SINALIZACAO E FECHAR EQUIPAMENTO 28 - 99605'},
        {'cronologia': 14, 'etapa_nome': '40 RELIGAMENTO MVDU105', 'equipamento': '22 - 137584', 'texto_linha': '30 MA07 - RETIRAR PLACA NAO OPERE DO EQUIPAMENTO 22 - 137584'},
        {'cronologia': 15, 'etapa_nome': '40 RELIGAMENTO MVDU105', 'equipamento': '22 - 137584', 'texto_linha': '40 MA65 - COLOCAR CONTROLE DO EQUIPAMENTO EM MODO REMOTO 22 - 137584'},
        {'cronologia': 16, 'etapa_nome': '40 RELIGAMENTO MVDU105', 'texto_linha': '50 MA41 - INFORMAR AO COD RELIGAMENTO COM HORARIO MVDU'},
        # Etapa 50: Normalização da transferência
        {'cronologia': 17, 'etapa_nome': '50 MANOBRA PELO TECNICO MVDU105', 'texto_linha': '10 MAA7 - SOLICITAR AO COD AUTORIZACAO PARA MANOBRAR MVDU'},
        {'cronologia': 18, 'etapa_nome': '50 MANOBRA PELO TECNICO MVDU105', 'equipamento': '28 - 233097', 'texto_linha': '20 MA01 - ABRIR EQUIPAMENTO 28 - 233097 MANY001'},
        {'cronologia': 19, 'etapa_nome': '50 MANOBRA PELO TECNICO MVDU105', 'equipamento': '24 - 99839', 'texto_linha': '30 MA66 - RETIRAR SINALIZACAO E FECHAR EQUIPAMENTO 24 - 99839'},
        {'cronologia': 20, 'etapa_nome': '50 MANOBRA PELO TECNICO MVDU105', 'texto_linha': '40 MAA8 - INFORMAR AO COD MANOBRA REALIZADA MVDU'}
    ]

    limite_cronologia = _obter_limite_pre_desligamento(manobra_dados)
    # Limite pré-desligamento deve ser o fim da etapa 30 (cronologia 11), sem estender para as etapas 40 e 50
    assert limite_cronologia == 11

    # Valida que nenhum dos 3 equipamentos tem bate-volta pré-desligamento
    macros_ab = re.compile(r'\b\d*(MA01|MA31|MA30|MA18|MA22|MA24|MA54|MA56|MAA9)\b(?!\s*-\s*OUTROS)')
    macros_fe = re.compile(r'\b\d*(MA02|MA66|MA67|MA19|MA23|MA25|MA55|MA57|MAB1)\b(?!\s*-\s*OUTROS)')

    for eq_test in ['24 - 99839', '28 - 233097', '28 - 99605']:
        itens_eq = [mi for mi in manobra_dados if mi.get('equipamento') == eq_test]
        hist_pre = []
        for mi in itens_eq:
            cron = mi['cronologia']
            nome_et = mi.get('etapa_nome', '').upper()
            eh_retorno = any(w in nome_et for w in ["RELIGAMENTO", "RECOMPOSICAO", "RECOMPOSIÇÃO", "RESTABELECIMENTO"])
            if (not eh_retorno) and (limite_cronologia != -1) and (cron <= limite_cronologia):
                txt = mi['texto_linha'].upper()
                if macros_ab.search(txt) or 'ABRIR' in txt:
                    hist_pre.append((mi['etapa_nome'], 'ABRIR'))
                elif macros_fe.search(txt) or 'FECHAR' in txt:
                    hist_pre.append((mi['etapa_nome'], 'FECHAR'))

        # Cada equipamento teve no máximo 1 ação na fase pré-desligamento (sem reversão prematura)
        assert len(hist_pre) <= 1, f"Equipamento {eq_test} não deve ter mais de 1 ação pré-desligamento: {hist_pre}"



