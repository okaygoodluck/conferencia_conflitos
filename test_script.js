() => {
            const norm = (s) => (s || '').normalize('NFD').replace(/[\\u0300-\\u036f]/g, '').toLowerCase().replace(/\\s+/g, ' ').trim();
            const clean = (s) => (s || '').replace(/\\s+/g, ' ').trim();
            
            const tables = Array.from(document.querySelectorAll("table[id$=':itensCadastrados']"));
            const resultado = [];
            
            for (const tabela of tables) {
                let etapaNome = "";
                let etapaTextoHeader = "";
                const bodyDiv = tabela.closest("div[id$='_body']");
                if (bodyDiv) {
                    const headerDiv = document.getElementById(bodyDiv.id.replace('_body', '_header'));
                    if (headerDiv) {
                        etapaNome = (headerDiv.textContent || '').replace(/[\s\xA0]+/g, ' ').trim();
                    }
                }
                
                // Busca blindada pela linha cinza do cabeçalho da Etapa (Via Mapeamento de Prefixo JSF)
                const tableId = tabela.id || '';
                const matchPrefix = tableId.match(/^(.*:\\d+:)/);
                if (matchPrefix) {
                    const prefix = matchPrefix[1];
                    const trs = Array.from(document.querySelectorAll('tr.backgroundCinza'));
                    for (const tr of trs) {
                        const firstTd = tr.querySelector('td');
                        // Se a barra cinza pertencer a mesma arvore JSF da tabela de itens, o prefixo bate perfeitamente
                        if (firstTd && firstTd.id && firstTd.id.startsWith(prefix)) {
                            const trText = Array.from(tr.querySelectorAll('td, th')).map(c => c.textContent.trim()).join(' ');
                            etapaTextoHeader += ' ' + trText;
                                  // Novo Fallback Topológico O(N): Encontra o elemento de Etapa que aparece logo ANTES desta tabela no DOM HTML (independente de aninhamento)
                if (!etapaTextoHeader.trim()) {
                    const etapaCandidates = Array.from(document.querySelectorAll('tr, div[class*="header"]'));
                    let bestHeader = '';
                    for (const cand of etapaCandidates) {
                        const c = cand.className || '';
                        const txt = cand.textContent || '';
                        if (c.includes('backgroundCinza') || txt.includes('Etapa:')) {
                            // Só avalia se o container for pequeno (pra não pegar wrapper da pagina inteira) e se estiver antes da tabela atual
                            if (txt.length < 300 && (cand.compareDocumentPosition(tabela) & Node.DOCUMENT_POSITION_FOLLOWING)) {
                                if (cand.tagName === 'TR') {
                                    const tds = Array.from(cand.querySelectorAll('td, th'));
                                    if (tds.length) bestHeader = tds.map(cel => cel.textContent.trim()).join(' ');
                                    else bestHeader = txt.replace(/[\s\xA0]+/g, ' ').trim();
                                } else {
                                    bestHeader = txt.replace(/[\s\xA0]+/g, ' ').trim();
                                }
                            }
                        }
                    }
                    etapaTextoHeader = bestHeader;
                }
                
                etapaTextoHeader = etapaTextoHeader.replace(/[\s\xA0]+/g, ' ').trim();
                
                const ths = Array.from(tabela.querySelectorAll('thead tr:first-child th'));
                const headers = ths.map(th => norm(th.textContent || ''));
                
                let idxAcao = headers.findIndex(h => h.includes('ação') || h.includes('acao') || h.includes('macro'));
                let idxEqpto = headers.findIndex(h => h.includes('eqpto') || h.includes('trafo') || h.includes('equipamento'));
                let idxAlim = headers.findIndex(h => h.includes('alimen') || h.includes('subes'));
                let idxLocal = headers.findIndex(h => h === 'local' || h.includes('local'));
                
                let idxExec = headers.findIndex(h => h.includes('executor') || h.includes('órgão') || h.includes('orgao') || h.includes('execu'));
                let idxPosic = headers.findIndex(h => h.includes('posicionamento') || h.includes('posic'));
                let idxObs = headers.findIndex(h => h.includes('observação') || h.includes('observacao') || h.includes('obs'));
                let idxData = headers.findIndex(h => h.includes('data') || h.includes('hora'));
                
                // Pega TODOS os TRs da tabela, ignorando divisões estritas de tbody/thead para não ser tapeado por JSF rendering
                const rows = Array.from(tabela.querySelectorAll('tr'));
                let currentEtapaLocal = etapaTextoHeader;
                
                for (const row of rows) {
                    // Atualiza a etapa atual caso a linha represente um divisor de bloco/etapa dentro da mesma tabela
                    const c = row.className || '';
                    const textContent = row.textContent || '';
                    if (c.includes('backgroundCinza') || c.includes('ui-rowgroup-header') || c.includes('ui-widget-header') || textContent.includes('Etapa:')) {
                        if (textContent.length < 300) {
                            const rowText = Array.from(row.querySelectorAll('td, th')).map(x => x.textContent.trim()).join(' ');
                            const trClean = rowText.replace(/[\s\xA0]+/g, ' ').trim();
                            // Se for Thead disfarçado, ignora. Apenas aceita linhas de dados
                            if (trClean && !trClean.includes('Operacional') && !trClean.includes('Ação')) {
                                currentEtapaLocal = trClean;
                            }
                        }
                    }
                    
                    const tds = row.querySelectorAll('td');
                    if (tds.length > 3) {
                        const a_mac = (idxAcao >= 0 && tds.length > idxAcao) ? clean(tds[idxAcao].textContent || '') : '';
                        const v = (idxEqpto >= 0 && tds.length > idxEqpto) ? clean(tds[idxEqpto].textContent || '') : '';
                        const a = (idxAlim >= 0 && tds.length > idxAlim) ? clean(tds[idxAlim].textContent || '') : '';
                        const l = (idxLocal >= 0 && tds.length > idxLocal) ? clean(tds[idxLocal].textContent || '') : '';
                        const ex = (idxExec >= 0 && tds.length > idxExec) ? clean(tds[idxExec].textContent || '') : '';
                        const po = (idxPosic >= 0 && tds.length > idxPosic) ? clean(tds[idxPosic].textContent || '') : '';
                        const ob = (idxObs >= 0 && tds.length > idxObs) ? clean(tds[idxObs].textContent || '') : '';
                        const dt = (idxData >= 0 && tds.length > idxData) ? clean(tds[idxData].textContent || '') : '';
                        resultado.push({
                            etapa_nome: etapaNome,
                            etapa_texto_header: currentEtapaLocal,
                            equipamento: v,
                            alimentador: a,
                            local: l,
                            executor: ex,
                            posicionamento: po,
                            observacao: ob,
                            data_hora: dt,
                            acao_bruta: a_mac,
                            texto_linha: clean(Array.from(tds).map(td => td.textContent.trim()).join(' ')).toLowerCase()
                        });
                    }
                }
            }
            return resultado;
        }