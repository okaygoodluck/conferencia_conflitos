import sys
import os
from datetime import datetime

# Adiciona o diretório raiz ao sys.path para importar os módulos do projeto
sys.path.append(os.getcwd())

from src.integration import gdis_http_extrator

def test_extraction():
    # Simula o HTML real capturado pelo subagente
    html_sample = """
    <div class="painel">
        <label class="labelDetalhe">Número</label> 1620022
        <br/>
        <label class="labelDetalhe">Data de Início</label> 07/05/2026 10:00
        <br/>
        <label class="labelDetalhe">Solicitante</label> KENNEDY
    </div>
    <div class="painel">
        <label class="labelDetalhe">Situação</label> APROVADA
        <br/>
        <label class="labelDetalhe">Data de Término</label> 07/05/2026 16:00
        <br/>
    </div>
    """
    
    print("\n[TESTE] Iniciando extração de datas do HTML simulado...")
    d_ini, d_fim = gdis_http_extrator._parse_datas(html_sample)
    
    print(f"Data Início: '{d_ini}'")
    print(f"Data Término: '{d_fim}'")
    
    assert d_ini == "07/05/2026 10:00", f"Erro: Esperado '07/05/2026 10:00', obtido '{d_ini}'"
    assert d_fim == "07/05/2026 16:00", f"Erro: Esperado '07/05/2026 16:00', obtido '{d_fim}'"
    
    print("\n✅ SUCESSO: Datas extraídas corretamente!")

if __name__ == "__main__":
    try:
        test_extraction()
    except Exception as e:
        print(f"\n❌ FALHA: {e}")
        sys.exit(1)
