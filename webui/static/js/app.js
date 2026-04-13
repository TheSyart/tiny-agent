/* ==========================================================================
   app.js — WebSocket connection, chat rendering, shared utilities
   ========================================================================== */

const ws = new WebSocket(`ws://${location.host}/ws`);
const chatInner = document.getElementById('chat-inner');
const chatEl    = document.getElementById('chat');
const input     = document.getElementById('input');
const sendBtn   = document.getElementById('send');
const welcome   = document.getElementById('welcome');
const connDot   = document.getElementById('conn-dot');

let currentAssistant = null; // { msg, bubbleEl, textEl, textBuf, insertPoint }
let pendingConfirmId  = null;

// ============ Utilities ============
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
  }[c]));
}
function safeJson(v) {
  try { return JSON.stringify(v, null, 2); } catch { return String(v); }
}
function scrollToEnd() { chatEl.scrollTop = chatEl.scrollHeight; }

function showToast(msg, isErr = false) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.toggle('err', isErr);
  t.classList.add('show');
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.classList.remove('show'), 3200);
}
window.showToast = showToast;

// ============ Welcome ============
function hideWelcome() {
  if (!welcome || !welcome.parentNode) return;
  welcome.style.transition = 'opacity 220ms ease, transform 220ms ease';
  welcome.style.opacity = '0';
  welcome.style.transform = 'translateY(-8px)';
  setTimeout(() => welcome.remove(), 240);
}

// ============ Message rendering ============
function addUserMessage(text) {
  hideWelcome();
  const msg = document.createElement('div');
  msg.className = 'msg user';
  msg.innerHTML = `
    <div class="avatar user" aria-hidden="true">U</div>
    <div class="bubble">
      <div class="bubble-role">You</div>
      <div class="bubble-content"></div>
    </div>`;
  msg.querySelector('.bubble-content').textContent = text;
  chatInner.appendChild(msg);
  scrollToEnd();
}

function ensureAssistantBubble() {
  if (currentAssistant) return currentAssistant;
  // Any lingering step loader belongs to the previous turn; keep it until
  // we have real content — actually it sits outside the bubble, so it will
  // naturally be replaced by new output.
  const msg = document.createElement('div');
  msg.className = 'msg assistant';
  msg.innerHTML = `
    <div class="avatar assistant" aria-hidden="true">小T</div>
    <div class="bubble">
      <div class="bubble-role">小T</div>
      <div class="bubble-content"></div>
    </div>`;
  chatInner.appendChild(msg);
  const textEl = msg.querySelector('.bubble-content');
  currentAssistant = { msg, bubbleEl: msg.querySelector('.bubble'), textEl, textBuf: '', insertPoint: textEl };
  scrollToEnd();
  return currentAssistant;
}

// ============ Step loading indicator ============
let stepLoaderEl = null;
function showStepLoader(stepNum) {
  removeStepLoader();
  stepLoaderEl = document.createElement('div');
  stepLoaderEl.className = 'step-loader';
  stepLoaderEl.innerHTML = `<span class="spinner"></span><span>第 ${stepNum} 步进行中…</span>`;
  chatInner.appendChild(stepLoaderEl);
  scrollToEnd();
}
function removeStepLoader() {
  if (stepLoaderEl && stepLoaderEl.parentNode) {
    stepLoaderEl.remove();
  }
  stepLoaderEl = null;
}

function addTypingIndicator() {
  const a = ensureAssistantBubble();
  if (a.textEl.querySelector('.typing')) return;
  a.textEl.innerHTML = '<div class="typing" aria-label="Thinking"><span></span><span></span><span></span></div>';
}
function removeTyping() {
  if (!currentAssistant) return;
  const t = currentAssistant.textEl.querySelector('.typing');
  if (t) t.remove();
}

let thinkingBuf = '';
let thinkingStartTime = 0;

function addThinkingText(text) {
  const a = ensureAssistantBubble();
  removeTyping();
  thinkingBuf += text;
  let thinkingEl = a.bubbleEl.querySelector('.thinking-section');
  if (!thinkingEl) {
    thinkingStartTime = Date.now();
    thinkingEl = document.createElement('div');
    thinkingEl.className = 'thinking-section thinking-active';
    thinkingEl.innerHTML = `
      <div class="thinking-pill">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6l1.4 1.4M17 17l1.4 1.4M5.6 18.4l1.4-1.4M17 7l1.4-1.4"/>
          <circle cx="12" cy="12" r="4"/>
        </svg>
        <span class="thinking-label-text">思考中</span>
        <span class="thinking-dots"><span></span><span></span><span></span></span>
      </div>
      <div class="thinking-body-wrapper">
        <div class="thinking-body">
          <pre class="thinking-content"></pre>
        </div>
      </div>`;
    a.textEl.insertAdjacentElement('beforebegin', thinkingEl);
    a.insertPoint = thinkingEl;
  }
  thinkingEl.querySelector('.thinking-content').textContent = thinkingBuf;
  scrollToEnd();
}

function finalizeThinking() {
  if (!currentAssistant) return;
  const thinkingEl = currentAssistant.bubbleEl.querySelector('.thinking-section');
  if (!thinkingEl || !thinkingEl.classList.contains('thinking-active')) return;
  const elapsed = ((Date.now() - thinkingStartTime) / 1000).toFixed(1);

  thinkingEl.classList.remove('thinking-active');
  thinkingEl.classList.add('thinking-done', 'collapsed');

  // Replace pill content: remove dots, add elapsed + chevron, make clickable
  const pill = thinkingEl.querySelector('.thinking-pill');
  pill.innerHTML = `
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6l1.4 1.4M17 17l1.4 1.4M5.6 18.4l1.4-1.4M17 7l1.4-1.4"/>
      <circle cx="12" cy="12" r="4"/>
    </svg>
    <span class="thinking-label-text">已思考 ${elapsed}s</span>
    <svg class="thinking-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
      <polyline points="6 9 12 15 18 9"/>
    </svg>`;
  pill.addEventListener('click', () => {
    thinkingEl.classList.toggle('collapsed');
  });
}

function addAssistantText(text) {
  const a = ensureAssistantBubble();
  removeTyping();
  a.textBuf += text;
  try {
    const html = marked.parse(a.textBuf, { breaks: true, gfm: true });
    a.textEl.innerHTML = html;
    a.textEl.querySelectorAll('pre code').forEach(block => {
      try { hljs.highlightElement(block); } catch (_) {}
    });
  } catch (_) {
    a.textEl.innerHTML = escapeHtml(a.textBuf).replace(/\n/g, '<br>');
  }
  scrollToEnd();
}

function addStepDivider(n) {
  const div = document.createElement('div');
  div.className = 'step-divider';
  div.textContent = `第 ${n} 步`;
  chatInner.appendChild(div);
}

function addToolCall(id, name, args) {
  const a = ensureAssistantBubble();
  removeTyping();

  const nextTextEl = document.createElement('div');
  nextTextEl.className = 'bubble-content';

  const card = document.createElement('div');
  card.className = 'tool-card open running';
  card.dataset.toolId = id;
  card.innerHTML = `
    <button class="tool-card-head" type="button">
      <svg class="tool-card-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>
      </svg>
      <span class="tool-card-name"></span>
      <span class="tool-card-status"><span class="spin"></span><span>running</span></span>
      <svg class="chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>
    </button>
    <div class="tool-card-body"><pre class="args"></pre></div>`;
  card.querySelector('.tool-card-name').textContent = (name || 'tool') + '()';
  card.querySelector('.args').textContent = safeJson(args);
  card.querySelector('.tool-card-head').addEventListener('click', () => card.classList.toggle('open'));

  a.insertPoint.insertAdjacentElement('afterend', card);
  card.insertAdjacentElement('afterend', nextTextEl);
  a.textEl     = nextTextEl;
  a.textBuf    = '';
  a.insertPoint = card;

  scrollToEnd();
}

function addToolResult(id, content, isError) {
  let card = currentAssistant?.bubbleEl?.querySelector(`.tool-card[data-tool-id="${CSS.escape(id)}"]`);
  if (!card) card = chatInner.querySelector(`.tool-card[data-tool-id="${CSS.escape(id)}"]`);
  if (!card) return;

  card.classList.remove('running');
  const status = card.querySelector('.tool-card-status');
  status.innerHTML = `<span>${isError ? 'error' : 'done'}</span>`;
  status.classList.remove('ok', 'err');
  status.classList.add(isError ? 'err' : 'ok');

  const body = card.querySelector('.tool-card-body');
  const pre = document.createElement('pre');
  pre.className = 'result';
  const text = typeof content === 'string' ? content : safeJson(content);
  pre.textContent = text.length > 2000 ? text.slice(0, 2000) + '\n… (truncated)' : text;
  body.appendChild(pre);
  scrollToEnd();
}

function finalizeAssistant() {
  removeTyping();
  finalizeThinking();
  currentAssistant = null;
  thinkingBuf = '';
}

function showError(err) {
  removeTyping();
  const a = ensureAssistantBubble();
  const box = document.createElement('div');
  box.className = 'error-box';
  box.innerHTML = `
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
      <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
    </svg>
    <span></span>`;
  box.querySelector('span').textContent = String(err);
  a.textEl.innerHTML = '';
  a.textEl.appendChild(box);
  finalizeAssistant();
  scrollToEnd();
}

// ============ Connection ============
ws.onopen = () => {
  connDot.classList.remove('off');
  sendBtn.disabled = false;
  loadMeta();
  loadChatHistory();
};
ws.onclose = () => {
  connDot.classList.add('off');
  sendBtn.disabled = true;
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  switch (data.type) {
    case 'typing':     addTypingIndicator(); break;
    case 'thinking':   removeStepLoader(); addThinkingText(data.content); break;
    case 'text':       removeStepLoader(); addAssistantText(data.content); break;
    case 'step_start':
      if (data.n > 1) {
        addStepDivider(data.n);
        showStepLoader(data.n);
        // Break current bubble so next text/thinking starts a fresh assistant block
        currentAssistant = null;
        thinkingBuf = '';
      }
      break;
    case 'tool_call':
      removeStepLoader();
      addToolCall(data.id, data.tool, data.input); break;
    case 'tool_result':
      addToolResult(data.tool_use_id, data.content, data.is_error); break;
    case 'done':
      removeStepLoader();
      if (currentAssistant && !currentAssistant.textBuf && data.message) {
        currentAssistant.textEl.textContent = data.message;
      }
      finalizeAssistant();
      updateSendState();
      break;
    case 'confirmation_required':
      pendingConfirmId = data.id;
      document.getElementById('confirmTool').textContent = (data.tool || 'tool') + '()';
      document.getElementById('confirmInput').textContent = safeJson(data.input);
      document.getElementById('confirmModal').classList.add('active');
      break;
    case 'error':
      showError(data.message);
      updateSendState();
      break;
    case 'cleared':
      location.reload();
      break;
  }
};

// ============ Send ============
function sendMessage() {
  const text = input.value.trim();
  if (!text) return;
  thinkingBuf = '';
  addUserMessage(text);
  ws.send(JSON.stringify({ type: 'chat', content: text }));
  input.value = '';
  autosize();
  sendBtn.disabled = true;
}

function runPrompt(text) {
  input.value = text;
  autosize();
  updateSendState();
  sendMessage();
}

function clearChat() {
  ws.send(JSON.stringify({ type: 'clear' }));
}

// ============ Confirmation ============
function confirmTool(allowed) {
  document.getElementById('confirmModal').classList.remove('active');
  ws.send(JSON.stringify({ type: 'confirm', id: pendingConfirmId, allowed }));
  pendingConfirmId = null;
}
window.confirmTool = confirmTool;
window.clearChat   = clearChat;

document.getElementById('confirm-allow').addEventListener('click', () => confirmTool(true));
document.getElementById('confirm-deny').addEventListener('click', () => confirmTool(false));
document.getElementById('confirmModal').addEventListener('click', e => {
  if (e.target === document.getElementById('confirmModal')) confirmTool(false);
});
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    const confirmModal = document.getElementById('confirmModal');
    if (confirmModal && confirmModal.classList.contains('active')) confirmTool(false);
  }
});

// ============ Input helpers ============
function autosize() {
  input.style.height = 'auto';
  input.style.height = Math.min(input.scrollHeight, 180) + 'px';
}
function updateSendState() {
  sendBtn.disabled = input.value.trim().length === 0;
}
input.addEventListener('input', () => { autosize(); updateSendState(); });
input.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    if (!sendBtn.disabled) sendMessage();
  }
});
sendBtn.addEventListener('click', () => { if (!sendBtn.disabled) sendMessage(); });
document.querySelectorAll('.suggestion').forEach(btn => {
  btn.addEventListener('click', () => runPrompt(btn.dataset.prompt));
});
document.getElementById('clear-btn').addEventListener('click', clearChat);

// ============ Chat history (on reconnect) ============
function addHistoryThinking(thinking, bubbleEl, textEl) {
  const thinkingEl = document.createElement('div');
  thinkingEl.className = 'thinking-section thinking-done collapsed';
  thinkingEl.innerHTML = `
    <div class="thinking-pill">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
        <path d="M12 2a7 7 0 0 1 7 7c0 2.5-1.3 4.7-3.3 6l-.7.5V17a2 2 0 0 1-2 2h-2a2 2 0 0 1-2-2v-1.5l-.7-.5A7 7 0 0 1 12 2z"/>
        <path d="M9 21h6"/>
      </svg>
      <span class="thinking-label-text">已思考</span>
      <svg class="thinking-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="6 9 12 15 18 9"/>
      </svg>
    </div>
    <div class="thinking-body-wrapper">
      <div class="thinking-body">
        <pre class="thinking-content"></pre>
      </div>
    </div>`;
  thinkingEl.querySelector('.thinking-content').textContent = thinking;
  thinkingEl.querySelector('.thinking-pill').addEventListener('click', () => {
    thinkingEl.classList.toggle('collapsed');
  });
  textEl.insertAdjacentElement('beforebegin', thinkingEl);
}

async function loadChatHistory() {
  try {
    const data = await fetch('/api/memory/chat-history').then(r => r.json());
    const msgs = data.messages || [];
    if (!msgs.length) return;
    hideWelcome();
    for (const m of msgs) {
      if (m.role === 'user') {
        addUserMessage(m.text);
      } else if (m.role === 'assistant') {
        currentAssistant = null;
        thinkingBuf = '';
        // Ensure a fresh bubble so we can inject thinking before text
        const a = ensureAssistantBubble();
        if (m.thinking) {
          addHistoryThinking(m.thinking, a.bubbleEl, a.textEl);
        }
        if (m.text) {
          addAssistantText(m.text);
        }
        finalizeAssistant();
      }
    }
  } catch (e) {
    console.warn('loadChatHistory failed', e);
  }
}

// ============ Meta load ============
async function loadMeta() {
  try {
    const cfg = await fetch('/api/config').then(r => r.json());

    const model  = cfg?.llm?.model   || '—';
    const safety = cfg?.safety?.mode || '—';
    const modelPill  = document.getElementById('model-pill');
    const safetyPill = document.getElementById('safety-pill');
    if (modelPill)  modelPill.textContent = model;
    if (safetyPill) safetyPill.querySelector('span').textContent = safety;

    // Populate config form
    if (window._initConfigForm) window._initConfigForm(cfg);
  } catch (e) { console.error('loadMeta', e); }
}

window.addEventListener('load', () => { input.focus(); autosize(); });
