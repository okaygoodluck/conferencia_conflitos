let confJobId = null, cmJobId = null;
let confTimer = null, cmTimer = null;

// --- NAVEGAÇÃO SIDEBAR ---
function showSection(id, btn) {
    document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.content-section').forEach(c => {
        c.style.display = 'none';
        c.classList.remove('active');
    });
    
    if (btn) btn.classList.add('active');
    const target = document.getElementById('section-' + id);
    if (target) {
        target.style.display = 'block';
        setTimeout(() => target.classList.add('active'), 10);
    }
    
    // Atualiza título da página
    const titles = { 'conflitos': 'Verificador de Conflitos', 'conferidor_manobras': 'Conferidor de Manobras' };
    document.getElementById('current-page-title').textContent = titles[id] || 'Dashboard';
}

// Sincronização de User/Pass
function setupCredentialSync() {
    document.querySelectorAll('.shared-user').forEach(el => {
        el.addEventListener('input', (e) => {
            const val = e.target.value;
            document.querySelectorAll('.shared-user').forEach(x => { if(x !== e.target) x.value = val; });
        });
    });
    document.querySelectorAll('.shared-pass').forEach(el => {
        el.addEventListener('input', (e) => {
            const val = e.target.value;
            document.querySelectorAll('.shared-pass').forEach(x => { if(x !== e.target) x.value = val; });
        });
    });
}

// Máscara de Data
function maskDate(e) {
    let v = e.target.value.replace(/\D/g, '').slice(0, 8);
    if (v.length > 4) v = v.slice(0, 2) + '/' + v.slice(2, 4) + '/' + v.slice(4);
    else if (v.length > 2) v = v.slice(0, 2) + '/' + v.slice(2);
    e.target.value = v;
}

// Status do Backend
async function pollBackendStatus() {
    try {
        const res = await fetch('/hub/status');
        const data = await res.json();
        const confDot = document.getElementById('status-dot-conf');
        const cmDot = document.getElementById('status-dot-cm');
        
        if (data.conflitos === 'online') confDot.className = 'dot online';
        else confDot.className = 'dot offline';
        
        if (data.conferidor_manobras === 'online') cmDot.className = 'dot online';
        else cmDot.className = 'dot offline';
    } catch (e) {
        console.error("Erro ao verificar status dos backends", e);
    }
}

// --- CONSOLE DRAWER ---
function toggleConsole(context, forceExpand = false, event = null) {
    if (event) event.stopPropagation();
    const drawer = document.getElementById('console-drawer');
    const isExpanded = forceExpand || (forceExpand === false && !drawer.classList.contains('expanded'));
    
    if (isExpanded) drawer.classList.add('expanded');
    else drawer.classList.remove('expanded');

    const icon = document.getElementById('console-toggle-icon');
    if (icon) {
        if (typeof lucide !== 'undefined') {
            // Se lucide estiver disponível, trocamos o atributo e recriamos
            icon.setAttribute('data-lucide', isExpanded ? 'chevron-down' : 'chevron-up');
            lucide.createIcons();
        } else {
            icon.textContent = isExpanded ? '▼' : '▲';
        }
    }

    if (context) {
        switchConsoleView(context);
    }
}

function switchConsoleView(context, event = null) {
    if (event) event.stopPropagation();
    
    document.querySelectorAll('.terminal').forEach(t => t.style.display = 'none');
    document.querySelectorAll('.console-tab').forEach(t => t.classList.remove('active'));
    
    const term = document.getElementById('term-' + (context === 'regras' ? 'cm' : context));
    const tab = document.getElementById('tab-' + (context === 'regras' ? 'cm' : context));
    
    if (term) {
        term.style.display = 'block';
        term.scrollTop = term.scrollHeight;
    }
    if (tab) tab.classList.add('active');
}

function clearConsole() {
    document.querySelectorAll('.terminal').forEach(t => t.innerHTML = "");
}

function updateTerminal(term, logText) {
    if (!logText) return;
    
    const lines = logText.split('\n');
    let html = '';
    let lastProgress = null;

    lines.forEach(line => {
        if (!line.trim()) {
            html += '<div style="height:8px"></div>';
            return;
        }

        let cls = 'log-info';
        let content = line;

        if (line.includes('[PROGRESS]')) {
            lastProgress = line.replace('[PROGRESS]', '').trim();
            return; // Não renderiza agora, guarda pro final
        }
        
        if (line.includes('[CONFLITO]')) {
            cls = 'log-conflito';
            content = '⚠️ ' + line.replace('[CONFLITO]', '').trim();
        } else if (line.includes('[SUCCESS]')) {
            cls = 'log-success';
            content = '✅ ' + line.replace('[SUCCESS]', '').trim();
        } else if (line.includes('[WARN]')) {
            cls = 'log-warn';
            content = '💡 ' + line.replace('[WARN]', '').trim();
        } else if (line.includes('[ERROR]')) {
            cls = 'log-error';
            content = '❌ ' + line.replace('[ERROR]', '').trim();
        } else if (line.includes('[INFO]')) {
            cls = 'log-info';
            content = line.replace('[INFO]', '').trim();
        }

        html += `<div class="log-line ${cls}">${content}</div>`;
    });

    if (lastProgress) {
        html += `<div class="log-progress">⚙️ ${lastProgress}</div>`;
    }

    // Só atualiza o DOM se houver mudança significativa para evitar flickering
    if (term.innerHTML !== html) {
        term.innerHTML = html;
        // Scroll suave para o fim se não estivermos no topo
        term.scrollTop = term.scrollHeight;
    }
}

// --- LÓGICA CONFLITOS ---
async function startConflitos(e) {
    e.preventDefault();
    
    const manobra = document.getElementById('conf-manobra').value.trim();
    const di = document.getElementById('conf-di').value.trim();
    const df = document.getElementById('conf-df').value.trim();
    const eqManual = document.getElementById('conf-eq-manual').value.trim();
    const alManual = document.getElementById('conf-al-manual').value.trim();

    if (!manobra && !eqManual && !alManual) {
        alert("⚠️ Informe uma Manobra ou Equipamentos.");
        return;
    }

    const sit = Array.from(document.querySelectorAll('input[name="sit"]:checked')).map(x => x.value).join(',');
    const mal = Array.from(document.querySelectorAll('input[name="mal"]:checked')).map(x => x.value).join(',');

    const params = new URLSearchParams();
    params.set('manobra', manobra);
    params.set('di', di);
    params.set('df', df);
    params.set('user', document.getElementById('conf-user').value);
    params.set('pass', document.getElementById('conf-pass').value);
    params.set('equipamentos', eqManual);
    params.set('alimentadores', alManual);
    params.set('situacoes', sit);
    params.set('malhas', mal);

    document.getElementById('btn-conf-start').disabled = true;
    document.getElementById('btn-conf-start').classList.add('btn-loading');
    document.getElementById('btn-conf-cancel').disabled = false;
    document.getElementById('pane-conf-status').style.display = 'block';
    document.getElementById('pane-conf-results').style.display = 'block'; // Mostra o card de resultados onde está o skeleton
    document.getElementById('conf-skeleton').classList.add('active');
    document.getElementById('conf-table-real').style.display = 'none';
    document.getElementById('conf-progress-container').style.display = 'block';
    document.getElementById('conf-progress-bar').style.width = '0%';
    
    document.getElementById('term-conf').textContent = "";
    document.getElementById('txt-conf-main').textContent = "Iniciando...";

    toggleConsole('conf', false); // Mantém minimizado conforme solicitado

    const res = await fetch('/conflitos/start', { method: 'POST', body: params });
    const data = await res.json();
    confJobId = data.job_id;
    clearInterval(confTimer);
    confTimer = setInterval(pollConf, 1000);
}

async function pollConf() {
    const res = await fetch('/conflitos/status?job_id=' + confJobId);
    const data = await res.json();

    const term = document.getElementById('term-conf');
    if (data.log) {
        updateTerminal(term, data.log);
    }

    if (data.state === 'running') {
        document.getElementById('txt-conf-main').innerHTML = `⚙️ <span style="color:var(--primary)">${data.processed}</span> / ${data.total}`;
        const small = `Cnf: ${data.conflitos} | Falhas: ${data.falhas} | Tempo: ${data.elapsed}`;
        document.getElementById('txt-conf-small').textContent = small;
        
        if (data.total > 0) {
            const perc = Math.min(100, (data.processed / data.total) * 100);
            document.getElementById('conf-progress-bar').style.width = perc + '%';
        }
    } else if (data.state === 'done') {
        clearInterval(confTimer);
        document.getElementById('btn-conf-start').disabled = false;
        document.getElementById('btn-conf-cancel').disabled = true;
        const rRes = await fetch('/conflitos/result?job_id=' + confJobId);
        const rData = await rRes.json();
        showConfResults(rData);
    } else if (data.state === 'error') {
        clearInterval(confTimer);
        document.getElementById('txt-conf-main').innerHTML = `<span style="color:var(--danger)">❌ ${data.error}</span>`;
        document.getElementById('btn-conf-start').disabled = false;
    }
}

function showConfResults(data) {
    document.getElementById('btn-conf-start').classList.remove('btn-loading');
    document.getElementById('conf-skeleton').classList.remove('active');
    document.getElementById('conf-progress-container').style.display = 'none';
    document.getElementById('conf-table-real').style.display = 'table';
    
    document.getElementById('pane-conf-status').style.display = 'none';
    document.getElementById('pane-conf-results').style.display = 'block';
    const source = data.base ? `Manobra ${data.base}` : `Busca Direta`;
    document.getElementById('conf-summary-bar').textContent = `${data.conflitos.length} conflitos em ${data.total_unico_sem_base} manobras (${data.elapsed}).`;

    const tbody = document.getElementById('tbl-conf-body');
    tbody.innerHTML = '';

    if (data.conflitos_internos) {
        data.conflitos_internos.forEach(c => {
            const tr = document.createElement('tr');
            tr.style.background = 'rgba(245, 158, 11, 0.05)';
            tr.innerHTML = `<td><span style="color:var(--warn)">⚠️ INTERNO</span></td><td>${c.origem} vs ${c.destino}</td><td>${c.equipamentos.join('; ')}</td><td>${c.alimentadores.join('; ')}</td>`;
            tbody.appendChild(tr);
        });
    }

    data.conflitos.forEach(c => {
        const tr = document.createElement('tr');
        tr.innerHTML = `<td><b>${c.manobra}</b></td><td>${c.situacoes.join(', ')}</td><td>${c.equipamentos.join('; ')}</td><td>${c.alimentadores.join('; ')}</td>`;
        tbody.appendChild(tr);
    });
    
    const exportBtn = document.getElementById('lnk-conf-export');
    exportBtn.href = `/conflitos/export?job_id=${confJobId}`;
    exportBtn.style.display = 'inline-flex';
}

// --- LÓGICA REGRAS ---
async function startConferidorManobras(e) {
    e.preventDefault();
    const payload = {
        manobra: document.getElementById('cm-manobra').value,
        usuario: document.getElementById('conf-user').value,
        senha: document.getElementById('conf-pass').value
    };

    document.getElementById('btn-cm-start').disabled = true;
    document.getElementById('btn-cm-start').classList.add('btn-loading');
    document.getElementById('pane-cm-results').style.display = 'block';
    document.getElementById('cm-skeleton').classList.add('active');
    document.getElementById('cm-report-content').style.display = 'none';
    document.getElementById('cm-progress-container').style.display = 'block';
    document.getElementById('cm-progress-bar').style.width = '0%';
    
    document.getElementById('cm-report-content').innerHTML = '';
    document.getElementById('term-cm').textContent = "";
    
    toggleConsole('cm', false); // Mantém minimizado

    const res = await fetch('/conferidor_manobras/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });
    const data = await res.json();
    cmJobId = data.job_id;
    clearInterval(cmTimer);
    cmTimer = setInterval(pollConferidor, 1000);
}

async function pollConferidor() {
    const res = await fetch('/conferidor_manobras/status?job_id=' + cmJobId);
    const data = await res.json();
    const term = document.getElementById('term-cm');

    if (data.log) {
        updateTerminal(term, data.log);
        renderConferidorResults(data.log);
        
        // Simulação de progresso para regras (baseado em fases encontradas no log)
        const phases = (data.log.match(/FASE/g) || []).length;
        const perc = Math.min(95, phases * 25); // Assume ~4 fases principais
        document.getElementById('cm-progress-bar').style.width = perc + '%';
    }

    if (data.state === 'done') {
        clearInterval(cmTimer);
        document.getElementById('btn-cm-start').disabled = false;
        document.getElementById('btn-cm-start').classList.remove('btn-loading');
        document.getElementById('cm-progress-bar').style.width = '100%';
        setTimeout(() => {
            document.getElementById('cm-progress-container').style.display = 'none';
        }, 500);
    } else if (data.state === 'error') {
        clearInterval(cmTimer);
        document.getElementById('btn-cm-start').disabled = false;
        document.getElementById('btn-cm-start').classList.remove('btn-loading');
        document.getElementById('cm-skeleton').classList.remove('active');
        renderConferidorResults(data.log + "\n\n❌ ERRO: " + data.error);
    }
}

function renderConferidorResults(log) {
    // Se log for robusto o suficiente, removemos o skeleton
    if (log.length > 50) {
        document.getElementById('cm-skeleton').classList.remove('active');
        document.getElementById('cm-report-content').style.display = 'block';
    }

    const content = document.getElementById('cm-report-content');
    const dash = document.getElementById('cm-summary-dash');
    const lines = log.split('\n');

    let html = '';
    let currentPhase = null;
    let ruleItems = [];
    let stats = { ok: 0, fail: 0, warn: 0 };

    lines.forEach(line => {
        const l = line.trim();
        if (!l) return;

        if (l.includes('FASE')) {
            if (currentPhase) html += buildPhaseCard(currentPhase, ruleItems);
            currentPhase = l.replace(/===/g, '').trim();
            ruleItems = [];
        } else if (l.includes('REGRA')) {
            const isOk = l.includes('✅') || l.includes('OK');
            const isFail = l.includes('❌') || l.includes('FALHA');
            const isWarn = l.includes('⚠️') || l.includes('ALERTA');

            let icon = '🔵', cls = '';
            if (isOk) { icon = '✅'; cls = 'ok'; stats.ok++; }
            else if (isFail) { icon = '❌'; cls = 'fail'; stats.fail++; }
            else if (isWarn) { icon = '⚠️'; cls = 'warn'; stats.warn++; }

            const text = l.replace(/✅|❌|⚠️|OK|FALHA|ALERTA|===/g, '').replace('REGRA', '<b>REGRA</b>').trim();
            ruleItems.push(`<div class="rule-item" style="display:flex; gap:12px; padding:8px 0; border-bottom:1px solid rgba(255,255,255,0.03);"><span>${icon}</span><span style="font-size:13px; color:${cls==='fail'?'var(--danger)':(cls==='warn'?'var(--warn)':'inherit')}">${text}</span></div>`);
        }
    });

    if (currentPhase) html += buildPhaseCard(currentPhase, ruleItems);

    if (html) {
        content.innerHTML = html;
        dash.innerHTML = `
            <div class="summary-stat"><span class="stat-val" style="color:var(--accent)">${stats.ok}</span><span class="stat-label">OK</span></div>
            <div class="summary-stat"><span class="stat-val" style="color:var(--danger)">${stats.fail}</span><span class="stat-label">Falhas</span></div>
            <div class="summary-stat"><span class="stat-val" style="color:var(--warn)">${stats.warn}</span><span class="stat-label">Alertas</span></div>
        `;
    }
}

function buildPhaseCard(title, items) {
    if (items.length === 0) return '';
    return `
        <div class="card" style="padding:0; overflow:hidden; margin-bottom:12px;">
            <div style="background:rgba(255,255,255,0.04); padding:10px 20px; font-size:12px; font-weight:700; color:var(--primary); border-bottom:1px solid var(--border);">${title}</div>
            <div style="padding:10px 20px;">${items.join('')}</div>
        </div>
    `;
}

// --- INITIALIZATION ---
document.addEventListener('DOMContentLoaded', () => {
    setupCredentialSync();
    
    const di = document.getElementById('conf-di');
    const df = document.getElementById('conf-df');
    if (di) di.oninput = maskDate;
    if (df) df.oninput = maskDate;

    document.getElementById('form-conflitos').onsubmit = startConflitos;
    document.getElementById('form-conferidor_manobras').onsubmit = startConferidorManobras;

    document.getElementById('btn-conf-cancel').onclick = async () => {
        if (!confJobId) return;
        await fetch('/conflitos/stop', { 
            method: 'POST', 
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ job_id: confJobId }) 
        });
        document.getElementById('txt-conf-main').innerHTML = `<span style="color:var(--danger)">🛑 Interrompendo...</span>`;
    };

    // Poll status every 5s
    pollBackendStatus();
    setInterval(pollBackendStatus, 5000);

    // Initialize Lucide
    if (typeof lucide !== 'undefined') {
        lucide.createIcons();
    }
    
    // Default Tab
    showSection('conflitos', document.querySelector('.nav-item'));
});
