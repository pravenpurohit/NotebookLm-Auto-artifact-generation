/**
 * grid.js – Status Grid rendering, WebSocket live updates, and cell/batch controls.
 *
 * Reads initial data from window.__GRID_DATA__ (set by dashboard.html).
 * Connects to ws://{host}/ws/grid for real-time cell status updates.
 *
 * Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 8.1, 8.2, 8.3, 8.4,
 *               9.1, 9.2, 9.3, 9.4, 9.5, 12.2
 */
(function () {
  'use strict';

  // ── Status colours (Req 7.3) ──────────────────────────────────────
  var STATUS_COLORS = {
    not_started: '#e0e0e0',
    pending:     '#fff3cd',
    in_progress: '#cce5ff',
    completed:   '#d4edda',
    failed:      '#f8d7da',
    stopped:     '#e2e3e5'
  };

  var STATUS_LABELS = {
    not_started: 'Not Started',
    pending:     'Pending',
    in_progress: 'In Progress',
    completed:   'Completed',
    failed:      'Failed',
    stopped:     'Stopped'
  };

  // ── State ─────────────────────────────────────────────────────────
  var reports   = [];
  var templates = [];
  var cellMap   = {};  // key: "reportId::templateId" → cell object
  var ws        = null;
  var MOBILE_BP = 768;

  // ── Helpers ───────────────────────────────────────────────────────
  function cellKey(reportId, templateId) {
    return reportId + '::' + templateId;
  }

  function getCell(reportId, templateId) {
    return cellMap[cellKey(reportId, templateId)] || null;
  }

  function formatTime(iso) {
    if (!iso) return '—';
    var d = new Date(iso);
    return d.toLocaleString();
  }

  function elapsed(startedIso) {
    if (!startedIso) return '—';
    var ms = Date.now() - new Date(startedIso).getTime();
    if (ms < 0) ms = 0;
    var secs = Math.floor(ms / 1000);
    var mins = Math.floor(secs / 60);
    secs = secs % 60;
    var hrs = Math.floor(mins / 60);
    mins = mins % 60;
    if (hrs > 0) return hrs + 'h ' + mins + 'm ' + secs + 's';
    if (mins > 0) return mins + 'm ' + secs + 's';
    return secs + 's';
  }

  function truncate(str, len) {
    if (!str) return '';
    return str.length > len ? str.substring(0, len) + '…' : str;
  }


  // ── API helpers (use shared apiPost/apiDelete from utils.js) ─────

  function setBatchStatus(msg) {
    var el = document.getElementById('batch-status');
    if (el) {
      if (msg) {
        // S2 fix: use DOM API instead of innerHTML to prevent XSS
        el.textContent = '';
        var span = document.createElement('span');
        span.textContent = msg;
        el.appendChild(span);
        var dismissBtn = document.createElement('button');
        dismissBtn.className = 'btn-dismiss-status';
        dismissBtn.type = 'button';
        dismissBtn.setAttribute('aria-label', 'Dismiss status');
        dismissBtn.textContent = '\u00D7';
        dismissBtn.addEventListener('click', function () { el.textContent = ''; });
        el.appendChild(dismissBtn);
      } else {
        el.textContent = '';
      }
    }
    if (msg) setTimeout(function () { if (el && el.textContent) el.textContent = ''; }, 4000);
  }

  // ── Cell action handlers (Req 8.1, 8.2, 8.3) ────────────────────
  function startCell(reportId, templateId) {
    // Check for duplicate prompt before starting generation (Req 8.2, 8.3)
    fetch('/api/generate/' + reportId + '/' + templateId + '/check-duplicate')
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.duplicate) {
          showDuplicatePromptDialog(reportId, templateId, data.existing);
        } else {
          doStartCell(reportId, templateId);
        }
      })
      .catch(function () {
        // If check fails, proceed with generation anyway
        doStartCell(reportId, templateId);
      });
  }

  function doStartCell(reportId, templateId) {
    apiPost('/api/generate/' + reportId + '/' + templateId)
      .then(function () { setBatchStatus('Started'); })
      .catch(function (e) { setBatchStatus('Error: ' + e.message); });
  }

  /**
   * Show a custom confirmation modal (consistent with artifacts.js / file-browser.js).
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

      var cancelBtnEl = document.createElement('button');
      cancelBtnEl.className = 'btn';
      cancelBtnEl.type = 'button';
      cancelBtnEl.textContent = cancelLabel || 'Cancel';

      var confirmBtnEl = document.createElement('button');
      confirmBtnEl.className = 'btn btn-danger';
      confirmBtnEl.type = 'button';
      confirmBtnEl.textContent = confirmLabel || 'Confirm';

      actions.appendChild(cancelBtnEl);
      actions.appendChild(confirmBtnEl);
      modal.appendChild(actions);
      overlay.appendChild(modal);
      document.body.appendChild(overlay);

      confirmBtnEl.focus();

      function cleanup(result) {
        document.body.removeChild(overlay);
        resolve(result);
      }

      confirmBtnEl.addEventListener('click', function () { cleanup(true); });
      cancelBtnEl.addEventListener('click', function () { cleanup(false); });
      overlay.addEventListener('click', function (e) {
        if (e.target === overlay) cleanup(false);
      });
      overlay.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') cleanup(false);
      });
    });
  }

  function showDuplicatePromptDialog(reportId, templateId, existing) {
    var msg = 'A completed generation with the same prompt already exists';
    if (existing.artifact_path) {
      msg += ' (artifact: ' + existing.artifact_path.split('/').pop() + ')';
    }
    msg += '. Do you want to regenerate anyway?';

    showConfirmModal('Duplicate Prompt Detected', msg, 'Regenerate', 'Skip').then(function (confirmed) {
      if (confirmed) {
        doStartCell(reportId, templateId);
      } else {
        setBatchStatus('Skipped (duplicate prompt)');
      }
    });
  }

  function stopCell(reportId, templateId) {
    apiDelete('/api/generate/' + reportId + '/' + templateId)
      .then(function () { setBatchStatus('Stopped'); })
      .catch(function (e) { setBatchStatus('Error: ' + e.message); });
  }

  function retryCell(reportId, templateId) {
    apiPost('/api/generate/' + reportId + '/' + templateId + '/retry')
      .then(function () { setBatchStatus('Retrying'); })
      .catch(function (e) { setBatchStatus('Error: ' + e.message); });
  }

  // ── Cell control buttons based on status (Req 8.1, 8.2, 8.3) ────
  function cellControls(cell) {
    var html = '<span class="cell-controls">';
    var rid = cell.report_id;
    var tid = cell.template_id;

    switch (cell.status) {
      case 'not_started':
      case 'pending':
        html += '<button class="btn btn-xs btn-start" data-action="start" data-rid="' + rid + '" data-tid="' + tid + '" title="Start">&#9654;</button>';
        break;
      case 'in_progress':
        html += '<button class="btn btn-xs btn-stop" data-action="stop" data-rid="' + rid + '" data-tid="' + tid + '" title="Stop">&#9632;</button>';
        break;
      case 'completed':
        if (cell.artifact_path) {
          html += '<a class="btn btn-xs btn-download" href="/api/artifacts/' + rid + '/preview" target="_blank" title="View">&#128065;</a>';
        }
        break;
      case 'failed':
      case 'stopped':
        html += '<button class="btn btn-xs btn-retry" data-action="retry" data-rid="' + rid + '" data-tid="' + tid + '" title="Retry">&#8635;</button>';
        break;
    }
    html += '</span>';
    return html;
  }

  // ── Tooltip (Req 7.4) ────────────────────────────────────────────
  var tooltipEl = null;

  function showTooltip(cell, anchorEl) {
    if (!tooltipEl) tooltipEl = document.getElementById('cell-tooltip');
    if (!tooltipEl) return;

    document.getElementById('tip-task-id').textContent = cell.task_id || '—';
    document.getElementById('tip-started').textContent = formatTime(cell.started_at);
    document.getElementById('tip-elapsed').textContent = elapsed(cell.started_at);

    var errRow = tooltipEl.querySelector('.tooltip-error');
    if (cell.error_message) {
      document.getElementById('tip-error').textContent = cell.error_message;
      errRow.style.display = '';
    } else {
      errRow.style.display = 'none';
    }

    // Position near the anchor element
    var rect = anchorEl.getBoundingClientRect();
    tooltipEl.style.top = (rect.bottom + window.scrollY + 6) + 'px';
    tooltipEl.style.left = (rect.left + window.scrollX) + 'px';
    tooltipEl.setAttribute('aria-hidden', 'false');
    tooltipEl.classList.add('visible');
  }

  function hideTooltip() {
    if (!tooltipEl) tooltipEl = document.getElementById('cell-tooltip');
    if (!tooltipEl) return;
    tooltipEl.classList.remove('visible');
    tooltipEl.setAttribute('aria-hidden', 'true');
  }


  // ── Render: Desktop grid (Req 7.1, 12.2) ─────────────────────────
  function renderGrid() {
    var table = document.getElementById('status-grid');
    if (!table) return;

    var thead = table.querySelector('thead tr');
    var tbody = table.querySelector('tbody');

    // Clear existing content (keep corner header)
    while (thead.children.length > 1) thead.removeChild(thead.lastChild);
    tbody.innerHTML = '';

    // Column headers: templates (S1 fix: use textContent for user-supplied names)
    templates.forEach(function (tpl) {
      var th = document.createElement('th');
      th.scope = 'col';
      th.textContent = truncate(tpl.name, 20);
      th.title = tpl.name;
      thead.appendChild(th);
    });

    // Rows: reports
    reports.forEach(function (report) {
      var tr = document.createElement('tr');

      // Row header (S1 fix: use textContent for user-supplied names)
      var th = document.createElement('th');
      th.scope = 'row';
      th.textContent = truncate(report.notebook_name || report.filename, 25);
      th.title = report.filename;
      tr.appendChild(th);

      // Cells
      templates.forEach(function (tpl) {
        var td = document.createElement('td');
        var cell = getCell(report.id, tpl.id);
        var status = cell ? cell.status : 'not_started';

        td.className = 'grid-cell status-' + status;
        td.style.backgroundColor = STATUS_COLORS[status] || '#e0e0e0';
        td.setAttribute('data-rid', report.id);
        td.setAttribute('data-tid', tpl.id);
        td.setAttribute('role', 'gridcell');
        td.setAttribute('aria-label', (report.notebook_name || report.filename) + ' × ' + tpl.name + ': ' + STATUS_LABELS[status]);

        var inner = '<span class="cell-status-label">' + STATUS_LABELS[status] + '</span>';
        if (cell) inner += cellControls(cell);
        td.innerHTML = inner;

        tr.appendChild(td);
      });

      tbody.appendChild(tr);
    });
  }

  // ── Render: Mobile card layout (Req 12.2) ────────────────────────
  function renderCards() {
    var container = document.getElementById('card-list');
    if (!container) return;
    container.innerHTML = '';

    reports.forEach(function (report) {
      templates.forEach(function (tpl) {
        var cell = getCell(report.id, tpl.id);
        var status = cell ? cell.status : 'not_started';

        var card = document.createElement('div');
        card.className = 'status-card status-' + status;
        card.style.borderLeftColor = STATUS_COLORS[status] || '#e0e0e0';
        card.setAttribute('data-rid', report.id);
        card.setAttribute('data-tid', tpl.id);

        // S1 fix: escape user-supplied text in card innerHTML
        card.innerHTML =
          '<div class="card-header">' +
            '<strong class="card-report">' + escapeHtml(truncate(report.notebook_name || report.filename, 30)) + '</strong>' +
            '<span class="card-template">' + escapeHtml(truncate(tpl.name, 30)) + '</span>' +
          '</div>' +
          '<div class="card-body">' +
            '<span class="card-status" style="background:' + STATUS_COLORS[status] + '">' + STATUS_LABELS[status] + '</span>' +
            (cell ? cellControls(cell) : '') +
          '</div>';

        container.appendChild(card);
      });
    });
  }

  // ── Responsive switch ─────────────────────────────────────────────
  function render() {
    var isMobile = window.innerWidth < MOBILE_BP;
    var gridWrapper = document.getElementById('grid-wrapper');
    var cardList = document.getElementById('card-list');

    if (gridWrapper) gridWrapper.style.display = isMobile ? 'none' : '';
    if (cardList) cardList.style.display = isMobile ? '' : 'none';

    if (isMobile) {
      renderCards();
    } else {
      renderGrid();
    }
  }

  // ── Update a single cell in-place ─────────────────────────────────
  function updateSingleCell(updatedCell) {
    var key = cellKey(updatedCell.report_id, updatedCell.template_id);
    cellMap[key] = updatedCell;
    // Re-render for simplicity; could be optimised to patch DOM
    render();
  }


  // ── WebSocket connection indicator ──────────────────────────────
  function setWsIndicator(connected) {
    var el = document.getElementById('ws-indicator');
    if (!el) return;
    if (connected) {
      el.textContent = '';
      el.style.display = 'none';
    } else {
      el.textContent = 'Live updates disconnected. Reconnecting…';
      el.style.display = 'block';
    }
  }

  // ── WebSocket connection (Req 7.2) ────────────────────────────────
  var wsReconnectDelay = 1000;
  var wsMaxDelay = 30000;

  function connectWebSocket() {
    var protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    var url = protocol + '//' + window.location.host + '/ws/grid';

    ws = new WebSocket(url);

    ws.onopen = function () {
      wsReconnectDelay = 1000;
      setWsIndicator(true);
    };

    ws.onmessage = function (event) {
      try {
        var msg = JSON.parse(event.data);
        if (msg.type === 'cell_update' && msg.data) {
          updateSingleCell(msg.data);
        } else if (msg.type === 'batch_update' && Array.isArray(msg.data)) {
          msg.data.forEach(function (c) {
            cellMap[cellKey(c.report_id, c.template_id)] = c;
          });
          render();
        }
      } catch (e) {
        // Ignore non-JSON or ack messages
      }
    };

    ws.onclose = function () {
      setWsIndicator(false);
      // Auto-reconnect with exponential backoff
      setTimeout(function () {
        wsReconnectDelay = Math.min(wsReconnectDelay * 2, wsMaxDelay);
        connectWebSocket();
      }, wsReconnectDelay);
    };

    ws.onerror = function () {
      ws.close();
    };
  }

  // ── Batch controls (Req 9.1–9.5) ─────────────────────────────────
  function bindBatchControls() {
    var actions = {
      'btn-start-all':   { url: '/api/batch/start',        label: 'Starting all…' },
      'btn-pause':       { url: '/api/batch/pause',         label: 'Pausing…' },
      'btn-resume':      { url: '/api/batch/resume',        label: 'Resuming…' },
      'btn-stop-all':    { url: '/api/batch/stop',          label: 'Stopping all…', confirmMsg: 'Are you sure you want to stop all running tasks?' },
      'btn-retry-failed': { url: '/api/batch/retry-failed', label: 'Retrying failed…' }
    };

    Object.keys(actions).forEach(function (id) {
      var btn = document.getElementById(id);
      if (!btn) return;
      btn.addEventListener('click', function () {
        function doAction() {
          setBatchStatus(actions[id].label);
          apiPost(actions[id].url)
            .then(function (data) { setBatchStatus(data.status || 'Done'); })
            .catch(function (e) { setBatchStatus('Error: ' + e.message); });
        }

        if (actions[id].confirmMsg) {
          showConfirmModal('Confirm Action', actions[id].confirmMsg, 'Stop All', 'Cancel').then(function (confirmed) {
            if (confirmed) doAction();
          });
        } else {
          doAction();
        }
      });
    });
  }

  // ── Delegated event listeners ─────────────────────────────────────
  function bindCellActions() {
    document.addEventListener('click', function (e) {
      var btn = e.target.closest('[data-action]');
      if (!btn) return;

      var action = btn.getAttribute('data-action');
      var rid = btn.getAttribute('data-rid');
      var tid = btn.getAttribute('data-tid');

      if (action === 'start') startCell(rid, tid);
      else if (action === 'stop') stopCell(rid, tid);
      else if (action === 'retry') retryCell(rid, tid);
    });
  }

  function bindTooltips() {
    // Desktop: hover
    document.addEventListener('mouseover', function (e) {
      var cellEl = e.target.closest('.grid-cell, .status-card');
      if (!cellEl) return;
      var rid = cellEl.getAttribute('data-rid');
      var tid = cellEl.getAttribute('data-tid');
      var cell = getCell(rid, tid);
      if (cell) showTooltip(cell, cellEl);
    });

    document.addEventListener('mouseout', function (e) {
      var cellEl = e.target.closest('.grid-cell, .status-card');
      if (cellEl) hideTooltip();
    });

    // Finding 8.6: Keyboard users — focusin/focusout for tooltip access
    document.addEventListener('focusin', function (e) {
      var cellEl = e.target.closest('.grid-cell, .status-card');
      if (!cellEl) return;
      var rid = cellEl.getAttribute('data-rid');
      var tid = cellEl.getAttribute('data-tid');
      var cell = getCell(rid, tid);
      if (cell) showTooltip(cell, cellEl);
    });

    document.addEventListener('focusout', function (e) {
      var cellEl = e.target.closest('.grid-cell, .status-card');
      if (cellEl) hideTooltip();
    });

    // Mobile: tap (toggle)
    document.addEventListener('touchstart', function (e) {
      var cellEl = e.target.closest('.grid-cell, .status-card');
      if (!cellEl) { hideTooltip(); return; }
      // Don't show tooltip if tapping a button
      if (e.target.closest('[data-action], a')) return;
      var rid = cellEl.getAttribute('data-rid');
      var tid = cellEl.getAttribute('data-tid');
      var cell = getCell(rid, tid);
      if (cell) showTooltip(cell, cellEl);
    }, { passive: true });
  }

  // ── Initialise ────────────────────────────────────────────────────
  function init() {
    var data = window.__GRID_DATA__;
    if (!data) return; // Not on dashboard page

    reports = data.reports || [];
    templates = data.templates || [];

    // Build cell map
    (data.cells || []).forEach(function (c) {
      cellMap[cellKey(c.report_id, c.template_id)] = c;
    });

    render();
    bindBatchControls();
    bindCellActions();
    bindTooltips();
    connectWebSocket();

    // Re-render on resize for responsive switch
    var resizeTimer;
    window.addEventListener('resize', function () {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(render, 150);
    });
  }

  // Run on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
