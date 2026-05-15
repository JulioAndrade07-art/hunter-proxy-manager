/**
 * main.js — Scanner de Proxies (Aba SCAN)
 * Responsável por: scan SSE, renderização de tabela, filtros, exportação
 */

// ── Estado ───────────────────────────────────────────────────
let allResults = [];
let activeSource = null;
let filterType = 'ALL';
let filterStatus = 'ALL';
let latencies = [];
let scanRunning = false;
let renderTimer = null;

// ── Utilitários de UI ─────────────────────────────────────────
export function switchTab(tabId) {
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
    document.getElementById(`tab-${tabId}`).classList.add('active');
    document.querySelector(`.tab-btn[data-tab="${tabId}"]`).classList.add('active');
}

function log(msg, cls = 'log-info') {
    const el = document.getElementById('logArea');
    const d = document.createElement('div');
    d.className = cls;
    d.textContent = `> ${msg}`;
    el.appendChild(d);
    el.scrollTop = el.scrollHeight;
}

function setStats(total, alive, dead) {
    document.getElementById('statTotal').textContent = total;
    document.getElementById('statAlive').textContent = alive;
    document.getElementById('statDead').textContent = dead;
    document.getElementById('exportCount').textContent = `${alive} proxies vivas disponíveis para exportar`;
    if (latencies.length) {
        const avg = Math.round(latencies.reduce((a, b) => a + b, 0) / latencies.length);
        document.getElementById('statSpeed').textContent = avg + 'ms';
    }
}

function setProgress(done, total) {
    const pct = total > 0 ? Math.round(done / total * 100) : 0;
    document.getElementById('progressFill').style.width = pct + '%';
    document.getElementById('progressPct').textContent = pct + '%';
}

// ── Renderização de Tabela (com debounce) ─────────────────────
export function scheduleRenderTable() {
    if (!renderTimer) {
        renderTimer = setTimeout(() => { renderTable(); renderTimer = null; }, 300);
    }
}

function latencyBar(ms) {
    const max = 8000;
    const pct = Math.min(ms / max * 100, 100);
    const color = ms < 1000 ? 'var(--accent2)' : ms < 3000 ? 'var(--warn)' : 'var(--danger)';
    return `<span class="latency-bar">
    <span class="lat-num" style="color:${color}">${ms}ms</span>
    <span class="lat-track"><span class="lat-fill" style="width:${pct}%;background:${color}"></span></span>
  </span>`;
}

function renderTable() {
    const search = document.getElementById('searchInput').value.toLowerCase();
    const rows = allResults.filter(r => {
        if (filterType !== 'ALL' && r.type !== filterType) return false;
        if (filterStatus !== 'ALL' && r.status !== filterStatus) return false;
        if (search && !r.host.includes(search)) return false;
        return true;
    });

    const tbody = document.getElementById('tableBody');
    if (rows.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7"><div class="empty-state">
      <div class="icon">📡</div><div>Nenhuma proxy encontrada.</div>
    </div></td></tr>`;
        return;
    }

    const TYPE_BADGE = {
        HTTP: 'badge-http', HTTPS: 'badge-https', SOCKS4: 'badge-s4', SOCKS5: 'badge-s5'
    };

    tbody.innerHTML = rows.map((r, i) => {
        const badge = TYPE_BADGE[r.type] || 'badge-http';
        const latHtml = r.latency != null ? latencyBar(r.latency) : '<span style="color:var(--text-dim)">—</span>';
        return `<tr class="${r.status === 'alive' ? '' : 'dead-row'}">
      <td style="color:var(--text-dim)">${i + 1}</td>
      <td style="color:var(--text);letter-spacing:1px">${r.host}</td>
      <td><span class="badge ${badge}">${r.type}</span></td>
      <td><span class="status-dot">
        <span class="dot ${r.status === 'alive' ? 'dot-alive' : 'dot-dead'}"></span>
        <span style="color:${r.status === 'alive' ? 'var(--accent2)' : 'var(--danger)'}">
          ${r.status === 'alive' ? 'ALIVE' : 'DEAD'}
        </span>
      </span></td>
      <td>${latHtml}</td>
      <td style="color:var(--text-dim)">${r.ip || '—'}</td>
      <td><button class="copy-btn" onclick="copyProxy('${r.host}')">COPIAR</button></td>
    </tr>`;
    }).join('');
}

// ── Filtros ───────────────────────────────────────────────────
export function toggleFilter(type, el) {
    filterType = type;
    el.closest('.filter-pills').querySelectorAll('.pill').forEach(p => p.classList.remove('active'));
    el.classList.add('active');
    scheduleRenderTable();
}

export function toggleStatus(st, el) {
    filterStatus = st === 'alive' ? 'alive' : 'ALL';
    el.parentElement.querySelectorAll('.pill').forEach(p => p.classList.remove('active'));
    el.classList.add('active');
    scheduleRenderTable();
}

// ── Scan ──────────────────────────────────────────────────────
export function startScan() {
    if (scanRunning) return;
    scanRunning = true;
    allResults = []; latencies = [];

    const btnFetch = document.getElementById('btnFetch');
    btnFetch.disabled = true;
    btnFetch.classList.add('running');
    document.getElementById('btnStop').disabled = false;
    document.getElementById('logArea').innerHTML = '';

    log('Iniciando coleta de proxies de múltiplas fontes...', 'log-hl');
    setStats(0, 0, 0);
    setProgress(0, 1);

    activeSource = new EventSource('/api/test-stream');

    activeSource.onmessage = function (ev) {
        const data = JSON.parse(ev.data);

        if (data.event === 'start') {
            log(`Total de proxies coletadas: ${data.total}`, 'log-warn');
            log(`Testando com ${data.total} proxies em paralelo...`, 'log-info');
        }
        if (data.event === 'result') {
            const r = data.result;
            allResults.unshift(r);
            if (r.status === 'alive') {
                if (r.latency) latencies.push(r.latency);
                log(`✓ ALIVE  ${r.host}  [${r.type}]  ${r.latency}ms  ${r.ip}`, 'log-ok');
            }
            setStats(data.total, data.alive, data.dead);
            setProgress(data.processed, data.total);
            scheduleRenderTable();
        }
        if (data.event === 'done') {
            log(`─── Scan concluído! ${data.alive} vivas / ${data.dead} mortas ───`, 'log-hl');
            finishScan();
        }
    };

    activeSource.onerror = function () {
        log('Conexão SSE perdida.', 'log-err');
        finishScan();
    };
}

export function stopScan() {
    if (activeSource) { activeSource.close(); activeSource = null; }
    log('Scan interrompido pelo usuário.', 'log-warn');
    finishScan();
}

function finishScan() {
    scanRunning = false;
    const btnFetch = document.getElementById('btnFetch');
    btnFetch.disabled = false;
    btnFetch.classList.remove('running');
    document.getElementById('btnStop').disabled = true;
}

export function clearResults() {
    if (scanRunning) { stopScan(); }
    allResults = []; latencies = [];
    setStats(0, 0, 0);
    setProgress(0, 1);
    document.getElementById('logArea').innerHTML = '';
    renderTable();
}

// ── Clipboard ─────────────────────────────────────────────────
export function copyProxy(host) {
    navigator.clipboard.writeText(host).then(() => {
        log(`Copiado: ${host}`, 'log-ok');
    }).catch(() => {
        log(`Erro ao copiar: ${host}`, 'log-err');
    });
}

// ── Exportação ────────────────────────────────────────────────
function aliveProxies() {
    return allResults.filter(r => r.status === 'alive');
}

function download(name, content, mime) {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([content], { type: mime }));
    a.download = name;
    a.click();
}

export function exportTXT() {
    download('proxies.txt', aliveProxies().map(r => `${r.type}://${r.host}`).join('\n'), 'text/plain');
}
export function exportJSON() {
    download('proxies.json', JSON.stringify(aliveProxies(), null, 2), 'application/json');
}
export function exportCSV() {
    const rows = ['host,type,latency_ms,ip_externo',
        ...aliveProxies().map(r => `${r.host},${r.type},${r.latency ?? ''},${r.ip ?? ''}`)
    ];
    download('proxies.csv', rows.join('\n'), 'text/csv');
}
