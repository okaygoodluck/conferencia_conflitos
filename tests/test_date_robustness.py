import re
import sys
import os

# Adiciona o path para importar o extrator
sys.path.append(os.getcwd())
from src.integration.gdis_http_extrator import _parse_datas

def test_user_snippet():
    html_snippet = """
<div class="rich-panel-body " id="formPrincipal:tooglePanelElaboracaoManobra_body"><table>
<tbody>
<tr>
<td><label>
Data de Início:</label></td>
<td><span style="width:110px;">07/03/2026 08:00</span></td>
</tr>
<tr>
<td><label>
Data de Término:</label></td>
<td><span style="width:110px;">07/03/2026 12:00</span></td>
</tr>
</tbody>
</table></div>
    """
    
    # Adiciona um "ruído" de filtro no topo para testar a resiliência
    html_full = f"""
    <html>
    <div id="sidebar">
        <span>Filtro de Pesquisa</span>
        <span>Data de Término: 30/04/2026</span>
    </div>
    <body>
    {html_snippet}
    </body>
    </html>
    """
    
    d_ini, d_fim = _parse_datas(html_full)
    print(f"Data Início: {d_ini}")
    print(f"Data Fim: {d_fim}")
    
    # Se capturou a hora, extrai apenas a data para comparação básica
    d_ini_short = d_ini.split()[0] if d_ini else ""
    d_fim_short = d_fim.split()[0] if d_fim else ""
    
    assert "07/03/2026" == d_ini_short, f"Erro na data de início: esperava 07/03/2026, obteve {d_ini}"
    assert "07/03/2026" == d_fim_short, f"Erro na data de término: esperava 07/03/2026, obteve {d_fim}"
    assert "30/04/2026" not in d_fim, "ERRO: Capturou a data do filtro (sidebar) em vez da manobra!"
    
    print("TESTE SUCESSO: A extração ignorou o filtro e pegou os dados corretos da manobra!")

if __name__ == "__main__":
    try:
        test_user_snippet()
    except Exception as e:
        print(f"FALHA NO TESTE: {e}")
        sys.exit(1)
