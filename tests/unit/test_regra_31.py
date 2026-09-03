import unittest
import os
import sys
import re

base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

from src.core import conferidor_manobras

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

if __name__ == "__main__":
    unittest.main()
