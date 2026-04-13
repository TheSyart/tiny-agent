/* ==========================================================================
   mcp-skills.js — MCP server management + Skills page
   ========================================================================== */

// ============ MCP page ============

async function loadMcpServers() {
  const container = document.getElementById('mcp-server-list');
  if (!container) return;
  container.innerHTML = '<div class="mem-empty">加载中…</div>';
  try {
    const data = await fetch('/api/mcp/servers').then(r => r.json());
    const servers = data.servers || [];
    if (servers.length === 0) {
      container.innerHTML = '<div class="mem-empty">暂无配置的 MCP 服务器。点击右上角"+ 添加"来添加。</div>';
      return;
    }
    container.innerHTML = '';
    servers.forEach(s => container.appendChild(_buildMcpRow(s)));
  } catch (e) {
    container.innerHTML = `<div class="mem-empty">加载失败: ${escapeHtml(String(e))}</div>`;
  }
}

function _buildMcpRow(s) {
  const row = document.createElement('div');
  row.className = 'mcp-server-row';
  row.dataset.name = s.name;
  const argsStr = (s.args || []).join(' ');
  row.innerHTML = `
    <div class="mcp-server-status">
      <span class="status-dot ${s.connected ? '' : 'off'}" title="${s.connected ? '已连接' : '未连接'}"></span>
    </div>
    <div class="mcp-server-info">
      <div class="mcp-server-name">${escapeHtml(s.name)}</div>
      <div class="mcp-server-cmd">${escapeHtml(s.command)}${argsStr ? ' ' + escapeHtml(argsStr) : ''}</div>
      ${s.connected ? `<div class="mcp-server-tools">${s.tool_count} 个工具</div>` : '<div class="mcp-server-tools" style="color:var(--text-dim)">未连接</div>'}
    </div>
    <div class="mcp-server-actions">
      <button class="btn-ghost mcp-reload-btn" type="button" title="重连">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 2v6h-6"/><path d="M21 13a9 9 0 1 1-3-7.7L21 8"/></svg>
      </button>
      <button class="btn-ghost btn-danger mcp-delete-btn" type="button" title="删除">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
      </button>
    </div>`;

  row.querySelector('.mcp-reload-btn').addEventListener('click', () => reloadMcpServer(s.name));
  row.querySelector('.mcp-delete-btn').addEventListener('click', () => removeMcpServer(s.name));
  return row;
}

async function reloadMcpServer(name) {
  try {
    const r = await fetch(`/api/mcp/servers/${encodeURIComponent(name)}/reload`, { method: 'POST' });
    const d = await r.json();
    showToast(d.ok ? `${name} 已重连` : `${name} 重连失败`, !d.ok);
    loadMcpServers();
  } catch (e) {
    showToast('重连失败: ' + e.message, true);
  }
}

async function removeMcpServer(name) {
  if (!confirm(`确定删除 MCP 服务器 "${name}"？此操作同步更新 config.yaml。`)) return;
  try {
    await fetch(`/api/mcp/servers/${encodeURIComponent(name)}`, { method: 'DELETE' });
    showToast(`${name} 已删除`);
    loadMcpServers();
  } catch (e) {
    showToast('删除失败: ' + e.message, true);
  }
}

// Add form toggle
const mcpAddToggle = document.getElementById('mcp-add-toggle');
const mcpAddFormCard = document.getElementById('mcp-add-form-card');
const mcpFormCancel = document.getElementById('mcp-form-cancel');

if (mcpAddToggle) {
  mcpAddToggle.addEventListener('click', () => {
    if (!mcpAddFormCard) return;
    const visible = mcpAddFormCard.style.display !== 'none';
    mcpAddFormCard.style.display = visible ? 'none' : '';
    mcpAddToggle.textContent = visible ? '+ 添加' : '✕ 取消';
  });
}
if (mcpFormCancel) {
  mcpFormCancel.addEventListener('click', () => {
    if (mcpAddFormCard) mcpAddFormCard.style.display = 'none';
    if (mcpAddToggle) mcpAddToggle.textContent = '+ 添加';
  });
}

const mcpFormSubmit = document.getElementById('mcp-form-submit');
if (mcpFormSubmit) {
  mcpFormSubmit.addEventListener('click', async () => {
    const name = document.getElementById('mcp-form-name')?.value.trim();
    const command = document.getElementById('mcp-form-command')?.value.trim();
    const argsRaw = document.getElementById('mcp-form-args')?.value.trim();
    const envRaw = document.getElementById('mcp-form-env')?.value.trim();
    const status = document.getElementById('mcp-form-status');

    if (!name || !command) {
      if (status) { status.textContent = '名称和命令不能为空'; status.style.color = 'var(--c-err)'; }
      return;
    }

    const args = argsRaw ? argsRaw.split(',').map(s => s.trim()).filter(Boolean) : [];
    const env = {};
    if (envRaw) {
      envRaw.split('\n').forEach(line => {
        const eq = line.indexOf('=');
        if (eq > 0) env[line.slice(0, eq).trim()] = line.slice(eq + 1).trim();
      });
    }

    mcpFormSubmit.disabled = true;
    if (status) { status.textContent = '添加中…'; status.style.color = 'var(--text-mute)'; }

    try {
      const r = await fetch('/api/mcp/servers', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, command, args, env }),
      });
      const d = await r.json();
      showToast(d.connected ? `${name} 已添加并连接` : `${name} 已添加（未连接，需重启生效）`);
      // Reset form
      ['mcp-form-name', 'mcp-form-command', 'mcp-form-args', 'mcp-form-env'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.value = '';
      });
      if (mcpAddFormCard) mcpAddFormCard.style.display = 'none';
      if (mcpAddToggle) mcpAddToggle.textContent = '+ 添加';
      loadMcpServers();
    } catch (e) {
      showToast('添加失败: ' + e.message, true);
      if (status) { status.textContent = '失败: ' + e.message; status.style.color = 'var(--c-err)'; }
    } finally {
      mcpFormSubmit.disabled = false;
      if (status) setTimeout(() => { status.textContent = ''; }, 4000);
    }
  });
}

window.loadMcpServers = loadMcpServers;

// ============ Skills page ============

async function loadSkillsPage() {
  try {
    const data = await fetch('/api/skills').then(r => r.json());

    // Config info
    const autoEl = document.getElementById('skills-auto-discover');
    const dirsEl = document.getElementById('skills-directories');
    if (autoEl) autoEl.textContent = data.auto_discover ? 'true' : 'false';
    if (dirsEl) dirsEl.textContent = (data.directories || []).join(', ') || '—';

    const container = document.getElementById('skills-list-container');
    const emptyEl = document.getElementById('skills-empty');
    if (!container) return;

    const skills = data.skills || [];
    if (skills.length === 0) {
      if (emptyEl) emptyEl.textContent = '暂未加载任何技能。请在 config.yaml 的 skills.directories 中配置技能目录。';
      return;
    }
    if (emptyEl) emptyEl.remove();

    container.innerHTML = '';
    skills.forEach(skill => container.appendChild(_buildSkillCard(skill)));
  } catch (e) {
    const emptyEl = document.getElementById('skills-empty');
    if (emptyEl) emptyEl.textContent = '加载失败: ' + e.message;
  }
}

function _buildSkillCard(skill) {
  const card = document.createElement('div');
  card.className = 'info-card';
  const tags = (skill.tags || []).map(t => `<span class="mem-tool-chip">${escapeHtml(t)}</span>`).join('');
  const tools = (skill.tools || []).map(t => `<span class="mem-tool-chip" style="background:rgba(94,234,212,0.12);color:var(--c-teal)">${escapeHtml(t)}</span>`).join('');
  card.innerHTML = `
    <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:12px">
      <div style="flex:1;min-width:0">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
          <span style="font-weight:700;color:var(--text-0);font-size:14px">${escapeHtml(skill.name)}</span>
          <span style="font-size:11px;color:var(--text-dim);font-family:monospace">v${escapeHtml(skill.version || '1.0.0')}</span>
          ${skill.author ? `<span style="font-size:11px;color:var(--text-dim)">by ${escapeHtml(skill.author)}</span>` : ''}
        </div>
        ${skill.description ? `<div style="font-size:13px;color:var(--text-mute);margin-bottom:8px;line-height:1.5">${escapeHtml(skill.description)}</div>` : ''}
        ${tags ? `<div style="margin-bottom:6px">${tags}</div>` : ''}
        ${tools ? `<div style="font-size:12px;color:var(--text-dim);margin-bottom:4px">工具：</div><div style="display:flex;flex-wrap:wrap;gap:4px">${tools}</div>` : '<div style="font-size:12px;color:var(--text-dim)">无贡献工具</div>'}
      </div>
    </div>`;
  return card;
}

window.loadSkillsPage = loadSkillsPage;

// ============ Skill creator ============

const _SKILL_TEMPLATE = `from skills.base import Skill, SkillInfo
from tools.base import tool


class MySkill(Skill):
    @property
    def info(self) -> SkillInfo:
        return SkillInfo(
            name="my_skill",
            description="描述这个技能的功能",
            version="1.0.0",
            author="",
            tags=["custom"],
        )

    async def execute(self, context):
        pass

    def get_tools(self):
        return [my_tool]


@tool
async def my_tool(query: str) -> str:
    """工具描述。
    Args:
        query: 输入参数
    """
    return f"结果: {query}"
`;

const skillCreateToggle = document.getElementById('skill-create-toggle');
const skillCreateCard   = document.getElementById('skill-create-card');
const skillCreateCancel = document.getElementById('skill-create-cancel');
const skillCreateCode   = document.getElementById('skill-create-code');
const skillCreateName   = document.getElementById('skill-create-name');

const _KNOWLEDGE_TEMPLATE = `## 触发词
用户说以下内容时加载本技能：
- 关键词1
- 关键词2

## 工作流程

1. 步骤一：...
2. 步骤二：...
3. 步骤三：返回结果

## 示例

用户：示例输入
\`\`\`bash
# 示例命令或代码
\`\`\`

## 注意事项

- 注意点1
- 注意点2
`;

if (skillCreateCode && !skillCreateCode.value) {
  skillCreateCode.value = _SKILL_TEMPLATE;
}

// Type radio toggle logic
function _getSkillType() {
  return document.querySelector('input[name="skill-create-type"]:checked')?.value || 'python';
}

document.querySelectorAll('input[name="skill-create-type"]').forEach(radio => {
  radio.addEventListener('change', () => {
    const isPython = _getSkillType() === 'python';
    const codePanel = document.getElementById('skill-code-panel');
    const knowledgePanel = document.getElementById('skill-knowledge-panel');
    const descRow = document.getElementById('skill-desc-row');
    if (codePanel) codePanel.style.display = isPython ? '' : 'none';
    if (knowledgePanel) knowledgePanel.style.display = isPython ? 'none' : '';
    if (descRow) descRow.style.display = isPython ? 'none' : '';
    // Pre-fill templates on first switch
    if (!isPython) {
      const contentEl = document.getElementById('skill-create-content');
      if (contentEl && !contentEl._edited) contentEl.value = _KNOWLEDGE_TEMPLATE;
    } else {
      if (skillCreateCode && !skillCreateCode._edited) skillCreateCode.value = _SKILL_TEMPLATE;
    }
  });
});

if (skillCreateToggle) {
  skillCreateToggle.addEventListener('click', () => {
    if (!skillCreateCard) return;
    const visible = skillCreateCard.style.display !== 'none';
    skillCreateCard.style.display = visible ? 'none' : '';
    skillCreateToggle.textContent = visible ? '+ 新建技能' : '✕ 取消';
    if (!visible && skillCreateCode && !skillCreateCode._edited) {
      skillCreateCode.value = _SKILL_TEMPLATE;
    }
  });
}
if (skillCreateCancel) {
  skillCreateCancel.addEventListener('click', () => {
    if (skillCreateCard) skillCreateCard.style.display = 'none';
    if (skillCreateToggle) skillCreateToggle.textContent = '+ 新建技能';
  });
}
if (skillCreateCode) {
  skillCreateCode.addEventListener('input', () => { skillCreateCode._edited = true; });
}
const contentEl2 = document.getElementById('skill-create-content');
if (contentEl2) contentEl2.addEventListener('input', () => { contentEl2._edited = true; });

// Sync name → class name in code (Python mode only)
if (skillCreateName) {
  skillCreateName.addEventListener('input', () => {
    const raw = skillCreateName.value.trim();
    if (!raw || _getSkillType() !== 'python' || !skillCreateCode) return;
    const cls = raw.replace(/(^|_)([a-z])/g, (_, _p, c) => c.toUpperCase());
    skillCreateCode.value = skillCreateCode.value
      .replace(/^class \w+\(Skill\)/m, `class ${cls}(Skill)`)
      .replace(/name="[^"]*"/, `name="${raw}"`);
    skillCreateCode._edited = true;
  });
}

const skillCreateSubmit = document.getElementById('skill-create-submit');
if (skillCreateSubmit) {
  skillCreateSubmit.addEventListener('click', async () => {
    const name    = skillCreateName?.value.trim();
    const type    = _getSkillType();
    const status  = document.getElementById('skill-create-status');

    let body;
    if (type === 'knowledge') {
      const desc    = document.getElementById('skill-create-desc')?.value.trim() || '';
      const content = document.getElementById('skill-create-content')?.value.trim();
      if (!name || !content) {
        if (status) { status.textContent = '名称和内容不能为空'; status.style.color = 'var(--c-err)'; }
        return;
      }
      body = { name, description: desc, content, type: 'knowledge' };
    } else {
      const code = skillCreateCode?.value.trim();
      if (!name || !code) {
        if (status) { status.textContent = '名称和代码不能为空'; status.style.color = 'var(--c-err)'; }
        return;
      }
      body = { name, code, type: 'python' };
    }

    skillCreateSubmit.disabled = true;
    if (status) { status.textContent = '保存中…'; status.style.color = 'var(--text-mute)'; }

    try {
      const r = await fetch('/api/skills', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const d = await r.json();
      if (!d.ok) throw new Error(d.detail || '未知错误');

      if (type === 'knowledge') {
        showToast(`知识技能 "${name}" 已保存${d.loaded ? '并热加载' : '，重启后生效'}`);
      } else if (d.loaded) {
        showToast(`技能 "${d.skill?.name || name}" 已保存并热加载`);
      } else {
        showToast(`技能代码已保存到 ${d.path}，热加载失败: ${d.error || ''}，重启后生效`, true);
      }

      if (skillCreateCard) skillCreateCard.style.display = 'none';
      if (skillCreateToggle) skillCreateToggle.textContent = '+ 新建技能';
      if (skillCreateName) skillCreateName.value = '';
      if (skillCreateCode) { skillCreateCode.value = _SKILL_TEMPLATE; skillCreateCode._edited = false; }
      const ce = document.getElementById('skill-create-content');
      if (ce) { ce.value = _KNOWLEDGE_TEMPLATE; ce._edited = false; }
      loadSkillsPage();
    } catch (e) {
      showToast('保存失败: ' + e.message, true);
      if (status) { status.textContent = '失败: ' + e.message; status.style.color = 'var(--c-err)'; }
    } finally {
      skillCreateSubmit.disabled = false;
      if (status) setTimeout(() => { status.textContent = ''; }, 5000);
    }
  });
}
