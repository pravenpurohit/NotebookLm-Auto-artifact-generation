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

/* ---------- Confirmation modal ---------- */

/**
 * Show a custom confirmation modal (accessible, consistent UX).
 * Returns a Promise that resolves to true (confirm) or false (cancel).
 */
function showConfirmModal(title, message, confirmLabel, cancelLabel) {
  return new Promise(function (resolve) {
    var overlay = document.createElement('div');
    overlay.className = 'confirm-modal-overlay';
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-modal', 'true');
    overlay.setAttribute('aria-label', title);

    var modal = document.createElement('div');
    modal.className = 'confirm-modal';

    var h3 = document.createElement('h3');
    h3.textContent = title;
    modal.appendChild(h3);

    var p = document.createElement('p');
    p.textContent = message;
    modal.appendChild(p);

    var actions = document.createElement('div');
    actions.className = 'confirm-modal-actions';

    var cancelBtn = document.createElement('button');
    cancelBtn.className = 'btn';
    cancelBtn.type = 'button';
    cancelBtn.textContent = cancelLabel || 'Cancel';

    var confirmBtn = document.createElement('button');
    confirmBtn.className = 'btn btn-danger';
    confirmBtn.type = 'button';
    confirmBtn.textContent = confirmLabel || 'Confirm';

    actions.appendChild(cancelBtn);
    actions.appendChild(confirmBtn);
    modal.appendChild(actions);
    overlay.appendChild(modal);
    document.body.appendChild(overlay);

    confirmBtn.focus();

    function cleanup(result) {
      document.body.removeChild(overlay);
      resolve(result);
    }

    confirmBtn.addEventListener('click', function () { cleanup(true); });
    cancelBtn.addEventListener('click', function () { cleanup(false); });
    overlay.addEventListener('click', function (e) {
      if (e.target === overlay) cleanup(false);
    });
    overlay.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') cleanup(false);
    });
  });
}
