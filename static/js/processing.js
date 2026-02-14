/**
 * processing.js – Processing matrix page for the NotebookLM Dashboard.
 *
 * Fetches grid state from /api/grid, renders a report×template matrix with
 * color-coded status cells, per-cell actions, batch controls, WebSocket
 * live updates, progress summary, sticky row headers, cell detail popovers,
 * and offline download tracking.
 *
 * Requirements: 5.1–5.6, 6.1–6.5, 10.1–10.5
 */
(function () {
  'use strict';

  /* ---------- constants ---------- */
  var STATUS_COLORS = {
    not_started: '#e0e0e0', pending: '#fff3cd', in_progress: '#cce5ff',
    completed: '#d4edda', failed: '#f8d7da', stopped: '#e2e3e5'
  };
  var STATUS_LABELS = {
    not_started: 'Not Started', pending: 'Pending', in_progress: 'In Progress',
    completed: 'Completed', failed: 'Failed', stopped: 'Stopped'
  };
  var MOBILE_BP = 768;

  /* ---------- DOM refs ---------- */
  var gridWrapper = document.getElementById('proc-grid-wrapper');
  var gridTable = document.getElementById('proc-grid');
  var cardList = document.getElementById('proc-card-list');
  var emptyMsg = document.getElementById('proc-empty-msg');
  var progressText = document.getElementById('proc-progress-text');
  var progressBar = document.getElementById('proc-progress-bar');
  var batchStatus = document.getElementById('proc-batch-status');
  var wsIndicator = document.getElementById('proc-ws-indicator');
  var tooltipEl = document.getElementById('proc-tooltip');
  var announcements = document.getElementById('proc-announcements');

  /* ---------- state ---------- */
  var reports = [];
  var templates = []; /* only non-excluded */
  var cellMap = {};
  var ws = null;
  var wsReconnectDelay = 1000;
  var _batchTimer = null;

  /* ---------- helpers ---------- */
  function cellKey(rid, tid) { return rid + '::' + tid; }
  function getCell(rid, tid) { return cellMap[cellKey(rid, tid)] || null; }

  function announce(msg) { if (announcements) announcements.textContent = msg; }

  function truncate(s, n) { return !s ? '' : s.length > n ? s.substring(0, n) + '…' : s; }

  function formatTime(iso) {
    if (!iso) return '—';
    var d = new Date(iso);
    return d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }

  function elapsed(iso) {
    if (!iso) return '—';
    var ms = Math.max(0, Date.now() - new Date(iso).getTime());
    var s = Math.floor(ms / 1000), m = Math.floor(s / 60); s %= 60;
    var h = Math.floor(m / 60); m %= 60;
    if (h) return h + 'h ' + m + 'm';
    if (m) return m + 'm ' + s + 's';
    return s + 's';
  }

  function setBatchStatus(msg) {
    if (!batchStatus) return;
    batchStatus.textContent = msg || '';
    clearTimeout(_batchTimer);
    if (msg) _batchTimer = setTimeout(function () { batchStatus.textContent = ''; }, 4000);
  }

  /* ---------- offline markers (localStorage) ---------- */
  function getOfflineIds() {
    try { return JSON.parse(localStorage.getItem('offline_artifacts') || '[]'); } catch (e) { return []; }
  }
  function markOffline(id) {
    var ids = getOfflineIds();
    if (ids.indexOf(id) < 0) { ids.push(id); localStorage.setItem('offline_artifacts', JSON.stringify(ids)); }
  }
  function isOffline(id) { return getOfflineIds().indexOf(id) >= 0; }

  /* ---------- progress summary ---------- */
  function updateProgress() {
    var total = 0, completed = 0, inProgress = 0, failed = 0;
    reports.forEach(function (r) {
      templates.forEach(function (t) {
        total++;
        var c = getCell(r.id, t.id);
        if (!c) return;
        if (c.status === 'completed') completed++;
        else if (c.status === 'in_progress') inProgress++;
        else if (c.status === 'failed') failed++;
      });
    });
    var pct = total ? Math.round((completed / total) * 100) : 0;
    progressText.textContent = completed + '/' + total + ' complete' +
      (inProgress ? ', ' + inProgress + ' in progress' : '') +
      (failed ? ', ' + failed + ' failed' : '');
    progressBar.style.width = pct + '%';
  }

  /* ---------- cell controls ---------- */
  function cellControls(cell) {
    var rid = cell.report_id, tid = cell.template_id;
    var html = '<span class="cell-controls">';
    switch (cell.status) {
      case 'not_started': case 'pending':
        html += '<button class="btn btn-xs btn-start" data-action="start" data-rid="' + rid + '" data-tid="' + tid + '" title="Start">&#9654;</button>';
        break;
      case 'in_progress':
        html += '<button class="btn btn-xs btn-stop" data-action="stop" data-rid="' + rid + '" data-tid="' + tid + '" title="Stop">&#9632;</button>';
        break;
      case 'completed':
        if (cell.artifact_path) {
          html += '<a class="btn btn-xs btn-download" href="/api/artifacts/' + rid + '/preview" target="_blank" title="Preview">&#128065;</a>';
          html += '<button class="btn btn-xs btn-download" data-action="download" data-rid="' + rid + '" data-tid="' + tid + '" title="Download">⬇</button>';
          if (isOffline(cell.task_id || rid + '_' + tid)) html += '<span class="badge badge-info" title="Downloaded">💾</span>';
        }
        break;
      case 'failed': case 'stopped':
        html += '<button class="btn btn-xs btn-retry" data-action="retry" data-rid="' + rid + '" data-tid="' + tid + '" title="Retry">&#8635;</button>';
        break;
    }
    html += '</span>';
    return html;
  }

  /* ---------- render: desktop grid ---------- */
  function renderGrid() {
    if (!gridTable) return;
    var thead = gridTable.querySelector('thead tr');
    var tbody = gridTable.querySelector('tbody');
    while (thead.children.length > 1) thead.removeChild(thead.lastChild);
    tbody.innerHTML = '';

    templates.forEach(function (tpl) {
      var th = document.createElement('th');
      th.scope = 'col';
      th.textContent = truncate(tpl.name, 20);
      th.title = tpl.name;
      thead.appendChild(th);
    });

    reports.forEach(function (report) {
      var tr = document.createElement('tr');
      var th = document.createElement('th');
      th.scope = 'row';
      th.className = 'sticky-col';
      th.textContent = truncate(report.notebook_name || report.filename, 25);
      th.title = report.filename;
      tr.appendChild(th);

      templates.forEach(function (tpl) {
        var td = document.createElement('td');
        var cell = getCell(report.id, tpl.id);
        var status = cell ? cell.status : 'not_started';
        td.className = 'grid-cell status-' + status;
        td.style.backgroundColor = STATUS_COLORS[status] || '#e0e0e0';
        td.dataset.rid = report.id;
        td.dataset.tid = tpl.id;
        td.setAttribute('role', 'gridcell');
        td.setAttribute('aria-label',
          (report.notebook_name || report.filename) + ' × ' + tpl.name + ': ' + STATUS_LABELS[status]);
        td.innerHTML = '<span class="cell-status-label">' + STATUS_LABELS[status] + '</span>' +
          (cell ? cellControls(cell) : '');
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
  }

  /* ---------- render: mobile cards ---------- */
  function renderCards() {
    if (!cardList) return;
    cardList.innerHTML = '';
    reports.forEach(function (report) {
      templates.forEach(function (tpl) {
        var cell = getCell(report.id, tpl.id);
        var status = cell ? cell.status : 'not_started';
        var card = document.createElement('div');
        card.className = 'status-card status-' + status;
        card.style.borderLeftColor = STATUS_COLORS[status] || '#e0e0e0';
        card.dataset.rid = report.id;
        card.dataset.tid = tpl.id;
        card.innerHTML =
          '<div class="card-header">' +
            '<strong class="card-report">' + escapeHtml(truncate(report.notebook_name || report.filename, 30)) + '</strong>' +
            '<span class="card-template">' + escapeHtml(truncate(tpl.name, 30)) + '</span>' +
          '</div>' +
          '<div class="card-body">' +
            '<span class="card-status" style="background:' + STATUS_COLORS[status] + '">' + STATUS_LABELS[status] + '</span>' +
            (cell ? cellControls(cell) : '') +
          '</div>';
        cardList.appendChild(card);
      });
    });
  }

  /* ---------- responsive render ---------- */
  function render() {
    var isMobile = window.innerWidth < MOBILE_BP;
    if (gridWrapper) gridWrapper.style.display = isMobile ? 'none' : '';
    if (cardList) cardList.style.display = isMobile ? '' : 'none';
    var hasData = reports.length && templates.length;
    if (emptyMsg) emptyMsg.style.display = hasData ? 'none' : 'block';
    if (!hasData) return;
    if (isMobile) renderCards(); else renderGrid();
    updateProgress();
  }

  /* ---------- tooltip ---------- */
  function showTooltip(cell, anchor) {
    if (!tooltipEl) return;
    document.getElementById('proc-tip-task-id').textContent = cell.task_id || '—';
    document.getElementById('proc-tip-started').textContent = formatTime(cell.started_at);
    document.getElementById('proc-tip-elapsed').textContent = elapsed(cell.started_at);
    var errRow = tooltipEl.querySelector('.tooltip-error');
    if (cell.error_message) {
      document.getElementById('proc-tip-error').textContent = cell.error_message;
      errRow.style.display = '';
    } else { errRow.style.display = 'none'; }
    var rect = anchor.getBoundingClientRect();
    tooltipEl.style.top = (rect.bottom + window.scrollY + 6) + 'px';
    tooltipEl.style.left = (rect.left + window.scrollX) + 'px';
    tooltipEl.classList.add('visible');
    tooltipEl.setAttribute('aria-hidden', 'false');
  }

  function hideTooltip() {
    if (!tooltipEl) return;
    tooltipEl.classList.remove('visible');
    tooltipEl.setAttribute('aria-hidden', 'true');
  }

  /* ---------- API / cell actions ---------- */
  function startCell(rid, tid) {
    apiPost('/api/generate/' + rid + '/' + tid)
      .then(function () { setBatchStatus('Started'); })
      .catch(function (e) { setBatchStatus('Error: ' + e.message); });
  }
  function stopCell(rid, tid) {
    apiDelete('/api/generate/' + rid + '/' + tid)
      .then(function () { setBatchStatus('Stopped'); })
      .catch(function (e) { setBatchStatus('Error: ' + e.message); });
  }
  function retryCell(rid, tid) {
    apiPost('/api/generate/' + rid + '/' + tid + '/retry')
      .then(function () { setBatchStatus('Retrying'); })
      .catch(function (e) { setBatchStatus('Error: ' + e.message); });
  }

  /* ---------- WebSocket ---------- */
  function setWsIndicator(connected) {
    if (!wsIndicator) return;
    if (connected) { wsIndicator.style.display = 'none'; }
    else { wsIndicator.textContent = 'Live updates disconnected. Reconnecting\u2026'; wsIndicator.style.display = 'block'; }
  }

  function connectWs() {
    var proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(proto + '//' + location.host + '/ws/grid');
    ws.onopen = function () { wsReconnectDelay = 1000; setWsIndicator(true); };
    ws.onmessage = function (ev) {
      try {
        var msg = JSON.parse(ev.data);
        if (msg.type === 'cell_update' && msg.data) {
          cellMap[cellKey(msg.data.report_id, msg.data.template_id)] = msg.data;
          render();
        } else if (msg.type === 'batch_update' && Array.isArray(msg.data)) {
          msg.data.forEach(function (c) { cellMap[cellKey(c.report_id, c.template_id)] = c; });
          render();
        }
      } catch (e) { /* ignore */ }
    };
    ws.onclose = function () {
      setWsIndicator(false);
      setTimeout(function () { wsReconnectDelay = Math.min(wsReconnectDelay * 2, 30000); connectWs(); }, wsReconnectDelay);
    };
    ws.onerror = function () { ws.close(); };
  }

  /* ---------- batch controls ---------- */
  function bindBatch() {
    var actions = {
      'proc-start-all': '/api/batch/start',
      'proc-pause': '/api/batch/pause',
      'proc-resume': '/api/batch/resume',
      'proc-stop-all': '/api/batch/stop',
      'proc-retry-failed': '/api/batch/retry-failed'
    };
    Object.keys(actions).forEach(function (id) {
      var btn = document.getElementById(id);
      if (!btn) return;
      btn.addEventListener('click', function () {
        setBatchStatus('Working\u2026');
        apiPost(actions[id])
          .then(function (d) { setBatchStatus(d.status || 'Done'); })
          .catch(function (e) { setBatchStatus('Error: ' + e.message); });
      });
    });
  }

  /* ---------- delegated events ---------- */
  function bindEvents() {
    document.addEventListener('click', function (e) {
      var btn = e.target.closest('[data-action]');
      if (!btn) return;
      var action = btn.dataset.action, rid = btn.dataset.rid, tid = btn.dataset.tid;
      if (action === 'start') startCell(rid, tid);
      else if (action === 'stop') stopCell(rid, tid);
      else if (action === 'retry') retryCell(rid, tid);
      else if (action === 'download') {
        markOffline((getCell(rid, tid) || {}).task_id || rid + '_' + tid);
        render();
      }
    });

    /* tooltips */
    document.addEventListener('mouseover', function (e) {
      var el = e.target.closest('.grid-cell, .status-card');
      if (!el) return;
      var c = getCell(el.dataset.rid, el.dataset.tid);
      if (c) showTooltip(c, el);
    });
    document.addEventListener('mouseout', function (e) {
      if (e.target.closest('.grid-cell, .status-card')) hideTooltip();
    });
    document.addEventListener('focusin', function (e) {
      var el = e.target.closest('.grid-cell, .status-card');
      if (!el) return;
      var c = getCell(el.dataset.rid, el.dataset.tid);
      if (c) showTooltip(c, el);
    });
    document.addEventListener('focusout', function (e) {
      if (e.target.closest('.grid-cell, .status-card')) hideTooltip();
    });

    /* resize */
    var resizeTimer;
    window.addEventListener('resize', function () {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(render, 150);
    });
  }

  /* ---------- load data ---------- */
  async function loadGrid() {
    try {
      var resp = await fetch('/api/grid');
      if (!resp.ok) throw new Error('Failed to load grid');
      var data = await resp.json();
      reports = data.reports || [];
      /* only show non-excluded templates */
      templates = (data.templates || []).filter(function (t) { return !t.is_excluded; });
      (data.cells || []).forEach(function (c) { cellMap[cellKey(c.report_id, c.template_id)] = c; });
      render();
    } catch (e) {
      if (emptyMsg) { emptyMsg.textContent = 'Failed to load processing data.'; emptyMsg.style.display = 'block'; }
    }
  }

  /* ---------- init ---------- */
  progressText.textContent = 'Loading\u2026';
  loadGrid().then(function () {
    bindBatch();
    bindEvents();
    connectWs();
  });
})();