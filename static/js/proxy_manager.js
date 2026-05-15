/**
 * proxy_manager.js — Gerenciador de Proxies Locais (Aba CRIAR PROXY)
 * Responsável por: lista de instâncias, polling de status, logs SSE, instruções
 */

// ── Estado ───────────────────────────────────────────────────
let proxiedInstances = [];
let selectedProxyPort = null;
let proxyPollingInterval = null;
let localProxyEventSource = null;

// ── Helpers de Form ───────────────────────────────────────────
export function toggleAuthFields() {
    const checked = document.getElementById('localProxyAuth').checked;
    document.getElementById('authFields').style.display = checked ? 'flex' : 'none';
}

// ── Polling de Status ─────────────────────────────────────────
async function loadProxies() {
    try {
        const res = await fetch('/api/proxy/status');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        proxiedInstances = await res.json();
        renderActiveProxies();

        if (selectedProxyPort !== null) {
            const proxy = proxiedInstances.find(p => p.port === selectedProxyPort);
            if (!proxy) {
                // A instância selecionada parou — deselecionar
                selectProxy(null);
            } else {
                document.getElementById('lProxyCount').textContent = proxy.req_count;
            }
        }
    } catch (err) {
        console.warn('[proxy_manager] loadProxies falhou:', err);
    }
}

// ── Renderização da Lista de Instâncias ───────────────────────
function renderActiveProxies() {
    const list = document.getElementById('activeProxiesList');
    if (proxiedInstances.length === 0) {
        list.innerHTML = `<div class="empty-state" style="padding:1rem;font-size:.65rem;">
      Nenhuma proxy local ativa.
    </div>`;
        return;
    }

    list.innerHTML = proxiedInstances.map(p => `
    <div class="local-proxy-card ${selectedProxyPort === p.port ? 'active' : ''}"
         onclick="window.proxyManager.selectProxy(${p.port})">
      <div style="display:flex;justify-content:space-between;align-items:center;">
        <div>
          <span class="status-dot"><span class="dot dot-alive"></span></span>
          <strong style="color:var(--text);font-size:.7rem;margin-left:4px;">Porta ${p.port}</strong>
          <span class="badge ${p.type === 'http' ? 'badge-http' : 'badge-s5'}"
                style="margin-left:6px;font-size:.5rem;padding:2px 4px;">
            ${p.type.toUpperCase()}
          </span>
        </div>
        <button class="btn btn-danger btn-small"
                style="margin:0;"
                onclick="window.proxyManager.stopLocalProxy(${p.port}, event)">✕</button>
      </div>
    </div>
  `).join('');
}

// ── Seleção de Instância ──────────────────────────────────────
export function selectProxy(port) {
    selectedProxyPort = port;
    renderActiveProxies();

    if (!port) {
        document.getElementById('lProxyStatus').textContent = 'NENHUM';
        document.getElementById('lProxyStatus').style.color = 'var(--text-dim)';
        document.getElementById('lProxyIP').textContent = '—';
        document.getElementById('lProxyCount').textContent = '0';
        document.getElementById('howToUsePanel').innerHTML =
            '<p>Selecione uma proxy na lista para ver as instruções de conexão.</p>';

        if (localProxyEventSource) {
            localProxyEventSource.close();
            localProxyEventSource = null;
        }
        document.getElementById('localProxyLogs').innerHTML =
            '<div class="log-info">&gt; Selecione uma proxy ativa.</div>';
        return;
    }

    const proxy = proxiedInstances.find(p => p.port === port);
    if (!proxy) return;

    document.getElementById('lProxyStatus').textContent = `P${proxy.port}`;
    document.getElementById('lProxyStatus').style.color = 'var(--accent2)';
    document.getElementById('lProxyIP').textContent = proxy.ip;
    document.getElementById('lProxyCount').textContent = proxy.req_count;

    renderHowToUse(proxy);
    reconnectLogsStream(proxy.port);
}

// ── Instruções Dinâmicas ──────────────────────────────────────
function renderHowToUse(proxy) {
    const displayAuth = proxy.auth_enabled ? `${proxy.user}:********@` : '';
    const simpleFormat = proxy.auth_enabled
        ? `${proxy.ip}:${proxy.port}:${proxy.user}:${proxy.pass}`
        : `${proxy.ip}:${proxy.port}`;

    const curlCmd = proxy.type === 'http'
        ? `curl -x http://${displayAuth}${proxy.ip}:${proxy.port} http://httpbin.org/ip`
        : `curl -x socks5://${displayAuth}${proxy.ip}:${proxy.port} http://httpbin.org/ip`;

    document.getElementById('howToUsePanel').innerHTML = `
    <div style="margin-bottom:1rem;">
      <strong style="color:var(--text);font-size:.8rem;letter-spacing:1px;">1. Endereço da Proxy</strong><br/>
      <code style="background:#071018;padding:3px 6px;border-radius:3px;color:var(--accent);
                   font-size:1.1em;display:inline-block;margin-top:5px;
                   border:1px solid rgba(0,229,255,0.3);">
        ${proxy.ip}:${proxy.port}
      </code>
    </div>
    <div style="margin-bottom:1rem;">
      <strong style="color:var(--text);font-size:.8rem;letter-spacing:1px;">2. Testar via CURL</strong><br/>
      <code style="background:#071018;padding:5px 8px;border-radius:3px;color:var(--accent2);
                   display:block;margin-top:5px;border:1px solid rgba(0,255,136,.3);word-wrap:break-word;">
        ${curlCmd}
      </code>
    </div>
    <div style="margin-bottom:1rem;">
      <strong style="color:var(--text);font-size:.8rem;letter-spacing:1px;">3. Configurar no Navegador / LAN</strong><br/>
      <ul style="margin-top:6px;padding-left:20px;line-height:1.8;">
        <li><strong>IP:</strong> <span style="color:var(--text);">${proxy.ip}</span>
            &nbsp;|&nbsp;<strong>Porta:</strong> <span style="color:var(--text);">${proxy.port}</span></li>
        <li><strong>Tipo:</strong> <span style="color:var(--warn);">${proxy.type === 'http' ? 'HTTP/HTTPS' : 'SOCKS V5'}</span></li>
        ${proxy.auth_enabled ? `<li><strong>Usuário:</strong> <span style="color:var(--text);">${proxy.user}</span></li>` : ''}
      </ul>
    </div>
    <div style="padding-top:1rem;border-top:1px solid rgba(13,51,71,.4);">
      <strong style="color:var(--text);font-size:.8rem;letter-spacing:1px;">4. Formato BOT (IP:PORTA:USER:PASS)</strong><br/>
      <div style="display:flex;gap:10px;margin-top:5px;align-items:center;">
        <input type="text" readonly value="${simpleFormat}" class="input-dark"
               style="margin:0;padding:.4rem;font-size:.8rem;background:#040c14;
                      border-color:var(--accent);color:var(--accent)"/>
        <button class="btn btn-primary btn-small"
                style="margin:0;white-space:nowrap;padding:.4rem 1rem;"
                onclick="navigator.clipboard.writeText('${simpleFormat}')
                         .then(() => alert('Copiado para a área de transferência!'))">
          COPIAR
        </button>
      </div>
    </div>
  `;
}

// ── Log SSE ───────────────────────────────────────────────────
function reconnectLogsStream(port) {
    if (localProxyEventSource) localProxyEventSource.close();
    const logEl = document.getElementById('localProxyLogs');
    logEl.innerHTML = `<div class="log-info">&gt; Logs da Porta ${port}...</div>`;

    localProxyEventSource = new EventSource(`/api/proxy/logs?port=${port}`);

    localProxyEventSource.onmessage = (ev) => {
        const data = JSON.parse(ev.data);
        if (data.event === 'stopped') {
            localProxyEventSource.close();
            return;
        }
        if (data.log) {
            const div = document.createElement('div');
            div.className = 'log-ok';
            div.textContent = `> ${data.log}`;
            logEl.appendChild(div);
            logEl.scrollTop = logEl.scrollHeight;
        }
    };

    localProxyEventSource.onerror = () => {
        console.warn('[proxy_manager] SSE de logs desconectou. Aguardando reconexão...');
    };
}

// ── Iniciar Proxy ─────────────────────────────────────────────
export async function startLocalProxy() {
    const type = document.getElementById('localProxyType').value;
    const port = parseInt(document.getElementById('localProxyPort').value, 10);
    const auth = document.getElementById('localProxyAuth').checked;
    const user = document.getElementById('localProxyUser').value.trim();
    const pass = document.getElementById('localProxyPass').value;

    const btn = document.getElementById('btnStartProxy');
    btn.classList.add('running');
    btn.disabled = true;

    try {
        const res = await fetch('/api/proxy/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ type, port, auth, user, pass }),
        });
        const data = await res.json();

        if (res.ok) {
            await loadProxies();
            selectProxy(port);
        } else {
            alert(`Falha ao iniciar: ${data.error}`);
        }
    } catch (err) {
        alert(`Erro de comunicação: ${err.message}`);
    } finally {
        btn.classList.remove('running');
        btn.disabled = false;
    }
}

// ── Parar Proxy ───────────────────────────────────────────────
export async function stopLocalProxy(port, ev) {
    ev.stopPropagation();
    try {
        await fetch('/api/proxy/stop', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ port }),
        });
        if (selectedProxyPort === port) selectProxy(null);
        await loadProxies();
    } catch (err) {
        console.error('[proxy_manager] stopLocalProxy:', err);
        alert(`Erro ao parar proxy: ${err.message}`);
    }
}

// ── Exportar Todas (formato BOT) ──────────────────────────────
export function exportAllProxies() {
    if (!proxiedInstances.length) {
        alert('Nenhuma proxy ativa para exportar.');
        return;
    }
    const lines = proxiedInstances.map(p =>
        p.auth_enabled
            ? `${p.ip}:${p.port}:${p.user}:${p.pass}`
            : `${p.ip}:${p.port}`
    );
    navigator.clipboard.writeText(lines.join('\n')).then(() => {
        alert(`${lines.length} proxie(s) copiada(s):\n\n${lines.join('\n')}`);
    }).catch(err => {
        console.error('[proxy_manager] exportAllProxies:', err);
        alert(`Erro ao copiar: ${err.message}`);
    });
}

// ── Inicialização ─────────────────────────────────────────────
export function init() {
    // Atualiza porta padrão ao trocar tipo
    document.getElementById('localProxyType').addEventListener('change', (e) => {
        document.getElementById('localProxyPort').value =
            e.target.value === 'socks5' ? 1080 : 8080;
    });

    // Polling de status a cada 2s
    proxyPollingInterval = setInterval(loadProxies, 2000);
    loadProxies(); // carrega imediatamente
}
