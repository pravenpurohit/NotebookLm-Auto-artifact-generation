/**
 * utils.js – Shared utility functions for the NotebookLM Dashboard.
 *
 * Provides common helpers used across multiple pages: escaping, formatting,
 * and API request wrappers.
 */

/* ---------- HTML / attribute escaping ---------- */

function escapeHtml(s) {
  var d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

function escapeAttr(s) {
  return s.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

/* ---------- Formatting ---------- */

function formatDate(iso) {
  if (!iso) return '—';
  var d = new Date(iso);
  return d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function formatSize(bytes) {
  if (bytes == null) return '—';
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

/* ---------- API helpers ---------- */

function apiPost(url) {
  return fetch(url, { method: 'POST' }).then(function (r) {
    if (!r.ok) return r.json().then(function (d) { throw new Error(d.detail || r.statusText); });
    return r.json();
  });
}

function apiDelete(url) {
  return fetch(url, { method: 'DELETE' }).then(function (r) {
    if (!r.ok) return r.json().then(function (d) { throw new Error(d.detail || r.statusText); });
    return r.json();
  });
}
