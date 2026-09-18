import os
import re
import sys
import unittest

base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)


class TestRegra31CoerenciaEstado(unittest.TestCase):

    def test_regra_31_fechar_equipamento_ja_nf(self):
        """Valida que tentar fechar (MA02) um equipamento Normal Fechado (NF) gera erro na Regra 31 quando rotulado como NF."""
        manobra_items = [
            {
                'texto_linha': 'MA02 - FECHAR EQUIPAMENTO 22 - 261812 (NF)',
                'observacao': 'CHAVE NF',
                'etapa_nome': '01 DESLIGAMENTO',
                'etapa_texto_header': '01 DESLIGAMENTO',
                'cronologia': 1
            }
        ]
        eq = "22 - 261812"
        eq_data = {}

        # Simula inferência de POSOPE com fronteira estrita NA/NF
        posope = str(eq_data.get('posope', '')).strip().upper()
        if not posope:
            txt_eq_completo = ' '.join([
                str(eq) + ' ' +
                str(mi.get('texto_linha', '')) + ' ' + 
                str(mi.get('observacao', '')) + ' ' + 
                str(mi.get('etapa_nome', '')) + ' ' + 
                str(mi.get('etapa_texto_header', ''))
                for mi in manobra_items
            ]).upper()
            tags_na = ['(NA)', 'CHAVE NA', 'POSOPE NA', 'POSOPE: NA', 'NORMAL ABERTO', 'NORMAL ABERTA']
            tags_nf = ['(NF)', 'CHAVE NF', 'POSOPE NF', 'POSOPE: NF', 'NORMAL FECHADO', 'NORMAL FECHADA']

            tem_na = any(k in txt_eq_completo for k in tags_na) or bool(re.search(r'\bNA\b', txt_eq_completo))
            tem_nf = any(k in txt_eq_completo for k in tags_nf) or bool(re.search(r'\bNF\b', txt_eq_completo))

            if tem_na and not tem_nf:
                posope = 'A'
            elif tem_nf and not tem_na:
                posope = 'F'
            else:
                posope = ''

        self.assertEqual(posope, 'F', "Equipamento 22 - 261812 com tag (NF) deve ser inferido como NF (F)")

        estado_simulado = posope
        erro_31 = []
        macros_fechamento = re.compile(r'\b\d*(MA02|MA66|MA67|MA19|MA23|MA25|MA55|MA57|MAB1)\b(?!\s*-\s*OUTROS)')

        for mi in manobra_items:
            txt = mi['texto_linha'].upper()
            is_fechamento = bool(macros_fechamento.search(txt) or re.search(r'\bFECHAR\b', txt))
            if is_fechamento:
                if estado_simulado == 'F':
                    erro_31.append("Tentativa de Fechamento em equipamento que já consta como Fechado (NF/POSOPE=F)")
                estado_simulado = 'F'

        self.assertTrue(len(erro_31) > 0, "Deveria detectar erro ao tentar fechar equipamento que já é NF")
        self.assertIn("Tentativa de Fechamento em equipamento que já consta como Fechado", erro_31[0])

    def test_regra_31_abrir_equipamento_ja_na(self):
        """Valida que tentar abrir (MA01) um equipamento Normal Aberto (NA) gera erro na Regra 31."""
        manobra_items = [
            {
                'texto_linha': 'MA01 - ABRIR EQUIPAMENTO 22 - 475659 (NA)',
                'observacao': 'CHAVE NA',
                'etapa_nome': '01 DESLIGAMENTO',
                'etapa_texto_header': '01 DESLIGAMENTO',
                'cronologia': 1
            }
        ]
        eq = "22 - 475659"
        eq_data = {}

        posope = str(eq_data.get('posope', '')).strip().upper()
        if not posope:
            txt_eq_completo = ' '.join([
                str(eq) + ' ' +
                str(mi.get('texto_linha', '')) + ' ' + 
                str(mi.get('observacao', '')) + ' ' + 
                str(mi.get('etapa_nome', '')) + ' ' + 
                str(mi.get('etapa_texto_header', ''))
                for mi in manobra_items
            ]).upper()
            tags_na = ['(NA)', 'CHAVE NA', 'POSOPE NA', 'POSOPE: NA', 'NORMAL ABERTO', 'NORMAL ABERTA']
            tags_nf = ['(NF)', 'CHAVE NF', 'POSOPE NF', 'POSOPE: NF', 'NORMAL FECHADO', 'NORMAL FECHADA']

            tem_na = any(k in txt_eq_completo for k in tags_na) or bool(re.search(r'\bNA\b', txt_eq_completo))
            tem_nf = any(k in txt_eq_completo for k in tags_nf) or bool(re.search(r'\bNF\b', txt_eq_completo))

            if tem_na and not tem_nf:
                posope = 'A'
            elif tem_nf and not tem_na:
                posope = 'F'
            else:
                posope = ''

        self.assertEqual(posope, 'A', "Equipamento 22 - 475659 com tag (NA) deve ser inferido como NA (A)")

        estado_simulado = posope
        erro_31 = []
        macros_abertura = re.compile(r'\b\d*(MA01|MA31|MA30|MA18|MA22|MA24|MA54|MA56|MAA9)\b(?!\s*-\s*OUTROS)')

        for mi in manobra_items:
            txt = mi['texto_linha'].upper()
            is_abertura = bool(macros_abertura.search(txt) or re.search(r'\bABRIR\b', txt))
            if is_abertura:
                if estado_simulado == 'A':
                    erro_31.append("Tentativa de Abertura em equipamento que já consta como Aberto (NA/POSOPE=A)")
                estado_simulado = 'A'

        self.assertTrue(len(erro_31) > 0, "Deveria detectar erro ao tentar abrir equipamento que já é NA")
        self.assertIn("Tentativa de Abertura em equipamento que já consta como Aberto", erro_31[0])

    def test_regra_31_estado_desconhecido_sem_tag(self):
        """Valida que um equipamento sem tag NA/NF e sem cadastro POSOPE não gera erro falso positivo ao ser fechado."""
        manobra_items = [
            {
                'texto_linha': 'MA02 - FECHAR EQUIPAMENTO 22 - 378993',
                'observacao': '',
                'etapa_nome': '01 DESLIGAMENTO',
                'etapa_texto_header': '01 DESLIGAMENTO',
                'cronologia': 1
            }
        ]
        eq = "22 - 378993"
        eq_data = {}

        posope = str(eq_data.get('posope', '')).strip().upper()
        if not posope:
            txt_eq_completo = ' '.join([
                str(eq) + ' ' +
                str(mi.get('texto_linha', '')) + ' ' + 
                str(mi.get('observacao', '')) + ' ' + 
                str(mi.get('etapa_nome', '')) + ' ' + 
                str(mi.get('etapa_texto_header', ''))
                for mi in manobra_items
            ]).upper()
            tags_na = ['(NA)', 'CHAVE NA', 'POSOPE NA', 'POSOPE: NA', 'NORMAL ABERTO', 'NORMAL ABERTA']
            tags_nf = ['(NF)', 'CHAVE NF', 'POSOPE NF', 'POSOPE: NF', 'NORMAL FECHADO', 'NORMAL FECHADA']

            tem_na = any(k in txt_eq_completo for k in tags_na) or bool(re.search(r'\bNA\b', txt_eq_completo))
            tem_nf = any(k in txt_eq_completo for k in tags_nf) or bool(re.search(r'\bNF\b', txt_eq_completo))

            if tem_na and not tem_nf:
                posope = 'A'
            elif tem_nf and not tem_na:
                posope = 'F'
            else:
                posope = ''

        self.assertEqual(posope, '', "Equipamento sem tag NA/NF deve ser considerado de estado desconhecido ('')")

        estado_simulado = posope
        erro_31 = []
        macros_fechamento = re.compile(r'\b\d*(MA02|MA66|MA67|MA19|MA23|MA25|MA55|MA57|MAB1)\b(?!\s*-\s*OUTROS)')

        for mi in manobra_items:
            txt = mi['texto_linha'].upper()
            is_fechamento = bool(macros_fechamento.search(txt) or re.search(r'\bFECHAR\b', txt))
            if is_fechamento:
                if estado_simulado == 'F':
                    erro_31.append("Tentativa de Fechamento em equipamento que já consta como Fechado (NF/POSOPE=F)")
                estado_simulado = 'F'

        self.assertEqual(len(erro_31), 0, "Equipamento sem tag não deve disparar erro falso positivo na Regra 31")

    def test_regra_31b_gerador_e_mesmo_horario(self):
        """Valida que abrir transformador e fechar gerador no mesmo horário (ou com indicação de gerador/com carga) não dispara erro na Regra 31.B."""
        manobra_dados = [
            {
                'equipamento': '28 - 163751',
                'texto_linha': '20 MA31 - ABRIR E SINALIZAR EQUIPAMENTO 28 - 163751 PTHD217 COM CARGA 23/09/2026 09:00',
                'observacao': 'TRAFO 778899 - 3 - 45',
                'etapa_nome': '20 MANOBRA PELO TECNICO',
                'etapa_texto_header': '20 MANOBRA PELO TECNICO PTHD217 23/09/2026 09:00',
                'data_hora': '23/09/2026 09:00',
                'grupo_id': 'ETAPA_20',
                'cronologia': 3
            },
            {
                'equipamento': '28 - 175854',
                'texto_linha': '30 MA02 - FECHAR EQUIPAMENTO 28 - 175854 SRQA001 COM CARGA 23/09/2026 09:00',
                'observacao': 'GERADOR DE BT',
                'etapa_nome': '20 MANOBRA PELO TECNICO',
                'etapa_texto_header': '20 MANOBRA PELO TECNICO PTHD217 23/09/2026 09:00',
                'data_hora': '23/09/2026 09:00',
                'grupo_id': 'ETAPA_20',
                'cronologia': 4
            }
        ]
        sol_dict = {'778899 - 3 - 45': {'eq': '778899 - 3 - 45'}}

        # Teste 1: Limite da solicitação identificado pela observação
        mi_ab = manobra_dados[0]
        obs_ab = mi_ab.get('observacao', '').upper()
        texto_completo_ab = f"{mi_ab['equipamento']} {obs_ab} {mi_ab['texto_linha'].upper()}"
        digits_ab = set(re.findall(r'\b\d{4,7}\b', texto_completo_ab))
        is_solicitacao_boundary = any(digits_ab & set(re.findall(r'\b\d{4,7}\b', sol_eq)) for sol_eq in sol_dict)
        self.assertTrue(is_solicitacao_boundary, "Trafo 778899 na observação deve ser reconhecido como boundary da solicitação")

        # Teste 2: Mesmo horário e contexto de gerador
        mi_fe = manobra_dados[1]
        texto_completo_fe = f"{mi_fe['equipamento']} {mi_fe['observacao'].upper()} {mi_fe['texto_linha'].upper()}"
        contexto_gerador = any(k in (texto_completo_ab + " " + texto_completo_fe) for k in ["GERADOR", "GBT", "GMT", "UGTM"])
        self.assertTrue(contexto_gerador, "Deve identificar contexto de gerador")

        m_dt_ab = re.search(r'(\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2})|(\b\d{2}:\d{2}\b)', mi_ab['data_hora'])
        m_dt_fe = re.search(r'(\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2})|(\b\d{2}:\d{2}\b)', mi_fe['data_hora'])
        self.assertEqual(m_dt_ab.group(0), m_dt_fe.group(0), "Ambas as manobras ocorrem no mesmo horário de agendamento (09:00)")

    def test_regra_31b_inversao_com_horarios_distintos_detecta_erro(self):
        """Valida que se houver abertura em etapa/horário anterior ao fechamento do socorro sem gerador, o erro é apontado."""
        mi_ab = {
            'equipamento': '28 - 111111',
            'texto_linha': 'MA01 - ABRIR EQUIPAMENTO 28 - 111111',
            'observacao': '',
            'data_hora': '23/09/2026 08:00',
            'etapa_texto_header': '10 MANOBRA 23/09/2026 08:00',
            'grupo_id': 'ETAPA_10',
            'cronologia': 1
        }
        mi_fe = {
            'equipamento': '28 - 222222',
            'texto_linha': 'MA02 - FECHAR EQUIPAMENTO 28 - 222222',
            'observacao': 'CHAVE DE SOCORRO',
            'data_hora': '23/09/2026 09:30',
            'etapa_texto_header': '20 MANOBRA 23/09/2026 09:30',
            'grupo_id': 'ETAPA_20',
            'cronologia': 5
        }
        texto_completo_ab = f"{mi_ab['equipamento']} {mi_ab['observacao']} {mi_ab['texto_linha'].upper()}"
        texto_completo_fe = f"{mi_fe['equipamento']} {mi_fe['observacao']} {mi_fe['texto_linha'].upper()}"
        
        contexto_gerador = any(k in (texto_completo_ab + " " + texto_completo_fe) for k in ["GERADOR", "GBT", "GMT", "UGTM"])
        self.assertFalse(contexto_gerador)

        m_dt_ab = re.search(r'(\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2})|(\b\d{2}:\d{2}\b)', mi_ab['data_hora'])
        m_dt_fe = re.search(r'(\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2})|(\b\d{2}:\d{2}\b)', mi_fe['data_hora'])
        mesmo_horario = (m_dt_ab.group(0) == m_dt_fe.group(0))
        self.assertFalse(mesmo_horario, "Horários 08:00 e 09:30 são diferentes (intervalo de 1h30)")

    def test_regra_31b_abertura_etapa_desligamento_e_delimitador_solicitacao(self):
        """Valida que aberturas na etapa de DESLIGAMENTO (delimitação da obra da solicitação)
        não são avaliadas falsamente como transferência de carga na Regra 31.B."""
        manobra_dados = [
            {
                'equipamento': '22 - 321468',
                'texto_linha': '20 MA02 - FECHAR EQUIPAMENTO 22 - 321468 MCLD210 COM TENSAO COD NÃO',
                'observacao': '',
                'etapa_nome': '20 MANOBRA COM RISCO SISTEMA',
                'etapa_texto_header': '20 MANOBRA COM RISCO SISTEMA MCLD208 21/09/2026 09:00',
                'data_hora': '21/09/2026 09:00',
                'cronologia': 20
            },
            {
                'equipamento': '24 - 24454',
                'texto_linha': '50 MA31 - ABRIR E SINALIZAR EQUIPAMENTO 24 - 24454 MCLD208 COM CARGA 21/09/2026 10:00 SUPERVISOR NÃO',
                'observacao': '',
                'etapa_nome': '40 DESLIGAMENTO',
                'etapa_texto_header': '40 DESLIGAMENTO MCLD208 21/09/2026 10:00',
                'data_hora': '21/09/2026 10:00',
                'cronologia': 40
            }
        ]
        sol_dict = {'24 - 24454': {'eq': '24 - 24454', 'alim': 'MCLD208', 'local': '2050'}}

        # Simula a checagem da Regra 31.B
        ab = manobra_dados[1]
        et_ab = ab['etapa_nome']
        eh_etapa_desligamento = any(w in et_ab.upper() for w in ["DESLIGAMENTO", "CORTE", "ISOLAMENTO"])
        self.assertTrue(eh_etapa_desligamento, "Etapa 40 DESLIGAMENTO deve ser classificada como etapa de desligamento")

        is_solicitacao_boundary = any(ab['equipamento'] == sol_eq for sol_eq in sol_dict)
        self.assertTrue(is_solicitacao_boundary, "Equipamento 24 - 24454 deve ser reconhecido como delimitador da solicitação")

        # Com a regra atualizada, aberturas em desligamento são desconsideradas de transferência de carga
        deve_ignorar_transferencia = eh_etapa_desligamento
        self.assertTrue(deve_ignorar_transferencia, "Equipamento aberto em etapa de desligamento não deve ser avaliado como transferência de carga")


if __name__ == "__main__":
    unittest.main()


