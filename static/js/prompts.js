/**
 * prompts.js – Prompt template management for the NotebookLM Dashboard.
 *
 * Handles template upload (drag-and-drop + file picker), listing grouped by
 * artifact type, selection/exclusion toggles, inline editing, and navigation
 * to the processing page.
 *
 * Requirements: 2.1–2.8, 3.1–3.7, 4.1–4.5
 */
(function () {
  'use strict';

  /* ---------- DOM refs ---------- */
  var dropZone = document.getElementById('drop-zone');
  var fileInput = document.getElementById('prompt-file-input');
  var feedback = document.getElementById('prompt-upload-feedback');
  var uploadError = document.getElementById('prompt-upload-error');
  var groupsContainer = document.getElementById('template-groups');
  var emptyMsg = document.getElementById('prompt-empty-msg');
  var selectAllBtn = document.getElementById('btn-select-all');
  var deselectAllBtn = document.getElementById('btn-deselect-all');
  var selectionCount = document.getElementById('prompt-selection-count');
  var editorPanel = document.getElementById('prompt-editor');
  var editorTitle = document.getElementById('editor-title');
  var editorTextarea = document.getElementById('editor-textarea');
  var editorValidation = document.getElementById('editor-validation');
  var btnSave = document.getElementById('btn-editor-save');
  var btnCancel = document.getElementById('btn-editor-cancel');
  var announcements = document.getElementById('prompt-announcements');

  var templates = [];
  var editingId = null;
  var originalContent = '';
  var _toastTimer = null;

  /* ---------- helpers ---------- */

  function announce(msg) {
    if (announcements) announcements.textContent = msg;
  }

  function showError(msg) {
    uploadError.textContent = msg;
    uploadError.style.display = 'block';
  }

  function hideError() {
    uploadError.textContent = '';
    uploadError.style.display = 'none';
  }

  function clearFeedback() {
    feedback.innerHTML = '';
    clearTimeout(_toastTimer);
  }

  function showProgress(count) {
    feedback.innerHTML = '<div class="upload-progress"><span class="loading-spinner" aria-hidden="true"></span>Uploading ' + count + ' file' + (count !== 1 ? 's' : '') + '…</div>';
  }

  function showSuccess(names) {
    var list = names.map(function (n) { return escapeHtml(n); }).join(', ');
    feedback.innerHTML = '<div class="upload-success">Uploaded: ' + list +
      ' <button type="button" class="btn-dismiss-toast" aria-label="Dismiss">&times;</button></div>';
    var btn = feedback.querySelector('.btn-dismiss-toast');
    if (btn) btn.addEventListener('click', clearFeedback);
    clearTimeout(_toastTimer);
    _toastTimer = setTimeout(clearFeedback, 5000);
  }

  var TYPE_LABELS = { infographic: 'Infographic', audio: 'Audio', video: 'Video' };
  var TYPE_ICONS = { infographic: '🖼️', audio: '🎧', video: '🎬' };

  /* ---------- API calls ---------- */

  async function loadTemplates() {
    try {
      var resp = await fetch('/api/templates');
      if (resp.ok) {
        templates = await resp.json();
        render();
      }
    } catch (e) {
      console.error('Failed to load templates', e);
      emptyMsg.textContent = 'Failed to load templates. Check your connection and try refreshing.';
      emptyMsg.style.display = 'block';
    }
  }

  async function uploadFiles(fileList) {
    hideError();
    clearFeedback();
    var validFiles = [];
    var invalid = [];
    for (var i = 0; i < fileList.length; i++) {
      var name = fileList[i].name.toLowerCase();
      if (!name.endsWith('.md')) {
        invalid.push(fileList[i].name);
      } else {
        validFiles.push(fileList[i]);
      }
    }
    if (invalid.length) {
      showError('Invalid file format: ' + invalid.join(', ') + '. Only .md files are accepted.');
      if (!validFiles.length) return;
    }
    if (!validFiles.length) return; /* AC 2.7: zero-file no-op */

    fileInput.disabled = true;
    showProgress(validFiles.length);
    var uploaded = [];
    var errors = [];

    for (var j = 0; j < validFiles.length; j++) {
      var fd = new FormData();
      fd.append('file', validFiles[j]);
      try {
        var resp = await fetch('/api/templates', { method: 'POST', body: fd });
        if (resp.ok) {
          var tpl = await resp.json();
          uploaded.push(tpl);
        } else {
          var err = await resp.json();
          errors.push(validFiles[j].name + ': ' + (err.detail || 'Unknown error'));
        }
      } catch (e) {
        errors.push(validFiles[j].name + ': Network error');
      }
    }

    if (uploaded.length) {
      /* merge into local list, replacing duplicates by filename */
      uploaded.forEach(function (u) {
        var idx = templates.findIndex(function (t) { return t.filename === u.filename; });
        if (idx >= 0) templates[idx] = u;
        else templates.push(u);
      });
      render();
      showSuccess(uploaded.map(function (t) { return t.filename; }));
      announce('Uploaded ' + uploaded.length + ' template' + (uploaded.length !== 1 ? 's' : '') + '.');
    }
    if (errors.length) {
      showError(errors.join('; '));
    }
    fileInput.value = '';
    fileInput.disabled = false;
  }

  async function toggleExclusion(id, isExcluded) {
    try {
      var resp = await fetch('/api/templates/' + id + '/exclude', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ is_excluded: isExcluded })
      });
      if (!resp.ok) {
        showError('Failed to update template selection.');
        return false;
      }
      /* update local state */
      var tpl = templates.find(function (t) { return t.id === id; });
      if (tpl) tpl.is_excluded = isExcluded;
      return true;
    } catch (e) {
      showError('Network error updating selection.');
      return false;
    }
  }

  async function saveContent(id, content) {
    try {
      var resp = await fetch('/api/templates/' + id, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: content })
      });
      if (!resp.ok) {
        var err = await resp.json();
        throw new Error(err.detail || 'Save failed');
      }
      var tpl = templates.find(function (t) { return t.id === id; });
      if (tpl) { tpl.content = content; tpl.content_edited = true; }
      return true;
    } catch (e) {
      editorValidation.textContent = 'Error: ' + e.message;
      return false;
    }
  }
  async function deleteTemplate(id) {
    var tpl = templates.find(function (t) { return t.id === id; });
    var name = tpl ? (tpl.name || tpl.filename) : 'this template';
    if (!confirm('Delete "' + name + '"?')) return;
    try {
      var resp = await fetch('/api/templates/' + id, { method: 'DELETE' });
      if (!resp.ok) {
        var err = await resp.json();
        throw new Error(err.detail || 'Delete failed');
      }
      templates = templates.filter(function (t) { return t.id !== id; });
      render();
      updateSelectionCount();
      announce('Deleted ' + name);
    } catch (e) {
      showError('Failed to delete: ' + e.message);
    }
  }



  /* ---------- render ---------- */

  function buildTemplateRow(t) {
    var div = document.createElement('div');
    div.className = 'template-row' + (t.is_excluded ? ' excluded' : '');
    div.dataset.id = t.id;

    var checked = t.is_excluded ? '' : ' checked';
    var editedBadge = t.content_edited ? ' <span class="badge badge-edited" title="Content edited">edited</span>' : '';
    var audioBadge = t.audio_format ? ' <span class="badge badge-audio">' + escapeHtml(t.audio_format) + '</span>' : '';

    div.innerHTML =
      '<label class="template-check-label">' +
        '<input type="checkbox" class="template-check" data-id="' + t.id + '"' + checked + ' aria-label="Include ' + escapeAttr(t.name || t.filename) + '">' +
      '</label>' +
      '<span class="template-number">' + escapeHtml(String(t.number || '')) + '</span>' +
      '<span class="template-name">' + escapeHtml(t.name || t.filename) + editedBadge + audioBadge + '</span>' +
      '<button class="btn btn-sm btn-edit-template" data-id="' + t.id + '" type="button" aria-label="Edit ' + escapeAttr(t.name || t.filename) + '">Edit</button>' +
      '<button class="btn btn-sm btn-delete-template" data-id="' + t.id + '" type="button" aria-label="Delete ' + escapeAttr(t.name || t.filename) + '">✕</button>';

    return div;
  }

  function render() {
    groupsContainer.innerHTML = '';
    emptyMsg.style.display = templates.length ? 'none' : 'block';

    if (!templates.length) return;

    /* group by artifact_type */
    var groups = {};
    templates.forEach(function (t) {
      var type = t.artifact_type || 'unknown';
      if (!groups[type]) groups[type] = [];
      groups[type].push(t);
    });

    /* sort groups in fixed order */
    var order = ['infographic', 'audio', 'video'];
    Object.keys(groups).forEach(function (k) {
      if (order.indexOf(k) < 0) order.push(k);
    });

    order.forEach(function (type) {
      if (!groups[type]) return;
      var section = document.createElement('div');
      section.className = 'template-group';

      var heading = document.createElement('h3');
      heading.className = 'template-group-heading';
      heading.innerHTML = (TYPE_ICONS[type] || '📄') + ' ' + (TYPE_LABELS[type] || type) +
        ' <span class="template-group-count">(' + groups[type].length + ')</span>';
      section.appendChild(heading);

      /* sort by number within group */
      groups[type].sort(function (a, b) { return (a.number || 0) - (b.number || 0); });

      groups[type].forEach(function (t) {
        section.appendChild(buildTemplateRow(t));
      });

      groupsContainer.appendChild(section);
    });

    updateSelectionCount();
  }

  /* ---------- selection ---------- */

  function getSelectedCount() {
    var count = 0;
    templates.forEach(function (t) { if (!t.is_excluded) count++; });
    return count;
  }

  function updateSelectionCount() {
    var count = getSelectedCount();
    selectionCount.textContent = count + ' selected';
  }

  /* ---------- inline editor ---------- */

  function openEditor(id) {
    var tpl = templates.find(function (t) { return t.id === id; });
    if (!tpl) return;
    editingId = id;
    originalContent = tpl.content || '';
    editorTitle.textContent = 'Edit: ' + (tpl.name || tpl.filename);
    editorTextarea.value = originalContent;
    editorValidation.textContent = '';
    editorPanel.style.display = 'block';
    editorTextarea.focus();
    announce('Editing ' + (tpl.name || tpl.filename));
  }

  function closeEditor() {
    editingId = null;
    originalContent = '';
    editorPanel.style.display = 'none';
    editorValidation.textContent = '';
  }

  function hasUnsavedChanges() {
    return editingId !== null && editorTextarea.value !== originalContent;
  }

  /* ---------- event listeners ---------- */

  /* Drop zone */
  dropZone.addEventListener('click', function () { fileInput.click(); });
  dropZone.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fileInput.click(); }
  });

  fileInput.addEventListener('change', function () {
    if (fileInput.files.length) uploadFiles(fileInput.files);
  });

  dropZone.addEventListener('dragover', function (e) {
    e.preventDefault();
    dropZone.classList.add('drag-over');
  });
  dropZone.addEventListener('dragleave', function () {
    dropZone.classList.remove('drag-over');
  });
  dropZone.addEventListener('drop', function (e) {
    e.preventDefault();
    dropZone.classList.remove('drag-over');
    if (e.dataTransfer.files.length) uploadFiles(e.dataTransfer.files);
  });

  /* Select All / Deselect All */
  selectAllBtn.addEventListener('click', async function () {
    selectAllBtn.disabled = true;
    for (var i = 0; i < templates.length; i++) {
      if (templates[i].is_excluded) await toggleExclusion(templates[i].id, false);
    }
    render();
    selectAllBtn.disabled = false;
    announce('All templates selected.');
  });

  deselectAllBtn.addEventListener('click', async function () {
    deselectAllBtn.disabled = true;
    for (var i = 0; i < templates.length; i++) {
      if (!templates[i].is_excluded) await toggleExclusion(templates[i].id, true);
    }
    render();
    deselectAllBtn.disabled = false;
    announce('All templates deselected.');
  });

  /* Template list: checkbox toggle + edit button */
  groupsContainer.addEventListener('change', function (e) {
    if (e.target.classList.contains('template-check')) {
      var id = e.target.dataset.id;
      var isExcluded = !e.target.checked;
      toggleExclusion(id, isExcluded).then(function (ok) {
        if (!ok) e.target.checked = !e.target.checked; /* revert on failure */
        updateSelectionCount();
      });
    }
  });

  groupsContainer.addEventListener('click', function (e) {
    if (e.target.classList.contains('btn-edit-template')) {
      openEditor(e.target.dataset.id);
    }
    if (e.target.classList.contains('btn-delete-template')) {
      deleteTemplate(e.target.dataset.id);
    }
  });

  /* Editor save / cancel */
  btnSave.addEventListener('click', async function () {
    var content = editorTextarea.value;
    if (!content.trim()) {
      editorValidation.textContent = 'Prompt content cannot be empty.';
      return;
    }
    editorValidation.textContent = '';
    btnSave.disabled = true;
    var ok = await saveContent(editingId, content);
    btnSave.disabled = false;
    if (ok) {
      announce('Template saved.');
      closeEditor();
      render();
    }
  });

  btnCancel.addEventListener('click', function () {
    if (hasUnsavedChanges()) {
      showConfirmModal('Unsaved Changes', 'You have unsaved changes. Discard them?', 'Discard', 'Keep Editing').then(function (confirmed) {
        if (confirmed) closeEditor();
      });
      return;
    }
    closeEditor();
  });

  /* Unsaved changes warning (AC 4.5) */
  window.addEventListener('beforeunload', function (e) {
    if (hasUnsavedChanges()) {
      e.preventDefault();
      e.returnValue = '';
    }
  });

  /* ---------- loading indicator ---------- */
  function showLoading() {
    emptyMsg.innerHTML = '<span class="loading-spinner" aria-hidden="true"></span>Loading templates…';
    emptyMsg.style.display = 'block';
  }

  /* ---------- init ---------- */
  showLoading();
  loadTemplates();
})();
