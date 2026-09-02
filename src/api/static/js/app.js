// --- GERENCIADOR DE TERMINAIS (ESTADO GLOBAL) ---
let currentTermTab = 'all';
let termLogMemory = [];
let lastLogId = 0;
let termPollInterval = null;

// --- ESTADO DOS JOBS DE VERIFICAÇÃO ---
let confJobId = null;
let confTimer = null;
let cmJobId = null;
let cmTimer = null;
let cmCurrentManobra = '';
let confCurrentManobra = '';
let confCurrentEqpt = '';
let confCurrentAlim = '';

function copyToClipboard(text) {
    if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(text).then(() => {
            showToast('Comunicação Operativa copiada!');
        }).catch(() => {
            fallbackCopy(text);
        });
    } else {
        fallbackCopy(text);
    }
}

function fallbackCopy(text) {
    const textArea = document.createElement('textarea');
    textArea.value = text;
    textArea.style.position = 'fixed';
    textArea.style.left = '-999999px';
    document.body.appendChild(textArea);
    textArea.focus();
    textArea.select();
    try {
        document.execCommand('copy');
        showToast('Comunicação Operativa copiada!');
    } catch (err) {
        alert('Texto: ' + text);
    }
    document.body.removeChild(textArea);
}

function showToast(msg) {
    let toast = document.getElementById('app-toast');
    if (!toast) {
        toast = document.createElement('div');
        toast.id = 'app-toast';
        toast.style.cssText = 'position:fixed; bottom:20px; right:20px; background:var(--primary); color:#fff; padding:10px 18px; border-radius:6px; font-size:13px; font-weight:600; z-index:9999; box-shadow:0 4px 12px rgba(0,0,0,0.3); transition:opacity 0.3s; opacity:0; pointer-events:none;';
        document.body.appendChild(toast);
    }
    toast.textContent = msg;
    toast.style.opacity = '1';
    setTimeout(() => { toast.style.opacity = '0'; }, 2500);
}

// --- GERENCIADOR DE AUTENTICAÇÃO DE ADMIN ---
let adminToken = sessionStorage.getItem('gdis_admin_token') || null;

function getAuthHeaders(headers = {}) {
    const h = { ...headers };
    if (adminToken) {
        h['X-Admin-Token'] = adminToken;
    }
    return h;
}

function updateAdminUIState(authenticated) {
    const navTerminal = document.getElementById('nav-item-terminal');
    const btnText = document.getElementById('btn-admin-text');
    const btnIcon = document.querySelector('#btn-admin-auth .icon');

    if (authenticated) {
        if (navTerminal) navTerminal.style.display = 'flex';
        if (btnText) btnText.textContent = 'Admin (Sair)';
        if (btnIcon && typeof lucide !== 'undefined') {
            btnIcon.setAttribute('data-lucide', 'unlock');
            lucide.createIcons();
        }
    } else {
        if (navTerminal) {
            navTerminal.style.display = 'none';
            const sec = document.getElementById('section-terminal');
            if (sec && sec.style.display !== 'none') {
                showSection('conflitos', document.querySelector('.nav-item'));
            }
        }
        if (btnText) btnText.textContent = 'Área do Administrador';
        if (btnIcon && typeof lucide !== 'undefined') {
            btnIcon.setAttribute('data-lucide', 'lock');
            lucide.createIcons();
        }
    }
}

async function checkAdminSession() {
    if (!adminToken) {
        updateAdminUIState(false);
        return;
    }
    try {
        const res = await fetch('/hub/auth/check', {
            headers: getAuthHeaders()
        });
        const data = await res.json();
        if (data.authenticated) {
            updateAdminUIState(true);
        } else {
            logoutAdmin();
        }
    } catch (e) {
        updateAdminUIState(false);
    }
}

function toggleAdminAuth() {
    if (adminToken) {
        logoutAdmin();
    } else {
        const modal = document.getElementById('modal-admin-login');
        const errDiv = document.getElementById('admin-login-error');
        const pwdInput = document.getElementById('admin-password-input');
        if (errDiv) errDiv.style.display = 'none';
        if (pwdInput) pwdInput.value = '';
        if (modal) modal.style.display = 'flex';
        setTimeout(() => pwdInput && pwdInput.focus(), 100);
    }
}

function closeAdminModal() {
    const modal = document.getElementById('modal-admin-login');
    if (modal) modal.style.display = 'none';
}

async function submitAdminLogin(event) {
    event.preventDefault();
    const pwdInput = document.getElementById('admin-password-input');
    const errDiv = document.getElementById('admin-login-error');
    const password = pwdInput ? pwdInput.value : '';

    if (errDiv) errDiv.style.display = 'none';

    try {
        const res = await fetch('/hub/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ password: password })
        });
        const data = await res.json();

        if (res.ok && data.success && data.token) {
            adminToken = data.token;
            sessionStorage.setItem('gdis_admin_token', adminToken);
            updateAdminUIState(true);
            closeAdminModal();
            const navTerminal = document.getElementById('nav-item-terminal');
            if (navTerminal) showSection('terminal', navTerminal);
            fetchTerminalLogs();
        } else {
            if (errDiv) {
                errDiv.textContent = data.message || 'Senha incorreta. Tente novamente.';
                errDiv.style.display = 'block';
            }
        }
    } catch (e) {
        if (errDiv) {
            errDiv.textContent = 'Erro de conexão ao validar credenciais.';
            errDiv.style.display = 'block';
        }
    }
}

function logoutAdmin() {
    adminToken = null;
    sessionStorage.removeItem('gdis_admin_token');
    updateAdminUIState(false);
}

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
    
    // Sincroniza o console com a aba selecionada
    if (id === 'terminal') {
        renderTerminalBox();
    } else {
        const consoleContext = (id === 'conferidor_manobras') ? 'cm' : 'conf';
        switchConsoleView(consoleContext);
    }

    // Atualiza título da página
    const titles = { 
        'conflitos': 'Verificador de Conflitos', 
        'conferidor_manobras': 'Conferidor de Manobras',
        'terminal': 'Gerenciador de Terminais',
        'config': 'Configurações do Sistema'
    };
    document.getElementById('current-page-title').textContent = titles[id] || 'Dashboard';
}

// Sincronização e Persistência de User/Pass por 10 Horas
const GDIS_CREDS_EXPIRY_MS = 10 * 60 * 60 * 1000;

function setupCredentialSync() {
    // 1. Restaurar credenciais salvas caso estejam dentro do limite de 10 horas
    const expiry = localStorage.getItem('gdis_creds_expiry');
    if (expiry && Date.now() < parseInt(expiry, 10)) {
        const savedUser = localStorage.getItem('gdis_user') || '';
        const savedPass = localStorage.getItem('gdis_pass') || '';
        document.querySelectorAll('.shared-user').forEach(x => { x.value = savedUser; });
        document.querySelectorAll('.shared-pass').forEach(x => { x.value = savedPass; });
    } else {
        localStorage.removeItem('gdis_user');
        localStorage.removeItem('gdis_pass');
        localStorage.removeItem('gdis_creds_expiry');
    }

    function saveCredentials() {
        const userVal = document.querySelector('.shared-user')?.value || '';
        const passVal = document.querySelector('.shared-pass')?.value || '';
        
        if (userVal || passVal) {
            localStorage.setItem('gdis_user', userVal);
            localStorage.setItem('gdis_pass', passVal);
            localStorage.setItem('gdis_creds_expiry', (Date.now() + GDIS_CREDS_EXPIRY_MS).toString());
        } else {
            localStorage.removeItem('gdis_user');
            localStorage.removeItem('gdis_pass');
            localStorage.removeItem('gdis_creds_expiry');
        }
    }

    document.querySelectorAll('.shared-user').forEach(el => {
        el.addEventListener('input', (e) => {
            const val = e.target.value;
            document.querySelectorAll('.shared-user').forEach(x => { if (x !== e.target) x.value = val; });
            saveCredentials();
        });
    });
    document.querySelectorAll('.shared-pass').forEach(el => {
        el.addEventListener('input', (e) => {
            const val = e.target.value;
            document.querySelectorAll('.shared-pass').forEach(x => { if (x !== e.target) x.value = val; });
            saveCredentials();
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

// Status do Backend & Processos
async function pollBackendStatus() {
    try {
        const res = await fetch('/hub/status');
        const data = await res.json();
        
        const confDot = document.getElementById('status-dot-conf');
        const cmDot = document.getElementById('status-dot-cm');
        const badgeConf = document.getElementById('badge-conflitos');
        const badgeCm = document.getElementById('badge-conferidor_manobras');

        // Status Conflitos
        const confOnline = data.conflitos && data.conflitos.running;
        if (confDot) confDot.className = confOnline ? 'dot online' : 'dot offline';
        if (badgeConf) badgeConf.className = confOnline ? 'dot online' : 'dot offline';

        // Status Conferidor
        const cmOnline = data.conferidor_manobras && data.conferidor_manobras.running;
        if (cmDot) cmDot.className = cmOnline ? 'dot online' : 'dot offline';
        if (badgeCm) badgeCm.className = cmOnline ? 'dot online' : 'dot offline';

        // Atualiza Badge do Terminal Ativo no Dashboard
        updateTermStatusBadge(data);
    } catch (e) {
        console.error("Erro ao verificar status dos backends", e);
    }
}

function updateTermStatusBadge(statusData) {
    const badge = document.getElementById('term-status-info');
    if (!badge) return;

    if (currentTermTab === 'all') {
        badge.innerHTML = `<span class="dot online"></span> <span>PAINEL CONSOLIDADO</span>`;
    } else if (statusData && statusData[currentTermTab]) {
        const info = statusData[currentTermTab];
        const isRun = info.running;
        const pidStr = info.pid ? ` (PID: ${info.pid})` : '';
        badge.innerHTML = `<span class="dot ${isRun ? 'online' : 'offline'}"></span> <span>${isRun ? 'RODANDO' : 'PARADO'}${pidStr}</span>`;
    }
}

// --- LOG STREAMING & GERENCIADOR DE TERMINAIS ---
async function fetchTerminalLogs() {
    if (!adminToken) return;
    try {
        const res = await fetch(`/hub/terminal/logs?service=all&since=${lastLogId}`, {
            headers: getAuthHeaders()
        });
        if (res.status === 401) {
            logoutAdmin();
            return;
        }
        const data = await res.json();

        if (data.logs && data.logs.length > 0) {
            data.logs.forEach(entry => {
                termLogMemory.push(entry);
                if (entry.id > lastLogId) lastLogId = entry.id;

                // Atualiza também o Console Drawer legado
                appendToConsoleDrawer(entry);
            });

            // Limita memória local a 3000 entradas
            if (termLogMemory.length > 3000) {
                termLogMemory = termLogMemory.slice(termLogMemory.length - 3000);
            }

            renderTerminalBox();
        }
    } catch (e) {
        console.error("Erro ao buscar logs do terminal", e);
    }
}

function appendToConsoleDrawer(entry) {
    let drawerContext = 'hub';
    if (entry.service === 'conflitos') drawerContext = 'conf';
    else if (entry.service === 'conferidor_manobras') drawerContext = 'cm';

    const termDiv = document.getElementById('term-' + drawerContext);
    if (!termDiv) return;

    const lineDiv = document.createElement('div');
    lineDiv.className = 'log-line';
    
    let cls = 'log-info';
    if (entry.text.includes('[ERROR]') || entry.text.includes('ERRO')) cls = 'log-error';
    else if (entry.text.includes('[WARN]')) cls = 'log-warn';
    else if (entry.text.includes('[SUCCESS]') || entry.text.includes('OK')) cls = 'log-success';
    else if (entry.text.includes('[CONFLITO]')) cls = 'log-conflito';

    lineDiv.classList.add(cls);
    lineDiv.textContent = `[${entry.time}] ${entry.text}`;

    termDiv.appendChild(lineDiv);
    
    // Auto-scroll do console drawer se visível
    if (termDiv.style.display !== 'none') {
        termDiv.scrollTop = termDiv.scrollHeight;
    }
}

function selectTerminalTab(service) {
    currentTermTab = service;
    
    document.querySelectorAll('.term-tab-btn').forEach(btn => {
        if (btn.getAttribute('data-service') === service) {
            btn.classList.add('active');
        } else {
            btn.classList.remove('active');
        }
    });

    pollBackendStatus();
    renderTerminalBox();
}

function renderTerminalBox() {
    const box = document.getElementById('term-full-output');
    if (!box) return;

    const query = (document.getElementById('term-search-filter')?.value || '').toLowerCase().trim();
    const autoScroll = document.getElementById('term-autoscroll')?.checked;

    let filtered = termLogMemory;

    // Filtro por Serviço
    if (currentTermTab !== 'all') {
        filtered = filtered.filter(e => e.service === currentTermTab);
    }

    // Filtro por Palavra-Chave
    if (query) {
        filtered = filtered.filter(e => e.text.toLowerCase().includes(query) || e.time.includes(query));
    }

    let html = '';
    filtered.forEach(entry => {
        let textCls = '#cbd5e1';
        const txtUpper = entry.text.toUpperCase();
        
        if (txtUpper.includes('ERROR') || txtUpper.includes('ERRO') || txtUpper.includes('FALHA') || txtUpper.includes('CRITICAL')) {
            textCls = '#f87171'; // Vermelho
        } else if (txtUpper.includes('WARN') || txtUpper.includes('AVISO')) {
            textCls = '#fbbf24'; // Amarelo
        } else if (txtUpper.includes('SUCCESS') || txtUpper.includes('[OK]') || txtUpper.includes('ATIVO')) {
            textCls = '#34d399'; // Verde
        } else if (txtUpper.includes('[START]') || txtUpper.includes('[STOP]') || txtUpper.includes('INICIANDO')) {
            textCls = '#60a5fa'; // Azul
        }

        const tagClass = 'tag-' + entry.service;
        const svcLabel = entry.service === 'conferidor_manobras' ? 'CONF' : entry.service.toUpperCase();

        html += `
            <div class="term-line">
                <span class="term-time">${entry.time}</span>
                <span class="term-svc-tag ${tagClass}">${svcLabel}</span>
                <span class="term-text" style="color: ${textCls};">${escapeHtml(entry.text)}</span>
            </div>
        `;
    });

    box.innerHTML = html || `<div style="color: #64748b; font-style: italic; padding: 20px;">Nenhum log registrado para este filtro.</div>`;

    if (autoScroll) {
        box.scrollTop = box.scrollHeight;
    }
}

function filterTerminalLogs() {
    renderTerminalBox();
}

async function termAction(action, service = null) {
    const targetService = service || currentTermTab;
    try {
        const res = await fetch('/hub/terminal/action', {
            method: 'POST',
            headers: getAuthHeaders({ 'Content-Type': 'application/json' }),
            body: JSON.stringify({ action: action, service: targetService })
        });
        if (res.status === 401) {
            logoutAdmin();
            alert("Sessão de administrador expirada. Faça login novamente.");
            return;
        }
        const data = await res.json();
        pollBackendStatus();
        fetchTerminalLogs();
    } catch (e) {
        console.error("Erro ao executar ação no terminal", e);
    }
}

function termActionForActive(action) {
    if (currentTermTab === 'all' && ['start', 'stop', 'restart'].includes(action)) {
        termAction(action + '_all');
    } else {
        termAction(action, currentTermTab);
    }
}

async function clearTerminalLogs() {
    try {
        const res = await fetch('/hub/terminal/clear', {
            method: 'POST',
            headers: getAuthHeaders({ 'Content-Type': 'application/json' }),
            body: JSON.stringify({ service: currentTermTab })
        });
        if (res.status === 401) {
            logoutAdmin();
            alert("Sessão de administrador expirada. Faça login novamente.");
            return;
        }
        if (currentTermTab === 'all') {
            termLogMemory = [];
        } else {
            termLogMemory = termLogMemory.filter(e => e.service !== currentTermTab);
        }
        renderTerminalBox();
    } catch (e) {
        console.error("Erro ao limpar logs", e);
    }
}

function downloadTerminalLogs() {
    let filtered = termLogMemory;
    if (currentTermTab !== 'all') {
        filtered = filtered.filter(e => e.service === currentTermTab);
    }

    const textContent = filtered.map(e => `[${e.time}] [${e.service.toUpperCase()}] ${e.text}`).join('\n');
    const blob = new Blob([textContent], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    
    const a = document.createElement('a');
    a.href = url;
    a.download = `gdis_terminal_${currentTermTab}_${new Date().toISOString().slice(0,10)}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

function escapeHtml(text) {
    return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

// --- CONSOLE DRAWER ---
function toggleConsole(context, forceExpand = null, event = null) {
    if (event) event.stopPropagation();
    const drawer = document.getElementById('console-drawer');
    
    let shouldExpand;
    if (typeof forceExpand === 'boolean') {
        shouldExpand = forceExpand;
    } else {
        shouldExpand = !drawer.classList.contains('expanded');
    }
    
    if (shouldExpand) drawer.classList.add('expanded');
    else drawer.classList.remove('expanded');

    const icon = document.getElementById('console-toggle-icon');
    if (icon) {
        if (typeof lucide !== 'undefined') {
            icon.setAttribute('data-lucide', shouldExpand ? 'chevron-down' : 'chevron-up');
            lucide.createIcons();
        } else {
            icon.textContent = shouldExpand ? '▼' : '▲';
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
    
    const term = document.getElementById('term-' + context);
    const tab = document.getElementById('tab-' + context);
    
    if (term) {
        term.style.display = 'block';
        requestAnimationFrame(() => {
            term.scrollTop = term.scrollHeight;
        });
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
            return;
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

    if (term.innerHTML !== html) {
        term.innerHTML = html;
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

    confCurrentManobra = manobra;
    confCurrentEqpt = eqManual;
    confCurrentAlim = alManual;

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
    document.getElementById('pane-conf-results').style.display = 'block';
    document.getElementById('conf-skeleton').classList.add('active');
    document.getElementById('conf-table-real').style.display = 'none';
    document.getElementById('conf-progress-container').style.display = 'block';
    document.getElementById('conf-progress-bar').style.width = '0%';
    
    // Limpeza de estado e resultados da conferência anterior
    document.getElementById('term-conf').textContent = "";
    document.getElementById('txt-conf-main').textContent = "Iniciando...";
    document.getElementById('txt-conf-small').textContent = "";
    document.getElementById('conf-summary-bar').innerHTML = "";
    document.getElementById('tbl-conf-body').innerHTML = "";
    document.getElementById('lnk-conf-export').style.display = 'none';

    toggleConsole('conf', true);

    try {
        const res = await fetch('/conflitos/start', { method: 'POST', body: params });
        if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            throw new Error(errData.error || errData.message || `Erro HTTP ${res.status}`);
        }
        const data = await res.json();
        if (!data.job_id) {
            throw new Error(data.error || "Servidor não retornou a identificação do Job.");
        }
        confJobId = data.job_id;
        clearInterval(confTimer);
        confTimer = setInterval(pollConf, 1000);
    } catch (err) {
        document.getElementById('txt-conf-main').innerHTML = `<span style="color:var(--danger)">❌ ${err.message}</span>`;
        document.getElementById('btn-conf-start').disabled = false;
        document.getElementById('btn-conf-start').classList.remove('btn-loading');
        document.getElementById('btn-conf-cancel').disabled = true;
        document.getElementById('conf-skeleton').classList.remove('active');
    }
}

let confPollFailures = 0;
async function pollConf() {
    if (!confJobId) return;
    try {
        const res = await fetch('/conflitos/status?job_id=' + confJobId);
        if (!res.ok) {
            confPollFailures++;
            if (confPollFailures < 3) return; // tolera até 2 oscilações de rede temporárias
            const errData = await res.json().catch(() => ({}));
            throw new Error(errData.error || `Erro HTTP ${res.status}`);
        }
        confPollFailures = 0;
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
            document.getElementById('btn-conf-start').classList.remove('btn-loading');
            document.getElementById('btn-conf-cancel').disabled = true;
            document.getElementById('conf-skeleton').classList.remove('active');
        }
    } catch (err) {
        clearInterval(confTimer);
        document.getElementById('txt-conf-main').innerHTML = `<span style="color:var(--danger)">❌ ${err.message}</span>`;
        document.getElementById('btn-conf-start').disabled = false;
        document.getElementById('btn-conf-start').classList.remove('btn-loading');
        document.getElementById('btn-conf-cancel').disabled = true;
        document.getElementById('conf-skeleton').classList.remove('active');
    }
}

function showConfResults(data) {
    document.getElementById('btn-conf-start').classList.remove('btn-loading');
    document.getElementById('conf-skeleton').classList.remove('active');
    document.getElementById('conf-progress-container').style.display = 'none';
    
    document.getElementById('pane-conf-status').style.display = 'none';
    document.getElementById('pane-conf-results').style.display = 'block';

    const bases = data.bases_analisadas || [];
    const manobraBase = (data.base || confCurrentManobra || document.getElementById('conf-manobra').value || '').trim();
    const eqManual = (confCurrentEqpt || document.getElementById('conf-eq-manual').value || '').trim();
    const alManual = (confCurrentAlim || document.getElementById('conf-al-manual').value || '').trim();
    const eqAlTarget = [eqManual, alManual].filter(Boolean).join(' / ') || 'SOLICITADOS';

    const conflitosInternos = data.conflitos_internos || [];
    const conflitosGlobais = data.conflitos || [];
    const resultadoPorBase = data.resultado_por_base || {};
    
    // Ordena as sanfonas de manobras base por data de início
    const baseKeys = Object.keys(resultadoPorBase).sort((a, b) => {
        const da = resultadoPorBase[a].data_inicio || '';
        const db = resultadoPorBase[b].data_inicio || '';
        return da.localeCompare(db);
    });

    // Calcula total global de conflitos somando os conflitos das bases
    let totalConflicts = conflitosGlobais.length;
    if (baseKeys.length > 0) {
        totalConflicts = baseKeys.reduce((acc, k) => acc + (resultadoPorBase[k].conflitos || []).length, 0);
    } else {
        totalConflicts += conflitosInternos.length;
    }

    const hasConflicts = totalConflicts > 0;
    const elapsed = data.elapsed_seconds ? (data.elapsed_seconds + 's') : (data.elapsed || '0s');

    let opMessage = '';
    if (bases.length > 1) {
        opMessage = hasConflicts ? `CONFLITO(S) IDENTIFICADO(S) EM LOTE DE ${bases.length} MANOBRAS BASE` : `NENHUM CONFLITO IDENTIFICADO NO LOTE DE ${bases.length} MANOBRAS BASE`;
    } else if (bases.length === 1 || manobraBase) {
        const targetM = bases[0] || manobraBase;
        opMessage = hasConflicts ? `CONFLITO IDENTIFICADO PARA MANOBRA ${targetM}` : `NENHUM CONFLITO IDENTIFICADO PARA MANOBRA ${targetM}`;
    } else {
        opMessage = hasConflicts ? `CONFLITO IDENTIFICADO PARA EQPT E ALIM ${eqAlTarget}` : `NENHUM CONFLITO IDENTIFICADO PARA EQPT E ALIM ${eqAlTarget}`;
    }

    const summaryBar = document.getElementById('conf-summary-bar');
    const totalManobrasGdis = data.total_unico_sem_base || 0;

    const bannerBg = hasConflicts ? 'rgba(239, 68, 68, 0.12)' : 'rgba(16, 185, 129, 0.12)';
    const bannerBorder = hasConflicts ? 'rgba(239, 68, 68, 0.35)' : 'rgba(16, 185, 129, 0.35)';
    const bannerColor = hasConflicts ? 'var(--danger)' : 'var(--accent)';
    const icon = hasConflicts ? '⚠️' : '✅';
    const subText = `${totalConflicts} conflito(s) em ${totalManobrasGdis} manobra(s) pesquisadas (${elapsed}).`;

    summaryBar.innerHTML = `
        <div class="alert-banner" style="background: ${bannerBg}; border: 1px solid ${bannerBorder}; border-radius: 8px; padding: 16px 20px; margin-bottom: 20px; display: flex; align-items: center; gap: 14px;">
            <div style="font-size: 26px;">${icon}</div>
            <div>
                <div style="font-size: 15px; font-weight: 700; color: ${bannerColor}; font-family: monospace; letter-spacing: 0.5px;">
                    ${opMessage}
                </div>
                <div style="font-size: 12px; color: var(--text-muted); margin-top: 4px;">
                    ${subText}
                </div>
            </div>
        </div>
    `;

    // Renderização do container de Accordion
    const accordionContainer = document.getElementById('conf-accordion-container');
    accordionContainer.innerHTML = '';

    let accordionHtml = '';

    // Renderiza Sanfonas por Manobra Base
    if (baseKeys.length > 0) {
        baseKeys.forEach((mBase, idx) => {
            const info = resultadoPorBase[mBase];
            const conflicts = info.conflitos || [];
            const confCount = conflicts.length;
            const hasConf = confCount > 0;
            
            let badgeHtml = '';
            if (hasConf) {
                badgeHtml = `<span style="background: rgba(239, 68, 68, 0.15); color: var(--danger); border: 1px solid rgba(239, 68, 68, 0.3); padding: 4px 10px; border-radius: 6px; font-size: 12px; font-weight: 700;">⚠️ ${confCount} CONFLITO(S)</span>`;
            } else {
                badgeHtml = `<span style="background: rgba(16, 185, 129, 0.15); color: var(--accent); border: 1px solid rgba(16, 185, 129, 0.3); padding: 4px 10px; border-radius: 6px; font-size: 12px; font-weight: 700;">✅ SEM CONFLITOS</span>`;
            }

            const isCollapsed = (baseKeys.length > 1) && (!hasConf) && (idx > 0);
            const displayStyle = isCollapsed ? 'none' : 'block';

            let tableHtml = '';
            if (hasConf) {
                tableHtml = `
                    <table style="width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 13px;">
                        <thead>
                            <tr style="border-bottom: 1px solid var(--border); text-align: left; color: var(--text-muted);">
                                <th style="padding: 8px 10px;">Manobra Conflitante</th>
                                <th style="padding: 8px 10px;">Data</th>
                                <th style="padding: 8px 10px;">Situação</th>
                                <th style="padding: 8px 10px;">Tipo Conflito</th>
                                <th style="padding: 8px 10px;">Equipamentos</th>
                                <th style="padding: 8px 10px;">Alimentadores</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${conflicts.map(c => {
                                const isInterno = c.is_interno || (c.situacoes && c.situacoes.includes('LOTE_INTERNO'));
                                const sitBg = isInterno ? 'rgba(245,158,11,0.15)' : 'rgba(255,255,255,0.08)';
                                const sitColor = isInterno ? 'var(--warn)' : 'var(--text-main)';
                                const sitLabel = isInterno ? 'LOTE INTERNO' : (c.situacoes || []).join(', ');

                                const typeBg = isInterno ? 'rgba(245,158,11,0.15)' : 'rgba(239,68,68,0.15)';
                                const typeColor = isInterno ? 'var(--warn)' : 'var(--danger)';
                                const typeLabel = c.tipo_conflito || 'CONFLITO';

                                return `
                                <tr style="border-bottom: 1px solid rgba(255,255,255,0.05);">
                                    <td style="padding: 8px 10px;"><b>${c.manobra}</b></td>
                                    <td style="padding: 8px 10px;"><span style="font-size: 11px; color: var(--text-muted); font-weight: 500;">📅 ${c.data_manobra || info.data_inicio || '-'}</span></td>
                                    <td style="padding: 8px 10px;"><span style="font-size: 11px; padding: 2px 6px; background: ${sitBg}; color: ${sitColor}; border-radius: 4px; font-weight: 600;">${sitLabel}</span></td>
                                    <td style="padding: 8px 10px;"><span style="font-size: 11px; padding: 2px 6px; background: ${typeBg}; color: ${typeColor}; border-radius: 4px; font-weight: 600;">${typeLabel}</span></td>
                                    <td style="padding: 8px 10px;">${(c.equipamentos || []).join('; ') || '-'}</td>
                                    <td style="padding: 8px 10px;">${(c.alimentadores || []).join('; ') || '-'}</td>
                                </tr>
                                `;
                            }).join('')}
                        </tbody>
                    </table>
                `;
            } else {
                tableHtml = `<div style="padding: 12px; font-size: 13px; color: var(--text-muted);">✅ Nenhum conflito identificado para esta manobra no período.</div>`;
            }

            const eqptStr = (info.equipamentos || []).join(', ') || 'Nenhum';
            const alimStr = (info.alimentadores || []).join(', ') || 'Nenhum';
            const dateBadge = info.data_inicio ? `<span style="font-size: 11px; font-weight: 600; padding: 2px 8px; background: rgba(255,255,255,0.06); border-radius: 4px; color: var(--text-muted); border: 1px solid var(--border);">📅 ${info.data_inicio}</span>` : '';

            accordionHtml += `
                <div class="manobra-accordion-item" style="border: 1px solid var(--border); border-radius: 10px; margin-bottom: 16px; overflow: hidden; background: rgba(255,255,255,0.02);">
                    <div class="accordion-header" onclick="window.toggleConfAccordion('${mBase}')" style="display: flex; justify-content: space-between; align-items: center; padding: 14px 20px; background: rgba(255,255,255,0.04); cursor: pointer; user-select: none;">
                        <div style="display: flex; align-items: center; gap: 10px; font-weight: 700; font-size: 15px; color: var(--text-bright);">
                            <i data-lucide="layers" style="width: 18px; height: 18px; color: var(--primary);"></i>
                            <span>Manobra Base ${mBase}</span>
                            ${dateBadge}
                        </div>
                        <div style="display: flex; align-items: center; gap: 12px;">
                            ${badgeHtml}
                            <i data-lucide="chevron-down" id="conf-acc-icon-${mBase}" style="width: 18px; height: 18px; transition: transform 0.2s; ${isCollapsed ? '' : 'transform: rotate(180deg);'}"></i>
                        </div>
                    </div>
                    <div id="conf-acc-body-${mBase}" style="padding: 16px 20px; display: ${displayStyle}; border-top: 1px solid var(--border);">
                        <div style="font-size: 12px; color: var(--text-muted); margin-bottom: 12px; display: flex; flex-wrap: wrap; gap: 16px; background: rgba(0,0,0,0.15); padding: 8px 12px; border-radius: 6px;">
                            <span>📅 Período Base: <b>${info.data_inicio || 'N/A'}${info.data_fim && info.data_fim !== info.data_inicio ? ' até ' + info.data_fim : ''}</b></span>
                            <span>🔧 Equipamentos: <b>${eqptStr}</b></span>
                            <span>⚡ Alimentadores: <b>${alimStr}</b></span>
                        </div>
                        ${tableHtml}
                    </div>
                </div>
            `;
        });
    }

    accordionContainer.innerHTML = accordionHtml;

    // Tabela Legada / Consolidada
    const confTableReal = document.getElementById('conf-table-real');
    const tbody = document.getElementById('tbl-conf-body');
    tbody.innerHTML = '';

    if (conflitosInternos.length > 0) {
        conflitosInternos.forEach(c => {
            const tr = document.createElement('tr');
            tr.style.background = 'rgba(245, 158, 11, 0.05)';
            tr.innerHTML = `<td><span style="color:var(--warn)">⚠️ INTERNO</span></td><td>${c.origem} vs ${c.destino}</td><td>${(c.equipamentos || []).join('; ')}</td><td>${(c.alimentadores || []).join('; ')}</td>`;
            tbody.appendChild(tr);
        });
    }

    if (conflitosGlobais.length > 0) {
        conflitosGlobais.forEach(c => {
            const tr = document.createElement('tr');
            tr.innerHTML = `<td><b>${c.manobra}</b></td><td>${(c.situacoes || []).join(', ')}</td><td>${(c.equipamentos || []).join('; ')}</td><td>${(c.alimentadores || []).join('; ')}</td>`;
            tbody.appendChild(tr);
        });
    }

    // Se renderizamos a visão de sanfona, a tabela consolidada só é exibida se não houver sanfonas ou para depuração
    if (baseKeys.length > 0) {
        confTableReal.style.display = 'none';
    } else {
        confTableReal.style.display = 'table';
    }
    
    const exportBtn = document.getElementById('lnk-conf-export');
    exportBtn.href = `/conflitos/export?job_id=${confJobId}`;
    exportBtn.style.display = 'inline-flex';

    if (window.lucide) lucide.createIcons();
}

window.toggleConfAccordion = function(mBase) {
    const body = document.getElementById(`conf-acc-body-${mBase}`);
    const icon = document.getElementById(`conf-acc-icon-${mBase}`);
    if (!body) return;
    if (body.style.display === 'none') {
        body.style.display = 'block';
        if (icon) icon.style.transform = 'rotate(180deg)';
    } else {
        body.style.display = 'none';
        if (icon) icon.style.transform = 'rotate(0deg)';
    }
};

// --- LÓGICA REGRAS ---
async function startConferidorManobras(e) {
    e.preventDefault();
    const payload = {
        manobra: document.getElementById('cm-manobra').value,
        usuario: document.getElementById('conf-user').value,
        senha: document.getElementById('conf-pass').value
    };
    cmCurrentManobra = payload.manobra ? payload.manobra.trim() : '';

    document.getElementById('btn-cm-start').disabled = true;
    document.getElementById('btn-cm-start').classList.add('btn-loading');
    document.getElementById('pane-cm-results').style.display = 'block';
    document.getElementById('cm-skeleton').classList.add('active');
    document.getElementById('cm-report-content').style.display = 'none';
    document.getElementById('cm-progress-container').style.display = 'block';
    document.getElementById('cm-progress-bar').style.width = '0%';
    
    document.getElementById('cm-report-content').innerHTML = '';
    document.getElementById('cm-summary-dash').innerHTML = '';
    document.getElementById('term-cm').textContent = "";
    
    toggleConsole('cm', true);

    try {
        const res = await fetch('/conferidor_manobras/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            throw new Error(errData.error || errData.message || `Erro HTTP ${res.status}`);
        }
        const data = await res.json();
        if (!data.job_id) {
            throw new Error(data.error || "Servidor não retornou a identificação do Job.");
        }
        cmJobId = data.job_id;
        clearInterval(cmTimer);
        cmTimer = setInterval(pollConferidor, 1000);
    } catch (err) {
        document.getElementById('btn-cm-start').disabled = false;
        document.getElementById('btn-cm-start').classList.remove('btn-loading');
        document.getElementById('cm-skeleton').classList.remove('active');
        renderConferidorResults("❌ ERRO AO INICIAR: " + err.message, true);
    }
}

async function pollConferidor() {
    if (!cmJobId) return;
    try {
        const res = await fetch('/conferidor_manobras/status?job_id=' + cmJobId);
        if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            throw new Error(errData.error || `Erro HTTP ${res.status}`);
        }
        const data = await res.json();
        const term = document.getElementById('term-cm');

        if (data.log) {
            updateTerminal(term, data.log);
            
            const phases = (data.log.match(/FASE/g) || []).length;
            const perc = Math.min(95, phases * 25);
            document.getElementById('cm-progress-bar').style.width = perc + '%';
        }

        if (data.state === 'done') {
            clearInterval(cmTimer);
            document.getElementById('btn-cm-start').disabled = false;
            document.getElementById('btn-cm-start').classList.remove('btn-loading');
            document.getElementById('cm-progress-bar').style.width = '100%';
            renderConferidorResults(data.log || "", true);
            setTimeout(() => {
                document.getElementById('cm-progress-container').style.display = 'none';
            }, 500);
        } else if (data.state === 'error') {
            clearInterval(cmTimer);
            document.getElementById('btn-cm-start').disabled = false;
            document.getElementById('btn-cm-start').classList.remove('btn-loading');
            document.getElementById('cm-skeleton').classList.remove('active');
            renderConferidorResults((data.log || "") + "\n\n❌ ERRO: " + data.error, true);
        }
    } catch (err) {
        clearInterval(cmTimer);
        document.getElementById('btn-cm-start').disabled = false;
        document.getElementById('btn-cm-start').classList.remove('btn-loading');
        document.getElementById('cm-skeleton').classList.remove('active');
        renderConferidorResults("❌ ERRO NO MONITORAMENTO: " + err.message, true);
    }
}

function stripAnsi(text) {
    if (!text) return '';
    return text.replace(/[\u001b\x1b]\[[0-9;]*[a-zA-Z]/g, '').trim();
}

function parseMultiManobraLog(log) {
    const blocks = [];
    const lines = log.split('\n');
    let currentManobra = null;
    let currentLogLines = [];

    lines.forEach(line => {
        const rawLine = line.trim();
        const clean = stripAnsi(rawLine);

        const startMatch = clean.match(/>>> MANOBRA_START:\s*(\d+)/i);
        const endMatch = clean.match(/>>> MANOBRA_END:\s*(\d+)/i);

        if (startMatch) {
            if (currentManobra && currentLogLines.length > 0) {
                blocks.push({ manobra: currentManobra, log: currentLogLines.join('\n') });
            }
            currentManobra = startMatch[1];
            currentLogLines = [];
        } else if (endMatch) {
            if (currentManobra) {
                blocks.push({ manobra: currentManobra, log: currentLogLines.join('\n') });
                currentManobra = null;
                currentLogLines = [];
            }
        } else if (currentManobra) {
            currentLogLines.push(line);
        }
    });

    if (currentManobra && currentLogLines.length > 0) {
        blocks.push({ manobra: currentManobra, log: currentLogLines.join('\n') });
    }

    if (blocks.length === 0 && log.trim().length > 0) {
        const manobraMatch = log.match(/Manobra\s+(\d{6,10})/i);
        const inputVal = (document.getElementById('cm-manobra')?.value || cmCurrentManobra || '').trim();
        const mNum = manobraMatch ? manobraMatch[1] : (inputVal || 'SOLICITADA');
        blocks.push({ manobra: mNum, log: log });
    }

    return blocks;
}

function analyzeManobraBlock(block) {
    const lines = block.log.split('\n');
    let currentPhase = null;
    let ruleItems = [];
    let cardsHtml = '';
    let stats = { ok: 0, fail: 0, warn: 0 };

    lines.forEach(line => {
        const rawLine = line.trim();
        if (!rawLine) return;
        const l = stripAnsi(rawLine);
        if (!l) return;

        if (l.includes('FASE')) {
            if (currentPhase && ruleItems.length > 0) {
                cardsHtml += buildPhaseCard(currentPhase, ruleItems);
            }
            currentPhase = l.replace(/===/g, '').trim();
            ruleItems = [];
        } else if (l.includes('REGRA')) {
            const isOk = l.includes('✅') || l.includes('OK');
            const isFail = l.includes('❌') || l.includes('FALHA');
            const isWarn = l.includes('⚠️') || l.includes('ALERTA');

            if (isOk) {
                stats.ok++;
            } else if (isFail) {
                stats.fail++;
                let text = escapeHtml(l.replace(/❌|FALHA|===/g, '').trim());
                text = text.replace(/(REGRA\s*\d+)/gi, '<b>$1</b>').replace(/:\s*:/g, ':').trim();
                ruleItems.push(`
                    <div class="rule-item" style="display:flex; align-items:flex-start; gap:12px; padding:10px 0; border-bottom:1px solid rgba(255,255,255,0.05);">
                        <span style="font-size:16px;">❌</span>
                        <span style="font-size:13px; color:var(--danger); font-weight:500; line-height:1.4;">${text}</span>
                    </div>
                `);
            } else if (isWarn) {
                stats.warn++;
                let text = escapeHtml(l.replace(/⚠️|ALERTA|===/g, '').trim());
                text = text.replace(/(REGRA\s*\d+)/gi, '<b>$1</b>').replace(/:\s*:/g, ':').trim();
                ruleItems.push(`
                    <div class="rule-item" style="display:flex; align-items:flex-start; gap:12px; padding:10px 0; border-bottom:1px solid rgba(255,255,255,0.05);">
                        <span style="font-size:16px;">⚠️</span>
                        <span style="font-size:13px; color:var(--warn); font-weight:500; line-height:1.4;">${text}</span>
                    </div>
                `);
            }
        }
    });

    if (currentPhase && ruleItems.length > 0) {
        cardsHtml += buildPhaseCard(currentPhase, ruleItems);
    }

    const hasProcessingError = block.log.toLowerCase().includes('erro') || block.log.toLowerCase().includes('falha');

    return {
        manobra: block.manobra,
        stats,
        cardsHtml,
        hasProcessingError,
        rawLog: block.log
    };
}

function renderConferidorResults(log, jobDone = true) {
    if (jobDone) {
        document.getElementById('cm-skeleton').classList.remove('active');
        document.getElementById('cm-report-content').style.display = 'block';
    } else if (log.length > 50) {
        document.getElementById('cm-skeleton').classList.remove('active');
        document.getElementById('cm-report-content').style.display = 'block';
    }

    const content = document.getElementById('cm-report-content');
    const dash = document.getElementById('cm-summary-dash');
    
    const blocks = parseMultiManobraLog(log);
    const analyzedList = blocks.map(analyzeManobraBlock);

    let totalOk = 0;
    let totalFail = 0;
    let totalWarn = 0;

    analyzedList.forEach(item => {
        totalOk += item.stats.ok;
        totalFail += item.stats.fail;
        totalWarn += item.stats.warn;
    });

    if (dash) {
        dash.innerHTML = `
            <div class="summary-stat"><span class="stat-val" style="color:var(--primary)">${analyzedList.length}</span><span class="stat-label">Lote Total</span></div>
            <div class="summary-stat"><span class="stat-val" style="color:var(--accent)">${totalOk}</span><span class="stat-label">Regras OK</span></div>
            <div class="summary-stat"><span class="stat-val" style="color:var(--danger)">${totalFail}</span><span class="stat-label">Divergências</span></div>
            <div class="summary-stat"><span class="stat-val" style="color:var(--warn)">${totalWarn}</span><span class="stat-label">Alertas</span></div>
        `;
    }

    let accordionHtml = '';

    analyzedList.forEach((item, idx) => {
        const { manobra, stats, cardsHtml, hasProcessingError } = item;
        let badgeHtml = '';
        let bannerHtml = '';

        if (stats.ok > 0 && stats.fail === 0 && stats.warn === 0) {
            badgeHtml = `<span style="background: rgba(16, 185, 129, 0.15); color: var(--accent); border: 1px solid rgba(16, 185, 129, 0.3); padding: 4px 10px; border-radius: 6px; font-size: 12px; font-weight: 700;">✅ OK</span>`;
            bannerHtml = `
                <div class="alert-banner success-banner" style="background: rgba(16, 185, 129, 0.12); border: 1px solid rgba(16, 185, 129, 0.35); border-radius: 8px; padding: 14px 18px; margin-bottom: 16px; display: flex; align-items: center; gap: 12px;">
                    <div style="font-size: 22px;">✅</div>
                    <div>
                        <div style="font-size: 14px; font-weight: 700; color: var(--accent);">
                            MANOBRA ${manobra} CONFERIDA COM SUCESSO!
                        </div>
                        <div style="font-size: 12px; color: var(--text-muted); margin-top: 2px;">
                            Nenhuma divergência foi identificada nas regras automáticas.
                        </div>
                    </div>
                </div>
            `;
        } else if (stats.fail === 0 && stats.warn === 0 && stats.ok === 0) {
            if (hasProcessingError) {
                badgeHtml = `<span style="background: rgba(239, 68, 68, 0.15); color: var(--danger); border: 1px solid rgba(239, 68, 68, 0.3); padding: 4px 10px; border-radius: 6px; font-size: 12px; font-weight: 700;">❌ ERRO PROCESSAMENTO</span>`;
                bannerHtml = `
                    <div class="alert-banner warning-banner" style="background: rgba(239, 68, 68, 0.12); border: 1px solid rgba(239, 68, 68, 0.35); border-radius: 8px; padding: 14px 18px; margin-bottom: 16px; display: flex; align-items: center; gap: 12px;">
                        <div style="font-size: 22px;">❌</div>
                        <div>
                            <div style="font-size: 14px; font-weight: 700; color: var(--danger);">
                                FALHA NO PROCESSAMENTO DA MANOBRA ${manobra}
                            </div>
                            <div style="font-size: 12px; color: var(--text-muted); margin-top: 2px;">
                                Ocorreu uma exceção durante a execução. Consulte o console de logs.
                            </div>
                        </div>
                    </div>
                `;
            } else {
                badgeHtml = `<span style="background: rgba(245, 158, 11, 0.15); color: var(--warn); border: 1px solid rgba(245, 158, 11, 0.3); padding: 4px 10px; border-radius: 6px; font-size: 12px; font-weight: 700;">⏳ PROCESSANDO</span>`;
                bannerHtml = `
                    <div class="alert-banner warning-banner" style="background: rgba(245, 158, 11, 0.12); border: 1px solid rgba(245, 158, 11, 0.35); border-radius: 8px; padding: 14px 18px; margin-bottom: 16px; display: flex; align-items: center; gap: 12px;">
                        <div style="font-size: 22px;">ℹ️</div>
                        <div>
                            <div style="font-size: 14px; font-weight: 700; color: var(--warn);">
                                PROCESSANDO MANOBRA ${manobra}...
                            </div>
                        </div>
                    </div>
                `;
            }
        } else {
            badgeHtml = `<span style="background: rgba(239, 68, 68, 0.15); color: var(--danger); border: 1px solid rgba(239, 68, 68, 0.3); padding: 4px 10px; border-radius: 6px; font-size: 12px; font-weight: 700;">⚠️ ${stats.fail} DIVERGÊNCIA(S)</span>`;
            bannerHtml = `
                <div class="alert-banner warning-banner" style="background: rgba(239, 68, 68, 0.12); border: 1px solid rgba(239, 68, 68, 0.35); border-radius: 8px; padding: 14px 18px; margin-bottom: 16px; display: flex; align-items: center; gap: 12px;">
                    <div style="font-size: 22px;">⚠️</div>
                    <div>
                        <div style="font-size: 14px; font-weight: 700; color: var(--danger);">
                            MANOBRA ${manobra}: ${stats.fail} DIVERGÊNCIA(S) IDENTIFICADA(S)
                        </div>
                        <div style="font-size: 12px; color: var(--text-muted); margin-top: 2px;">
                            ${stats.fail} erro(s) e ${stats.warn} alerta(s). Detalhes abaixo:
                        </div>
                    </div>
                </div>
            `;
        }

        const isCollapsed = (analyzedList.length > 1) && (stats.fail === 0 && stats.warn === 0 && !hasProcessingError && idx > 0);
        const displayStyle = isCollapsed ? 'none' : 'block';

        accordionHtml += `
            <div class="manobra-accordion-item" style="border: 1px solid var(--border); border-radius: 10px; margin-bottom: 16px; overflow: hidden; background: rgba(255,255,255,0.02);">
                <div class="accordion-header" onclick="window.toggleManobraAccordion('${manobra}')" style="display: flex; justify-content: space-between; align-items: center; padding: 14px 20px; background: rgba(255,255,255,0.04); cursor: pointer; user-select: none;">
                    <div style="display: flex; align-items: center; gap: 10px; font-weight: 700; font-size: 15px; color: var(--text-bright);">
                        <i data-lucide="file-text" style="width: 18px; height: 18px; color: var(--primary);"></i>
                        <span>Manobra ${manobra}</span>
                    </div>
                    <div style="display: flex; align-items: center; gap: 12px;">
                        ${badgeHtml}
                        <i data-lucide="chevron-down" id="acc-icon-${manobra}" style="width: 18px; height: 18px; transition: transform 0.2s; ${isCollapsed ? '' : 'transform: rotate(180deg);'}"></i>
                    </div>
                </div>
                <div id="acc-body-${manobra}" style="padding: 16px 20px; display: ${displayStyle}; border-top: 1px solid var(--border);">
                    ${bannerHtml}
                    ${cardsHtml}
                </div>
            </div>
        `;
    });

    content.innerHTML = accordionHtml;

    if (window.lucide) lucide.createIcons();
}

window.toggleManobraAccordion = function(manobra) {
    const body = document.getElementById(`acc-body-${manobra}`);
    const icon = document.getElementById(`acc-icon-${manobra}`);
    if (!body) return;
    if (body.style.display === 'none') {
        body.style.display = 'block';
        if (icon) icon.style.transform = 'rotate(180deg)';
    } else {
        body.style.display = 'none';
        if (icon) icon.style.transform = 'rotate(0deg)';
    }
};

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
    
    // Verifica sessão de Administrador armazenada
    checkAdminSession();

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

    // Polling contínuo de status e de logs de terminal
    pollBackendStatus();
    setInterval(pollBackendStatus, 4000);

    fetchTerminalLogs();
    setInterval(fetchTerminalLogs, 1500);

    // Initialize Lucide
    if (typeof lucide !== 'undefined') {
        lucide.createIcons();
    }
    
    // Default Tab
    showSection('conflitos', document.querySelector('.nav-item'));
});
