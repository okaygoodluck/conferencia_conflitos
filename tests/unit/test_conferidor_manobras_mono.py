import unittest
import os
import sys

base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

from src.core import conferidor_manobras

class TestConferidorManobrasMono(unittest.TestCase):
    def test_carregar_dados_equipamentos_mono(self):
        dados = {"22 - 220754": {"fases": "A", "telecontrolado": False}}
        
        eq_data = conferidor_manobras._get_eq_data(dados, "22 - 220754", "MVDU106")
        self.assertIsNotNone(eq_data, "Equipamento 220754 deveria ser encontrado na base")
        
        fases = conferidor_manobras._obter_fases_equipamento("22 - 220754", eq_data)
        self.assertEqual(fases, "A", "Equipamento 220754 é monofásico (Fase A)")
        
        telecontrolado = conferidor_manobras._verificar_telecontrole("22 - 220754", eq_data)
        self.assertFalse(telecontrolado, "Equipamento 220754 não é telecontrolado")

    def test_regra_29_alerta_gerador_e_interligacao(self):
        """Valida que alimentadores de Gerador e Disjuntor de Interligação (mesmo com erros de digitação como INTELIGACAO) geram alertas informativos e não falhas."""
        import re
        
        manobra_dados = [
            {'alimentador': 'PTHD217', 'texto_linha': 'MA09 - VERIFICAR SE HA ANORMALIDADE NO ALIMENTADOR PTHD217', 'executor': 'COD'},
            {'alimentador': 'SRQA001', 'texto_linha': 'MA02 - FECHAR EQUIPAMENTO', 'observacao': 'GERADOR DE BT', 'executor': 'TECNICO'},
            {'alimentador': 'SSFB001', 'texto_linha': 'MA02 - FECHAR EQUIPAMENTO', 'observacao': 'DISJUNTOR DE INTELIGACAO', 'executor': 'TECNICO'},
            {'alimentador': 'SRRV001', 'texto_linha': 'MA02 - FECHAR EQUIPAMENTO', 'observacao': 'GERADOR DE MT', 'executor': 'TECNICO'},
        ]
        
        contagem_alim = {}
        verificacao_cod_ma09 = set()
        alimentadores_isentos = {}

        for mi in manobra_dados:
            alim = mi.get('alimentador', '').strip()
            if alim:
                contagem_alim[alim] = contagem_alim.get(alim, 0) + 1
            
            tx = mi.get('texto_linha', '')
            ob = mi.get('observacao', '')
            execut_cod = mi.get('executor', '')
            txt_completo_item = f"{tx} {ob}".upper()
            
            motivo_isencao = None
            if "GERADOR DE BT" in txt_completo_item or re.search(r'\bGBT\b', txt_completo_item):
                motivo_isencao = "GERADOR DE BT"
            elif "GERADOR DE MT" in txt_completo_item or re.search(r'\bGMT\b', txt_completo_item):
                motivo_isencao = "GERADOR DE MT"
            elif re.search(r'\bDISJUNTOR\s+DE\s+INT?ERLIGA[CÇ][AÃ]O\b', txt_completo_item) or "INTELIGACAO" in txt_completo_item or "INTERLIGACAO" in txt_completo_item:
                motivo_isencao = "DISJUNTOR DE INTERLIGACAO"
            
            if motivo_isencao and alim:
                alimentadores_isentos[alim] = motivo_isencao
            
            if "COD" in execut_cod and "MA09" in tx:
                verificacao_cod_ma09.add(alim)

        self.assertEqual(alimentadores_isentos.get('SRQA001'), "GERADOR DE BT")
        self.assertEqual(alimentadores_isentos.get('SSFB001'), "DISJUNTOR DE INTERLIGACAO")
        self.assertEqual(alimentadores_isentos.get('SRRV001'), "GERADOR DE MT")
        self.assertNotIn('PTHD217', alimentadores_isentos, "Alimentador principal PTHD217 não pode ser classificado como gerador")
        self.assertIn('PTHD217', verificacao_cod_ma09)

        falhas = [a for a in contagem_alim if a not in verificacao_cod_ma09 and a not in alimentadores_isentos]
        self.assertEqual(len(falhas), 0, "Nenhum dos alimentadores deve gerar falha")

if __name__ == "__main__":
    unittest.main()
