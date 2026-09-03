# -*- coding: utf-8 -*-
"""
mappings_macros.py
Mapeamento centralizado de Macros, Descrições e Regras de Inversão de Manobras SD/ADMS (CEMIG).
Baseado no repositório oficial de mapeamentos de manobra.
"""

# =========================================
# ETAPAS
# =========================================
ETAPAS = [
    'DESLIGAMENTO',
    'RELIGAMENTO',
    'VERIFICACAO PELO COD',
    'PIQUE PROGRAMADO AT',
    'AUTORIZACAO DO PLE/BI',
    'DISPENSA DO PLE/BI',
    'MANOBRA PELO TECNICO',
    'NOTA',
    'MANOBRA',
    'MANOBRA COM PIQUE',
    'MANOBRA COM RISCO SISTEMA',
    'MANOBRA C/ PIQUE RISCO SISTEMA',
    'MANOBRA COM CORTE DE CARGA'
]

# =========================================
# CONDIÇÃO OPERATIVA
# =========================================
CONDICAO_OPERATIVA = {
    'CC': 'COM CARGA',
    'CT': 'COM TENSAO',
    'ST': 'SEM TENSAO',
    '-': '-'
}

# =========================================
# EXECUTOR
# =========================================
EXECUTOR = ['COD', 'TÉCNICO', 'TECNICO', 'REGIAO', 'REGIÃO', 'SUPERVISOR']

# =========================================
# AÇÕES DA DISTRIBUIÇÃO
# =========================================
ACAO_DISTRIBUICAO = {
    'MA01': 'MA01 - ABRIR EQUIPAMENTO',
    'MA02': 'MA02 - FECHAR EQUIPAMENTO',
    'MA03': 'MA03 - TESTAR AUSENCIA DE TENSAO',
    'MA10': 'MA10 - RETIRAR EQUIPAMENTO DO BY-PASS',
    'MA12': 'MA12 - RECEBER REDE',
    'MA13': 'MA13 - PREPARAR E AGUARDAR',
    'MA14': 'MA14 - BLOQUEAR RA DO RELIGADOR E SINALIZAR',
    'MA15': 'MA15 - BLOQUEAR ST DO RELIGADOR E SINALIZAR',
    'MA16': 'MA16 - RETIRAR SINALIZACAO E NORMALIZAR RA DO RELIGADOR',
    'MA17': 'MA17 - RETIRAR SINALIZACAO E NORMALIZAR ST DO RELIGADOR',
    'MA23': 'MA23 - RETIRAR SINALIZACAO E NORMALIZAR RA',
    'MA27': 'MA27 - POSICIONAR PARA MANOBRAR',
    'MA28': 'MA28 - BLOQUEAR RA DA CHAVE REPETIDORA E SINALIZAR',
    'MA29': 'MA29 - RETIRAR SINALIZ E NORMALIZ RA DA CHAVE REPETIDORA',
    'MA30': 'MA30 - ABRIR, SINALIZAR, TESTAR E ATERRAR',
    'MA31': 'MA31 - ABRIR E SINALIZAR EQUIPAMENTO',
    'MA35': 'MA35 - COLOCAR RT NO NEUTRO E DESLIGAR CAIXA DE COMANDO',
    'MA36': 'MA36 - LIGAR CAIXA DE COMANDO E COLOCAR RT EM SERVICO',
    'MA39': 'MA39 - CONFIRMAR EQUIPAMENTO ABERTO',
    'MA40': 'MA40 - SOLICITAR AO COD AUTORIZACAO PARA DESLIGAMENTO',
    'MA41': 'MA41 - INFORMAR AO COD RELIGAMENTO COM HORARIO',
    'MA42': 'MA42 - TESTAR E ATERRAR OS CIRCUITOS',
    'MA43': 'MA43 - RETIRAR ATERRAMENTO DOS CIRCUITOS',
    'MA48': 'MA48 - ENTREGAR TRECHO AO SUPERVISOR DE SERVICO',
    'MA49': 'MA49 - CONFIRMAR EQUIPAMENTO FECHADO',
    'MA50': 'MA50 - RECEBER TRECHO DO SUPERVISOR DE SERVICO',
    'MA52': 'MA52 - SOLICITAR AO COD BLOQUEIO DO RA',
    'MA53': 'MA53 - DISPENSAR BLOQUEIO DO RA',
    'MA60': 'MA60 - CONFIRMAR EXECUCAO DA ETAPA/ITEM/MANOBRA',
    'MA62': 'MA62 - INSPECIONAR REDE DE DISTRIBUICAO',
    'MA63': 'MA63 - SUBSTITUIR ELO(S) FUSIVEL(EIS) PARA',
    'MA64': 'MA64 - COLOCAR CONTROLE DO EQUIPAMENTO EM MODO LOCAL',
    'MA65': 'MA65 - COLOCAR CONTROLE DO EQUIPAMENTO EM MODO REMOTO',
    'MA66': 'MA66 - RETIRAR SINALIZACAO E FECHAR EQUIPAMENTO',
    'MA67': 'MA67 - RETIRAR ATERRAMENTO, SINALIZACAO E FECHAR',
    'MA79': 'MA79 - CONFIRMAR EQUIPAMENTO COMUNICANDO',
    'MA88': 'MA88 - VERIFICAR DISJ GERAL DO CLIENTE ABERTO E SINALIZAR',
    'MA89': 'MA89 - ALTERAR PARA AJUSTE PRINCIPAL/GRUPO 1',
    'MA90': 'MA90 - RETIRAR SINALIZACAO DO DISJUNTOR GERAL DO CLIENTE',
    'MA91': 'MA91 - FAZER TESTE DE TENSAO ZERO E INFORMAR COD RESULTAD',
    'MA92': 'MA92 - ABRIR SECCIONAMENTO OPERATIVO',
    'MA93': 'MA93 - FECHAR SECCIONAMENTO OPERATIVO',
    'MAA1': 'MAA1 - ALTERAR PARA AJUSTE ALTERNATIVO 1/GRUPO 2',
    'MAA2': 'MAA2 - ALTERAR PARA AJUSTE ALTERNATIVO 2/GRUPO 3',
    'MAA3': 'MAA3 - ALTERAR PARA AJUSTE ALTERNATIVO 3/GRUPO 4',
    'MAA4': 'MAA4 - DESABILITAR TRANSFERENCIA AUTOMATICA',
    'MAA5': 'MAA5 - HABILITAR TRANSFERENCIA AUTOMATICA',
    'MAA7': 'MAA7 - SOLICITAR AO COD AUTORIZACAO PARA MANOBRAR',
    'MAA8': 'MAA8 - INFORMAR AO COD MANOBRA REALIZADA',
    'MAA9': 'MAA9 - ABRIR, SINALIZAR, TESTAR, ATERRAR E INTERTRAVAR',
    'MAB1': 'MAB1 - RETIRAR INTERTRAV, ATERRAMENTO, SINALIZ E FECHAR',
    'MAB2': 'MAB2 - TESTAR, ATERRAR E INTERTRAVAR',
    'MAB3': 'MAB3 - RETIRAR INTERTRAVAMENTO E ATERRAMENTO',
    'MAB4': 'MAB4 - INTERTRAVAR EQUIPAMENTO',
    'MAB5': 'MAB5 - RETIRAR INTERTRAVAMENTO',
    'MAB6': 'MAB6 - SOLICITAR CLIENTE ABRIR DISJUTOR GERAL',
    'MAB7': 'MAB7 - AUTORIZAR CLIENTE FECHAR DISJUNTOR GERAL',
    'MAB8': 'MAB8 - CONFIRMAR EQUIPAMENTO BY-PASSADO',
    'MAB9': 'MAB9 - CONFIRMAR EQUIPAMENTO SEM TELECONTROLE',
    'MAC1': 'MAC1 - SOLICITAR AO CLIENTE AUTORIZACAO PARA DESLIGAR',
    'MACT': 'MACT - CONFIRMAR TENSAO NAS 3 FASES',
    'MAAS': 'MAAS - SOLICITAR AO COD AUTORIZACAO PARA INICIAR SERVICO',
    'MAST': 'MAST - INFORMAR AO COD TERMINO DO SERVICO'
}

# =========================================
# AÇÕES DA SUBESTAÇÃO
# =========================================
ACAO_SUBESTACAO = {
    'MA19': 'MA19 - RETIRAR SINALIZACAO E FECHAR DISJUNTOR/RELIGADOR',
    'MA26': 'MA26 - SOLICITAR COD/AT DISPENSAR PLE',
    'MA78': 'MA78 - RETIRAR SINALIZ E NORMALIZAR SEGUND RELE DE NEUTRO',
    'MA80': 'MA80 - ENTREGAR COD/AT DISJ/RELIG ABERTO C TENSAO RETORNO',
    'MA81': 'MA81 - ENTREGAR COD/AT DISJ/RELIG ABERTO S TENSAO RETORNO',
    'MA96': 'MA96 - CONFIRMAR COM COD/AT AUTORIZACAO DO PLE',
    'MA97': 'MA97 - CONFIRM CODAT EXECUTADA MANOBRA DA DISPENSA DO PLE',
    'MAA6': 'MAA6 - RECEBER COD/AT AUTORIZACAO P NORMALIZAR DISJ/RELIG',
    'MAC2': 'MAC2 - SOLICITAR COD/AT AUTORIZAR PLE'
}

# =========================================
# AÇÕES VARIÁVEIS POR ORIGEM
# 'D' = REDE DISTRIBUICAO | 'S' = SUBESTACAO
# =========================================
ACAO_VARIAVEL = {
    'MA04': {
        'D': 'MA04 - ATERRAR',
        'S': 'MA04 - BLOQUEAR RA E SINALIZAR'
    },
    'MA05': {
        'D': 'MA05 - RETIRAR ATERRAMENTO',
        'S': 'MA05 - RETIRAR SINALIZACAO E NORMALIZAR RA'
    },
    'MA06': {
        'D': 'MA06 - VERIFICAR EQUIPAMENTO ABERTO E SINALIZAR',
        'S': 'MA06 - BLOQUEAR RN/ST E SINALIZAR'
    },
    'MA07': {
        'D': 'MA07 - RETIRAR PLACA NAO OPERE DO EQUIPAMENTO',
        'S': 'MA07 - RETIRAR SINALIZACAO E NORMALIZAR RN/ST'
    },
    'MA09': {
        'D': 'MA09 - BY-PASSAR EQUIPAMENTO',
        'S': 'MA09 - VERIFICAR SE HA ANORMALIDADE NO ALIMENTADOR'
    },
    'MA11': {
        'D': 'MA11 - LIBERAR REDE',
        'S': 'MA11 - OUTROS'
    },
    'MA18': {
        'D': 'MA18 - OUTROS',
        'S': 'MA18 - ABRIR E SINALIZAR DISJUNTOR/RELIGADOR'
    },
    'MA77': {
        'D': 'MA77 - FIXAR TAP DO REGULADOR E DESLIGAR CX DE COMANDO',
        'S': 'MA77 - BLOQUEAR SEGUNDO RELE DE NEUTRO E SINALIZAR'
    }
}

# =========================================
# INVERSÃO DE AÇÕES FIXAS
# =========================================
INVERSAO_ACOES_FIXAS = {
    # Abertura / Fechamento & Operações
    'MA01': 'MA02',
    'MA02': 'MA01',
    'MA30': 'MA67',
    'MA67': 'MA30',
    'MA31': 'MA66',
    'MA66': 'MA31',
    'MAA9': 'MAB1',
    'MAB1': 'MAA9',
    'MA92': 'MA93',
    'MA93': 'MA92',

    # Teste e Aterramento
    'MA42': 'MA43',
    'MA43': 'MA42',
    'MAB2': 'MAB3',
    'MAB3': 'MAB2',

    # Bloqueios de Proteção (RA, ST)
    'MA14': 'MA16',
    'MA16': 'MA14',
    'MA15': 'MA17',
    'MA17': 'MA15',
    'MA28': 'MA29',
    'MA29': 'MA28',
    'MA52': 'MA53',
    'MA53': 'MA52',

    # Reguladores / Caixa de Comando
    'MA35': 'MA36',
    'MA36': 'MA35',

    # Comunicação, Autorizações e Trecho
    'MA40': 'MA41',
    'MA41': 'MA40',
    'MAAS': 'MAST',
    'MAST': 'MAAS',
    'MAA7': 'MAA8',
    'MAA8': 'MAA7',
    'MA48': 'MA50',
    'MA50': 'MA48',
    'MA88': 'MA90',
    'MA90': 'MA88',
    'MAB6': 'MAB7',
    'MAB7': 'MAB6',

    # Modos de Controle, Ajustes e Transferência
    'MA64': 'MA65',
    'MA65': 'MA64',
    'MAA1': 'MA89',
    'MAA2': 'MA89',
    'MAA3': 'MA89',
    'MAA4': 'MAA5',
    'MAA5': 'MAA4',
    'MAB4': 'MAB5',
    'MAB5': 'MAB4',

    # Subestação Específicas / PLE
    'MAC2': 'MA26',
    'MA26': 'MAC2',
    'MA96': 'MA97',
    'MA97': 'MA96',
    'MA80': 'MAA6',
    'MA81': 'MAA6'
}

# =========================================
# INVERSÃO DE AÇÕES VARIÁVEIS
# 'D' = REDE DISTRIBUICAO | 'S' = SUBESTACAO
# =========================================
INVERSAO_ACOES_VARIAVEIS = {
    'MA04': {'D': 'MA05', 'S': 'MA05'},
    'MA05': {'D': 'MA04', 'S': 'MA04'},
    'MA06': {'D': 'MA07', 'S': 'MA07'},
    'MA07': {'D': 'MA06', 'S': 'MA06'},
    'MA09': {'D': 'MA10', 'S': None},
    'MA10': {'D': 'MA09', 'S': 'MA09'},
    'MA11': {'D': 'MA12', 'S': None},
    'MA12': {'D': 'MA11', 'S': 'MA11'},
    'MA18': {'D': None, 'S': 'MA19'},
    'MA19': {'D': 'MA18', 'S': 'MA18'},
    'MA77': {'D': 'MA36', 'S': 'MA78'},
    'MA78': {'D': None, 'S': 'MA77'}
}


def obter_descricao_macro(codigo_macro, origem='REDE DISTRIBUICAO'):
    """
    Retorna a descrição textual completa de uma macro (ex: MA01 -> 'MA01 - ABRIR EQUIPAMENTO').
    """
    if not codigo_macro:
        return ""
    
    code = codigo_macro.strip().upper()
    orig = 'S' if ('SUB' in str(origem).upper() or str(origem).upper() == 'S') else 'D'

    if code in ACAO_VARIAVEL:
        return ACAO_VARIAVEL[code].get(orig, ACAO_VARIAVEL[code].get('D', ''))
    
    if code in ACAO_DISTRIBUICAO:
        return ACAO_DISTRIBUICAO[code]
        
    if code in ACAO_SUBESTACAO:
        return ACAO_SUBESTACAO[code]
        
    return code


def obter_acao_inversa(codigo_macro, origem='REDE DISTRIBUICAO'):
    """
    Retorna o código da ação inversa considerando a origem da ação.
    Ex: obter_acao_inversa('MA31') -> 'MA66'
    """
    if not codigo_macro:
        return None
        
    code = codigo_macro.strip().upper()
    orig = 'S' if ('SUB' in str(origem).upper() or str(origem).upper() == 'S') else 'D'

    # 1. Ações variáveis por origem
    if code in INVERSAO_ACOES_VARIAVEIS:
        return INVERSAO_ACOES_VARIAVEIS[code].get(orig)

    # 2. Ações fixas
    if code in INVERSAO_ACOES_FIXAS:
        return INVERSAO_ACOES_FIXAS[code]

    return None
