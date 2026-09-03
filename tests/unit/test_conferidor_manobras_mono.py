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

if __name__ == "__main__":
    unittest.main()
