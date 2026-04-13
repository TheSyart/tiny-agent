/* ==========================================================================
   memory.js — Stub: memory management has moved to the Memory page (nav.js)
   This file is kept for backwards compatibility.
   ========================================================================== */

// The memory drawer has been replaced by the dedicated Memory page in the left nav.
// All memory management logic is now in nav.js → loadMemoryPage(), loadMemoryPageShortTerm(), etc.
// This file is intentionally minimal.

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

function truncate(s, n) { return s.length > n ? s.slice(0, n) + '…' : s; }
