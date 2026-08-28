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
    
    document.getElementById('term-conf').textContent = "";
    document.getElementById('txt-conf-main').textContent = "Iniciando...";

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

async function pollConf() {
    if (!confJobId) return;
    try {
        const res = await fetch('/conflitos/status?job_id=' + confJobId);
        if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            throw new Error(errData.error || `Erro HTTP ${res.status}`);
        }
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
    document.getElementById('conf-table-real').style.display = 'table';
    
    document.getElementById('pane-conf-status').style.display = 'none';
    document.getElementById('pane-conf-results').style.display = 'block';

    const manobraBase = (data.base || confCurrentManobra || document.getElementById('conf-manobra').value || '').trim();
    const eqManual = (confCurrentEqpt || document.getElementById('conf-eq-manual').value || '').trim();
    const alManual = (confCurrentAlim || document.getElementById('conf-al-manual').value || '').trim();
    const eqAlTarget = [eqManual, alManual].filter(Boolean).join(' / ') || 'SOLICITADOS';

    const totalConflicts = (data.conflitos ? data.conflitos.length : 0) + (data.conflitos_internos ? data.conflitos_internos.length : 0);
    const hasConflicts = totalConflicts > 0;
    const isManobraSearch = Boolean(manobraBase);

    let opMessage = '';
    if (isManobraSearch) {
        if (!hasConflicts) {
            opMessage = `NENHUM CONFLITO IDENTIFICADO PARA MANOBRA ${manobraBase}`;
        } else {
            opMessage = `IDENTIFICADO CONFLITO IDENTIFICADO PARA MANOBRA ${manobraBase}`;
        }
    } else {
        if (!hasConflicts) {
            opMessage = `NENHUM CONFLITO IDENTIFICADO PARA EQPT E ALIM ${eqAlTarget}`;
        } else {
            opMessage = `IDENTIFICADO CONFLITO IDENTIFICADO PARA EQPT E ALIM ${eqAlTarget}`;
        }
    }

    const summaryBar = document.getElementById('conf-summary-bar');
    const totalManobras = data.total_unico_sem_base || 0;
    const elapsed = data.elapsed || '0s';

    const bannerBg = hasConflicts ? 'rgba(239, 68, 68, 0.12)' : 'rgba(16, 185, 129, 0.12)';
    const bannerBorder = hasConflicts ? 'rgba(239, 68, 68, 0.35)' : 'rgba(16, 185, 129, 0.35)';
    const bannerColor = hasConflicts ? 'var(--danger)' : 'var(--accent)';
    const icon = hasConflicts ? '⚠️' : '✅';
    const subText = `${totalConflicts} conflito(s) em ${totalManobras} manobra(s) analisada(s) (${elapsed}).`;

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

    if (data.conflitos) {
        data.conflitos.forEach(c => {
            const tr = document.createElement('tr');
            tr.innerHTML = `<td><b>${c.manobra}</b></td><td>${c.situacoes.join(', ')}</td><td>${c.equipamentos.join('; ')}</td><td>${c.alimentadores.join('; ')}</td>`;
            tbody.appendChild(tr);
        });
    }
    
    const exportBtn = document.getElementById('lnk-conf-export');
    exportBtn.href = `/conflitos/export?job_id=${confJobId}`;
    exportBtn.style.display = 'inline-flex';

    if (window.lucide) lucide.createIcons();
}

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
        renderConferidorResults("❌ ERRO AO INICIAR: " + err.message);
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
            renderConferidorResults(data.log || "");
            setTimeout(() => {
                document.getElementById('cm-progress-container').style.display = 'none';
            }, 500);
        } else if (data.state === 'error') {
            clearInterval(cmTimer);
            document.getElementById('btn-cm-start').disabled = false;
            document.getElementById('btn-cm-start').classList.remove('btn-loading');
            document.getElementById('cm-skeleton').classList.remove('active');
            renderConferidorResults((data.log || "") + "\n\n❌ ERRO: " + data.error);
        }
    } catch (err) {
        clearInterval(cmTimer);
        document.getElementById('btn-cm-start').disabled = false;
        document.getElementById('btn-cm-start').classList.remove('btn-loading');
        document.getElementById('cm-skeleton').classList.remove('active');
        renderConferidorResults("❌ ERRO NO MONITORAMENTO: " + err.message);
    }
}

function stripAnsi(text) {
    if (!text) return '';
    return text.replace(/[\u001b\x1b]\[[0-9;]*[a-zA-Z]/g, '').trim();
}

function renderConferidorResults(log) {
    if (log.length > 50) {
        document.getElementById('cm-skeleton').classList.remove('active');
        document.getElementById('cm-report-content').style.display = 'block';
    }

    const content = document.getElementById('cm-report-content');
    const dash = document.getElementById('cm-summary-dash');
    const lines = log.split('\n');

    let cardsHtml = '';
    let currentPhase = null;
    let ruleItems = [];
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
                let text = l.replace(/❌|FALHA|===/g, '').trim();
                text = text.replace(/(REGRA\s*\d+)/gi, '<b>$1</b>').replace(/:\s*:/g, ':').trim();
                ruleItems.push(`
                    <div class="rule-item" style="display:flex; align-items:flex-start; gap:12px; padding:10px 0; border-bottom:1px solid rgba(255,255,255,0.05);">
                        <span style="font-size:16px;">❌</span>
                        <span style="font-size:13px; color:var(--danger); font-weight:500; line-height:1.4;">${text}</span>
                    </div>
                `);
            } else if (isWarn) {
                stats.warn++;
                let text = l.replace(/⚠️|ALERTA|===/g, '').trim();
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

    const manobraInputVal = (document.getElementById('cm-manobra')?.value || cmCurrentManobra || '').trim();
    const manobraCode = manobraInputVal ? manobraInputVal : 'SOLICITADA';

    let bannerHtml = '';
    let cmOpMessage = '';
    if (stats.fail === 0 && stats.warn === 0) {
        cmOpMessage = `MANOBRA ${manobraCode} FOI CONFERIDA, ESTÁ TUDO OK, MAS NÃO ESQUEÇA DE FAZER SUA VERIFICAÇÃO!`;
        bannerHtml = `
            <div class="alert-banner success-banner" style="background: rgba(16, 185, 129, 0.12); border: 1px solid rgba(16, 185, 129, 0.35); border-radius: 8px; padding: 16px 20px; margin-bottom: 20px; display: flex; align-items: center; gap: 14px;">
                <div style="font-size: 26px;">✅</div>
                <div>
                    <div style="font-size: 15px; font-weight: 700; color: var(--accent);">
                        ${cmOpMessage}
                    </div>
                    <div style="font-size: 12px; color: var(--text-muted); margin-top: 4px;">
                        Nenhuma divergência ou alerta foi identificado nas regras automáticas.
                    </div>
                </div>
            </div>
        `;
    } else {
        cmOpMessage = `MANOBRA ${manobraCode} FOI CONFERIDA, PORÉM FOI IDENTIFICADO ESSA(S) DIVERGÊNCIA(S):`;
        bannerHtml = `
            <div class="alert-banner warning-banner" style="background: rgba(239, 68, 68, 0.12); border: 1px solid rgba(239, 68, 68, 0.35); border-radius: 8px; padding: 16px 20px; margin-bottom: 20px; display: flex; align-items: center; gap: 14px;">
                <div style="font-size: 26px;">⚠️</div>
                <div>
                    <div style="font-size: 15px; font-weight: 700; color: var(--danger);">
                        ${cmOpMessage}
                    </div>
                    <div style="font-size: 12px; color: var(--text-muted); margin-top: 4px;">
                        Apontado(s) ${stats.fail} erro(s)/falha(s) e ${stats.warn} alerta(s). Detalhes abaixo:
                    </div>
                </div>
            </div>
        `;
    }

    content.innerHTML = bannerHtml + cardsHtml;

    if (window.lucide) lucide.createIcons();

    if (dash) {
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
