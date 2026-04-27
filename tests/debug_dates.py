import re

def _strip_tags(text):
    return re.sub(r'<[^>]+>', '', text)

def _parse_datas(html_text):
    """Cópia da função do extrator para debug."""
    d_ini = ""
    d_fim = ""
    date_regex = r"(\d{2}/\d{2}/\d{4}(?:\s+\d{2}:\d{2})?)"

    print("--- Tentando Estratégia 1 ---")
    for label, target in [("Data de Início", "d_ini"), ("Data de Término", "d_fim")]:
        # Regex captura o label e tenta achar a data logo depois, pulando tags HTML se houver
        pattern = r'.*?' + re.escape(label) + r'[^>]*>[\s\S]*?' + date_regex
        print(f"Pattern para {label}: {pattern}")
        m = re.search(pattern, html_text, re.I)
        if m:
            val = m.group(1).strip()
            print(f"Encontrado {target}: {val}")
            if target == "d_ini": d_ini = val
            else: d_fim = val
        else:
            print(f"Não encontrado {target}")

    print("\n--- Tentando Estratégia 2 ---")
    if not d_ini:
        m_ini = re.search(r"In[íi]cio[\s\S]{1,100}?" + date_regex, html_text, re.IGNORECASE)
        if m_ini: 
            d_ini = m_ini.group(1).strip()
            print(f"Encontrado d_ini (Est2): {d_ini}")
        
    if not d_fim:
        m_fim = re.search(r"T[ée]rmino[\s\S]{1,100}?" + date_regex, html_text, re.IGNORECASE)
        if m_fim: 
            d_fim = m_fim.group(1).strip()
            print(f"Encontrado d_fim (Est2): {d_fim}")

    return d_ini, d_fim

html_user = """
<div class="rich-panel-body " id="formPrincipal:tooglePanelElaboracaoManobra_body"><table>
<tbody>
<tr>
<td><label>
Data de Início:</label></td>
</tr>
</tbody>
</table>
</td>
<td><table style="height:120px;">
<tbody>
<tr>
<td><span style="width:110px;">07/03/2026 08:00</span></td>
</tr>
</tbody>
</table>
</td>
<td><table style="height:120px;">
<tbody>
<tr>
<td><label>
Data de Término:</label></td>
</tr>
</tbody>
</table>
</td>
<td><table style="height:120px;">
<tbody>
<tr>
<td><span style="width:110px;">07/03/2026 14:00</span></td>
</tr>
</tbody>
</table>
</td>
</tr>
</tbody>
</table>
</div>
"""

ini, fim = _parse_datas(html_user)
print(f"\nResultado Final: Início={ini}, Fim={fim}")
