/* ==========================================================================
   config.js — Model config page: read-only display + hot-patch patchable fields
   The config modal has been replaced by the inline model page (page-model).
   ========================================================================== */

// ============ Init form ============
function _initConfigForm(cfg) {
  const llm   = cfg.llm   || {};
  const agent = cfg.agent || {};
  const safety = cfg.safety || {};

  // Read-only
  const setTxt = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
  setTxt('cfg-base-url', llm.base_url || '(default)');
  setTxt('cfg-model',    llm.model    || '—');
  setTxt('cfg-api-key',  llm.api_key  || '—');

  // Patchable
  const setVal = (id, val) => { const el = document.getElementById(id); if (el) el.value = val; };
  setVal('cfg-temperature', llm.temperature ?? 1.0);
  setVal('cfg-max-tokens',  llm.max_tokens  ?? 4096);
  setVal('cfg-max-loops',   agent.max_loops ?? 50);
  const verboseEl = document.getElementById('cfg-verbose');
  if (verboseEl) verboseEl.value = (agent.verbose === true || agent.verbose === 'true') ? 'true' : 'false';
  const safetyEl = document.getElementById('cfg-safety-mode');
  if (safetyEl) safetyEl.value = safety.mode || 'confirm';
}

// Expose for app.js and nav.js
window._initConfigForm = _initConfigForm;

// ============ Save / patch ============
const configSaveBtn = document.getElementById('config-save');
if (configSaveBtn) {
  configSaveBtn.addEventListener('click', async () => {
    const get = id => document.getElementById(id);
    const patch = {
      'llm.temperature': parseFloat(get('cfg-temperature')?.value),
      'llm.max_tokens':  parseInt(get('cfg-max-tokens')?.value, 10),
      'agent.max_loops': parseInt(get('cfg-max-loops')?.value, 10),
      'agent.verbose':   get('cfg-verbose')?.value === 'true',
      'safety.mode':     get('cfg-safety-mode')?.value,
    };

    // Validate
    for (const [k, v] of Object.entries(patch)) {
      if (v !== v) { showToast(`Invalid value for ${k}`, true); return; } // NaN check
    }

    configSaveBtn.disabled = true;
    configSaveBtn.textContent = 'Applying…';
    try {
      const res = await fetch('/api/config', {
        method: 'PATCH',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(patch),
      }).then(r => r.json());
      const keys = Object.keys(res.applied || {}).join(', ');
      showToast(`Applied: ${keys || 'no changes'} (不写回 yaml)`);
    } catch (e) {
      showToast('Failed to apply: ' + (e.message || e), true);
    } finally {
      configSaveBtn.disabled = false;
      configSaveBtn.textContent = 'Apply';
    }
  });
}
