/* ==========================================================================
   nav.js — Left navigation, page switching, and per-page data loading
   ========================================================================== */

// ============ Page switching ============
function switchPage(pageId) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
  const page = document.getElementById('page-' + pageId);
  if (page) page.classList.add('active');
  const navItem = document.querySelector(`.nav-item[data-page="${pageId}"]`);
  if (navItem) navItem.classList.add('active');
  // Lazy-load page data
  onPageEnter(pageId);
}

document.querySelectorAll('.nav-item').forEach(item => {
  item.addEventListener('click', () => switchPage(item.dataset.page));
});

function onPageEnter(pageId) {
  if (pageId === 'model')   loadModelPage();
  if (pageId === 'tools')   loadToolsPage();
  if (pageId === 'mcp')     { if (window.loadMcpServers) window.loadMcpServers(); }
  if (pageId === 'skills')  { if (window.loadSkillsPage) window.loadSkillsPage(); }
  if (pageId === 'memory')  loadMemoryPage();
  if (pageId === 'stats')   loadStatsPage();
  if (pageId === 'prompt')  loadPromptPage();
}

// ============ Model page ============
function loadModelPage() {
  // Re-use config loaded in app.js loadMeta()
  // _initConfigForm is already called; just ensure it runs if not yet done
  fetch('/api/config').then(r => r.json()).then(cfg => {
    if (window._initConfigForm) window._initConfigForm(cfg);
    // Update read-only fields
    const llm = cfg.llm || {};
    const el = id => document.getElementById(id);
    if (el('cfg-model'))   el('cfg-model').textContent   = llm.model     || '—';
    if (el('cfg-base-url'))el('cfg-base-url').textContent = llm.base_url  || '(default)';
    if (el('cfg-api-key')) el('cfg-api-key').textContent  = llm.api_key   || '—';
  }).catch(() => {});
}

// ============ Tools page ============
async function loadToolsPage() {
  const container = document.getElementById('page-tools-list');
  if (!container) return;
  container.innerHTML = '<div class="mem-empty">加载中…</div>';
  try {
    const data = await fetch('/api/tools').then(r => r.json());
    const tools = data.tools || [];
    if (tools.length === 0) {
      container.innerHTML = '<div class="mem-empty">无可用工具</div>';
      return;
    }
    container.innerHTML = '';
    const list = document.createElement('div');
    list.className = 'tool-list-page';
    tools.forEach(t => {
      const item = document.createElement('div');
      item.className = 'tool-item-page';
      item.innerHTML = `
        <div class="tool-item-page-icon">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>
        </div>
        <div style="flex:1;min-width:0">
          <div class="tool-item-page-name">${escapeHtml(t.name)}()${t.is_dangerous ? '<span class="tool-badge">danger</span>' : ''}</div>
          <div class="tool-item-page-desc">${escapeHtml(t.description || '—')}</div>
        </div>`;
      list.appendChild(item);
    });
    container.appendChild(list);
  } catch (e) {
    container.innerHTML = `<div class="mem-empty">加载失败: ${escapeHtml(String(e))}</div>`;
  }
}

// ============ Prompt editor page ============
async function loadPromptPage() {
  const ta = document.getElementById('prompt-editor');
  if (!ta || ta._loaded) return;
  try {
    const data = await fetch('/api/config/prompt').then(r => r.json());
    ta.value = data.content || '';
    ta._loaded = true;
  } catch (e) {
    ta.value = '// 加载失败: ' + e.message;
  }
}

const promptSave = document.getElementById('prompt-save');
const promptReload = document.getElementById('prompt-reload');
const promptStatus = document.getElementById('prompt-status');

if (promptSave) {
  promptSave.addEventListener('click', async () => {
    const ta = document.getElementById('prompt-editor');
    if (!ta) return;
    promptSave.disabled = true;
    promptSave.textContent = '保存中…';
    try {
      await fetch('/api/config/prompt', {
        method: 'PATCH',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({content: ta.value}),
      });
      if (promptStatus) { promptStatus.textContent = '✓ 已保存并生效'; setTimeout(() => { promptStatus.textContent = ''; }, 3000); }
      showToast('人格设定已保存并热更新');
    } catch (e) {
      showToast('保存失败: ' + e.message, true);
    } finally {
      promptSave.disabled = false;
      promptSave.textContent = '保存并生效';
    }
  });
}

if (promptReload) {
  promptReload.addEventListener('click', async () => {
    const ta = document.getElementById('prompt-editor');
    if (!ta) return;
    ta._loaded = false;
    await loadPromptPage();
    if (promptStatus) { promptStatus.textContent = '↺ 已重新加载'; setTimeout(() => { promptStatus.textContent = ''; }, 2000); }
  });
}

// ============ Memory page ============
function loadMemoryPage() {
  loadMemoryPageShortTerm();
  loadMemoryPageArchive();
  loadMemoryPageImportant();
}

// Page-level memory tabs
document.querySelectorAll('.page-tab').forEach(btn => {
  btn.addEventListener('click', () => {
    const parent = btn.closest('.page-memory-body');
    if (!parent) return;
    parent.querySelectorAll('.page-tab').forEach(t => t.classList.remove('active'));
    parent.querySelectorAll('.page-tab-panel').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    const panel = document.getElementById('ptab-' + btn.dataset.ptab);
    if (panel) panel.classList.add('active');
    if (btn.dataset.ptab === 'mem-archive') loadMemoryPageArchive();
    if (btn.dataset.ptab === 'mem-important') loadMemoryPageImportant();
  });
});

async function loadMemoryPageShortTerm() {
  try {
    const data = await fetch('/api/memory/short-term').then(r => r.json());
    const {messages, count, max, trigger_threshold} = data;
    const el = id => document.getElementById(id);

    // Metrics
    if (el('pg-st-count')) el('pg-st-count').textContent = count;
    if (el('pg-st-max')) el('pg-st-max').textContent = max > 0 ? max : '∞';
    if (el('pg-st-trigger')) el('pg-st-trigger').textContent = trigger_threshold != null ? trigger_threshold : '—';
    const pct = max > 0 ? Math.min((count / max) * 100, 100) : 0;
    if (el('pg-st-pct')) el('pg-st-pct').textContent = pct.toFixed(0);

    // Bar fill + color state
    const bar = el('pg-st-bar');
    if (bar) {
      bar.style.width = pct + '%';
      bar.classList.remove('warn', 'danger');
      if (trigger_threshold != null && max > 0) {
        const trigPct = (trigger_threshold / max) * 100;
        if (pct >= trigPct) bar.classList.add('danger');
        else if (pct >= trigPct * 0.8) bar.classList.add('warn');
      }
    }
    const trigPct = (trigger_threshold != null && max > 0)
      ? Math.min((trigger_threshold / max) * 100, 100) : 60;
    if (el('pg-st-marker')) el('pg-st-marker').style.left = trigPct + '%';

    // Hint
    const hint = el('pg-st-hint');
    if (hint) {
      hint.classList.remove('active', 'warn');
      if (trigger_threshold != null) {
        const rem = trigger_threshold - count;
        if (rem > 0) {
          hint.textContent = `还差 ${rem} 条消息触发自动压缩`;
          hint.classList.add('active');
        } else {
          hint.textContent = '已达压缩阈值，下一轮对话将触发压缩';
          hint.classList.add('warn');
        }
      } else {
        hint.textContent = '自动压缩未启用';
      }
    }

    // List
    const list = el('pg-st-list');
    if (!list) return;
    list.innerHTML = '';
    if (!messages || messages.length === 0) {
      list.innerHTML = '<div class="mem-empty">暂无消息</div>';
      return;
    }
    const validRoles = ['user', 'assistant', 'summary', 'system'];
    messages.forEach((msg, i) => {
      const role = msg.role || 'system';
      const roleClass = validRoles.includes(role) ? role : 'system';
      const content = _extractText(msg);
      const len = content.length;
      const truncated = len > 220;
      const preview = truncated ? content.slice(0, 220) + '…' : content;

      // Detect summary messages (compressed history)
      const isSummary = roleClass === 'user' && /^\[历史会话摘要|^\[conversation summary/i.test(content);
      const displayRole = isSummary ? 'summary' : roleClass;

      const item = document.createElement('div');
      item.className = 'mem-item';
      item.dataset.role = displayRole;
      item.innerHTML = `
        <div class="mem-item-head">
          <span class="mem-item-role ${displayRole}">${escapeHtml(isSummary ? 'summary' : role)}</span>
          <span class="mem-item-idx">#${i+1}</span>
          <span class="mem-item-meta">
            <span>${len.toLocaleString()} 字</span>
            ${truncated ? '<span class="mem-item-toggle">展开 ▾</span>' : ''}
          </span>
        </div>
        <div class="mem-item-body ${truncated ? 'collapsed' : ''}">${escapeHtml(truncated ? preview : content)}</div>
      `;
      if (truncated) {
        const toggle = item.querySelector('.mem-item-toggle');
        const body = item.querySelector('.mem-item-body');
        toggle.addEventListener('click', () => {
          const expanded = body.classList.toggle('expanded');
          body.classList.toggle('collapsed', !expanded);
          if (expanded) {
            body.textContent = content;
            toggle.textContent = '收起 ▴';
          } else {
            body.textContent = preview;
            toggle.textContent = '展开 ▾';
          }
        });
      }
      list.appendChild(item);
    });
  } catch (e) { console.error('loadMemoryPageShortTerm', e); }
}

async function loadMemoryPageArchive() {
  const list = document.getElementById('pg-archive-list');
  if (!list) return;
  list.innerHTML = '<div class="mem-empty">加载中…</div>';
  try {
    const data = await fetch('/api/memory/archives?limit=40').then(r => r.json());
    const sessions = data.sessions || [];
    if (sessions.length === 0) {
      list.innerHTML = '<div class="mem-empty">暂无归档会话</div>';
      return;
    }
    list.innerHTML = '';
    sessions.forEach(s => list.appendChild(_buildArchiveCard(s)));
  } catch (e) {
    list.innerHTML = `<div class="mem-empty">加载失败: ${escapeHtml(String(e))}</div>`;
  }
}

async function loadMemoryPageImportant() {
  const el = document.getElementById('pg-important-content');
  if (!el) return;
  try {
    const data = await fetch('/api/memory/important').then(r => r.json());
    el.textContent = data.content || '（暂无重要记忆）';
  } catch (e) {
    el.textContent = '加载失败: ' + e.message;
  }
}

// Page memory action buttons
const pgCompress = document.getElementById('pg-btn-compress');
const pgArchive  = document.getElementById('pg-btn-archive');
const pgClearImp = document.getElementById('pg-btn-clear-important');

if (pgCompress) {
  pgCompress.addEventListener('click', async () => {
    pgCompress.disabled = true; pgCompress.textContent = '压缩中…';
    try {
      const res = await fetch('/api/memory/compress', {method:'POST'}).then(r => r.json());
      showToast(`压缩完成，折叠了 ${res.compressed_count} 条消息`);
      loadMemoryPageShortTerm();
    } catch (e) { showToast('压缩失败', true); }
    finally { pgCompress.disabled = false; pgCompress.textContent = '立即压缩'; }
  });
}
if (pgArchive) {
  pgArchive.addEventListener('click', async () => {
    pgArchive.disabled = true; pgArchive.textContent = '归档中…';
    try {
      const res = await fetch('/api/memory/archive', {method:'POST'}).then(r => r.json());
      showToast(`已归档会话 ${res.archived_session_id}`);
      loadMemoryPageShortTerm();
    } catch (e) { showToast('归档失败', true); }
    finally { pgArchive.disabled = false; pgArchive.textContent = '归档会话'; }
  });
}
if (pgClearImp) {
  pgClearImp.addEventListener('click', async () => {
    if (!confirm('确定清空所有重要记忆？')) return;
    try {
      await fetch('/api/memory/important', {method:'DELETE'});
      showToast('重要记忆已清空');
      loadMemoryPageImportant();
    } catch (e) { showToast('清空失败', true); }
  });
}

// Page search
const pgSearchInput = document.getElementById('pg-search-input');
const pgSearchBtn   = document.getElementById('pg-search-btn');
async function doPageSearch() {
  const q = pgSearchInput?.value.trim();
  if (!q) return;
  const list = document.getElementById('pg-archive-list');
  if (!list) return;
  list.innerHTML = '<div class="mem-empty">搜索中…</div>';
  try {
    const data = await fetch(`/api/memory/search?q=${encodeURIComponent(q)}&limit=12`).then(r => r.json());
    const results = data.results || [];
    if (results.length === 0) { list.innerHTML = '<div class="mem-empty">没有找到相关归档</div>'; return; }
    list.innerHTML = '';
    results.forEach(r => list.appendChild(_buildArchiveCard(r)));
  } catch (e) { list.innerHTML = `<div class="mem-empty">搜索失败: ${escapeHtml(String(e))}</div>`; }
}
if (pgSearchBtn) pgSearchBtn.addEventListener('click', doPageSearch);
if (pgSearchInput) pgSearchInput.addEventListener('keydown', e => { if (e.key === 'Enter') doPageSearch(); });

// ============ Stats page ============
async function loadStatsPage() {
  try {
    const data = await fetch('/api/metrics/usage?days=14').then(r => r.json());
    const s = data.summary || {};
    const fmt = n => n >= 1000000 ? (n/1000000).toFixed(1)+'M' : n >= 1000 ? (n/1000).toFixed(1)+'K' : String(n||0);

    const el = id => document.getElementById(id);
    if (el('stat-total-tokens')) el('stat-total-tokens').textContent = fmt(s.total_tokens);
    if (el('stat-cost'))         el('stat-cost').textContent        = s.total_cost_usd != null ? '$' + s.total_cost_usd.toFixed(4) : '—';
    if (el('stat-sessions'))     el('stat-sessions').textContent    = s.total_sessions || 0;
    if (el('stat-tools'))        el('stat-tools').textContent       = s.total_tool_calls || 0;

    // Bar chart
    const chart = el('stats-bar-chart');
    if (chart && data.by_day) {
      chart.innerHTML = '';
      const days = data.by_day;
      const maxVal = Math.max(...days.map(d => d.input + d.output), 1);
      days.forEach(d => {
        const total = (d.input || 0) + (d.output || 0);
        const heightPct = Math.max((total / maxVal) * 100, total > 0 ? 2 : 0);
        const bar = document.createElement('div');
        bar.className = 'chart-bar';
        bar.style.height = heightPct + '%';
        bar.title = `${d.date}: ${fmt(total)} tokens`;
        bar.innerHTML = `<div class="chart-bar-tooltip">${d.date.slice(5)}<br>${fmt(total)}</div>`;
        chart.appendChild(bar);
      });
    }

    // By model
    const modelList = el('stats-by-model');
    if (modelList && data.by_model) {
      modelList.innerHTML = '';
      const maxIn = Math.max(...data.by_model.map(m => m.input || 0), 1);
      data.by_model.forEach(m => {
        const row = document.createElement('div');
        row.className = 'stats-row';
        row.innerHTML = `
          <div style="flex:1;min-width:0">
            <div class="stats-row" style="margin-bottom:2px">
              <span class="stats-row-name">${escapeHtml(m.model)}</span>
              <span class="stats-row-val">${fmt((m.input||0)+(m.output||0))}</span>
            </div>
            <div class="stats-row-bar" style="width:${Math.round(((m.input||0)/maxIn)*100)}%"></div>
          </div>`;
        modelList.appendChild(row);
      });
    }

    // Top tools
    const toolList = el('stats-top-tools');
    if (toolList && data.top_tools) {
      toolList.innerHTML = '';
      const maxCount = Math.max(...data.top_tools.map(t => t.count||0), 1);
      data.top_tools.forEach(t => {
        const row = document.createElement('div');
        row.innerHTML = `
          <div class="stats-row" style="margin-bottom:2px">
            <span class="stats-row-name">${escapeHtml(t.name)}</span>
            <span class="stats-row-val">${t.count}</span>
          </div>
          <div class="stats-row-bar" style="width:${Math.round((t.count/maxCount)*100)}%"></div>`;
        toolList.appendChild(row);
      });
      if (data.top_tools.length === 0) toolList.innerHTML = '<div class="mem-empty">暂无工具调用记录</div>';
    }
  } catch (e) {
    console.error('loadStatsPage', e);
  }
}

// ============ Helpers ============
function _extractText(msg) {
  const content = msg.content;
  if (typeof content === 'string') return content;
  if (Array.isArray(content)) {
    return content.map(b => {
      if (typeof b === 'string') return b;
      if (b.type === 'text') return b.text || '';
      if (b.type === 'tool_use') return `[tool: ${b.name}]`;
      if (b.type === 'tool_result') {
        const c = b.content;
        if (typeof c === 'string') return c;
        if (Array.isArray(c)) return c.map(x => x.text || '').join(' ');
      }
      return '';
    }).join(' ').trim();
  }
  return String(content || '');
}

function _buildArchiveCard(session) {
  const card = document.createElement('div');
  card.className = 'mem-card';
  const date = (session.created_at || '').replace('T',' ').slice(0, 16);
  const tools = (session.tool_calls || []).slice(0, 5);
  const summary = session.summary || '(no summary)';
  const trunc = summary.length > 200 ? summary.slice(0,200)+'…' : summary;
  card.innerHTML = `
    <div class="mem-card-title">${escapeHtml(session.id || '?')}</div>
    <div class="mem-card-date">${escapeHtml(date)} · ${session.message_count || '?'} msgs</div>
    <div class="mem-card-summary">${escapeHtml(trunc)}</div>
    ${tools.length ? `<div class="mem-card-tools">${tools.map(t=>`<span class="mem-tool-chip">${escapeHtml(t)}</span>`).join('')}</div>` : ''}`;
  return card;
}
