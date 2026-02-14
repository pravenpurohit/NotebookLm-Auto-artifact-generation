/**
 * file-browser.js – Report file management for the NotebookLM Dashboard.
 *
 * Handles file upload (auto-upload on selection), report listing, selection,
 * deletion, and notebook name editing. Depends on utils.js for escapeHtml,
 * escapeAttr, formatSize, formatDate helpers.
 *
 * Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 3.1, 3.2
 */
(function () {
  'use strict';

  var fileInput = document.getElementById('file-input');
  var uploadForm = document.getElementById('upload-form');
  var uploadError = document.getElementById('upload-error');
  var uploadFeedback = document.getElementById('upload-feedback');
  var tbody = document.getElementById('report-tbody');
  var emptyMsg = document.getElementById('empty-msg');
  var selectAll = document.getElementById('select-all');
  var reportActions = document.getElementById('report-actions');
  var selectionCount = document.getElementById('selection-count');
  var deleteSelectedBtn = document.getElementById('btn-delete-selected');

  var reports = [];
  var _nameDebounceTimers = {};
  var _toastTimer = null;
  var announcements = document.getElementById('file-browser-announcements');

  /* ---------- helpers ---------- */

  function announce(message) {
    if (announcements) {
      announcements.textContent = message;
    }
  }

  function showError(msg) {
    uploadError.textContent = msg;
    uploadError.style.display = 'block';
  }

  function hideError() {
    uploadError.textContent = '';
    uploadError.style.display = 'none';
  }

  function showProgress(fileCount) {
    uploadFeedback.innerHTML = '<div class="upload-progress"><span class="loading-spinner" aria-hidden="true"></span>Uploading ' + fileCount + ' file' + (fileCount !== 1 ? 's' : '') + '…</div>';
  }

  function showSuccess(filenames) {
    var list = filenames.map(function (n) { return escapeHtml(n); }).join(', ');
    // Finding 5.1: Add dismiss button to success toast
    uploadFeedback.innerHTML = '<div class="upload-success">Uploaded: ' + list +
      ' <button type="button" class="btn-dismiss-toast" aria-label="Dismiss">&times;</button></div>';
    var dismissBtn = uploadFeedback.querySelector('.btn-dismiss-toast');
    if (dismissBtn) {
      dismissBtn.addEventListener('click', function () {
        clearFeedback();
      });
    }
    clearTimeout(_toastTimer);
    _toastTimer = setTimeout(function () {
      uploadFeedback.innerHTML = '';
    }, 5000);
  }

  function clearFeedback() {
    uploadFeedback.innerHTML = '';
    clearTimeout(_toastTimer);
  }

  /* ---------- render ---------- */

  function buildReportRow(r) {
    var tr = document.createElement('tr');
    tr.dataset.id = r.id;
    tr.innerHTML =
      '<td data-label="Select"><input type="checkbox" class="row-check" data-id="' + r.id + '" aria-label="Select ' + r.filename + '"></td>' +
      '<td data-label="Filename">' + escapeHtml(r.filename) + '</td>' +
      '<td data-label="Size">' + formatSize(r.file_size) + '</td>' +
      '<td data-label="Last Modified">' + formatDate(r.last_modified) + '</td>' +
      '<td data-label="Notebook Name"><input type="text" class="notebook-name-input" data-id="' + r.id + '" value="' + escapeAttr(r.notebook_name) + '" aria-label="Notebook name for ' + r.filename + '"></td>' +
      '<td data-label="Actions"><button class="btn btn-sm btn-danger btn-delete" data-id="' + r.id + '" type="button" aria-label="Delete ' + r.filename + '">Delete</button></td>';
    return tr;
  }

  function render() {
    tbody.innerHTML = '';
    emptyMsg.textContent = 'No reports added yet. Upload PDF or MD files above.';
    emptyMsg.style.display = reports.length ? 'none' : 'block';

    reports.forEach(function (r) {
      tbody.appendChild(buildReportRow(r));
    });

    updateSelectionUI();
  }

  function appendReports(newReports) {
    newReports.forEach(function (r) {
      tbody.appendChild(buildReportRow(r));
    });
    emptyMsg.style.display = reports.length ? 'none' : 'block';
    updateSelectionUI();
  }

  /* ---------- selection ---------- */

  function getCheckedIds() {
    return Array.from(tbody.querySelectorAll('.row-check:checked')).map(function (cb) { return cb.dataset.id; });
  }

  function updateSelectionUI() {
    var ids = getCheckedIds();
    var count = ids.length;
    selectionCount.textContent = count + ' selected';
    reportActions.style.display = count > 0 ? 'flex' : 'none';

    var allBoxes = tbody.querySelectorAll('.row-check');
    selectAll.checked = allBoxes.length > 0 && count === allBoxes.length;
    selectAll.indeterminate = count > 0 && count < allBoxes.length;
  }

  /* ---------- API calls ---------- */

  async function loadReports() {
    try {
      var resp = await fetch('/api/reports');
      if (resp.ok) {
        reports = await resp.json();
        render();
      }
    } catch (e) {
      console.error('Failed to load reports', e);
      // Finding 9.2: Show user-facing error instead of silent failure
      emptyMsg.textContent = 'Failed to load reports. Check your connection and try refreshing.';
      emptyMsg.style.display = 'block';
    }
  }

  async function uploadFiles(fileList) {
    hideError();
    clearFeedback();
    var formData = new FormData();
    var validFiles = [];
    var invalid = [];
    for (var i = 0; i < fileList.length; i++) {
      var name = fileList[i].name.toLowerCase();
      if (!name.endsWith('.pdf') && !name.endsWith('.md')) {
        invalid.push(fileList[i].name);
      } else {
        formData.append('files', fileList[i]);
        validFiles.push(fileList[i].name);
      }
    }
    if (invalid.length) {
      showError('Invalid file format: ' + invalid.join(', ') + '. Only PDF and MD files are accepted.');
      if (!formData.has('files')) return;
    }
    try {
      fileInput.disabled = true;
      showProgress(validFiles.length);
      var resp = await fetch('/api/reports', { method: 'POST', body: formData });
      if (resp.ok) {
        var added = await resp.json();
        reports = reports.concat(added);
        appendReports(added);
        fileInput.value = '';
        var uploadedNames = added.map(function (r) { return r.filename; });
        showSuccess(uploadedNames);

        // Check for duplicate content hashes (Req 7.3)
        var duplicateWarnings = [];
        added.forEach(function (newReport) {
          if (!newReport.content_hash) return;
          reports.forEach(function (existing) {
            if (existing.id !== newReport.id && existing.content_hash === newReport.content_hash) {
              duplicateWarnings.push(
                '"' + newReport.filename + '" has the same content as "' + existing.filename + '". ' +
                'A notebook may already exist for this file.'
              );
            }
          });
        });
        if (duplicateWarnings.length) {
          showConfirmModal(
            'Duplicate File Detected',
            duplicateWarnings.join(' '),
            'OK',
            'Dismiss'
          );
        }
      } else {
        var err = await resp.json();
        clearFeedback();
        showError('Upload failed for ' + validFiles.join(', ') + ': ' + (err.detail || 'Unknown error.'));
      }
    } catch (e) {
      clearFeedback();
      showError('Network error uploading ' + validFiles.join(', ') + '. Please try again.');
    } finally {
      fileInput.disabled = false;
    }
  }

  async function deleteReport(id, btnElement) {
    if (btnElement) btnElement.disabled = true;
    try {
      var deletedReport = reports.find(function (r) { return r.id === id; });
      var resp = await fetch('/api/reports/' + id, { method: 'DELETE' });
      if (resp.ok) {
        reports = reports.filter(function (r) { return r.id !== id; });
        render();
        if (deletedReport) {
          announce('Report "' + deletedReport.filename + '" deleted.');
        }
      } else {
        // Finding 9.3: Show user-facing error on deletion failure
        showError('Failed to delete report. Please try again.');
        if (btnElement) btnElement.disabled = false;
      }
    } catch (e) {
      console.error('Delete failed', e);
      // Finding 9.3: Show user-facing error on deletion failure
      showError('Delete failed: ' + e.message);
      if (btnElement) btnElement.disabled = false;
    }
  }

  async function updateNotebookName(id, name) {
    try {
      var resp = await fetch('/api/reports/' + id, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ notebook_name: name })
      });
      if (!resp.ok) {
        showError('Failed to save notebook name. Please try again.');
      }
    } catch (e) {
      console.error('Update notebook name failed', e);
      showError('Could not save notebook name. Check your connection.');
    }
  }

  /* ---------- event listeners ---------- */

  fileInput.addEventListener('change', function () {
    hideError();
    if (fileInput.files.length) {
      uploadFiles(fileInput.files);
    }
  });

  uploadForm.addEventListener('submit', function (e) {
    e.preventDefault();
  });

  selectAll.addEventListener('change', function () {
    var checked = selectAll.checked;
    tbody.querySelectorAll('.row-check').forEach(function (cb) { cb.checked = checked; });
    updateSelectionUI();
  });

  tbody.addEventListener('change', function (e) {
    if (e.target.classList.contains('row-check')) updateSelectionUI();
    if (e.target.classList.contains('notebook-name-input')) {
      var id = e.target.dataset.id;
      var value = e.target.value;
      clearTimeout(_nameDebounceTimers[id]);
      _nameDebounceTimers[id] = setTimeout(function () {
        updateNotebookName(id, value);
      }, 500);
    }
  });

  tbody.addEventListener('click', function (e) {
    if (e.target.classList.contains('btn-delete')) {
      var deleteBtn = e.target;
      // Finding 5.5: Use custom modal instead of confirm()
      showConfirmModal(
        'Delete Report',
        'Are you sure you want to delete this report?',
        'Delete',
        'Keep'
      ).then(function (confirmed) {
        if (confirmed) {
          deleteReport(deleteBtn.dataset.id, deleteBtn).then(function () {
            var firstBtn = tbody.querySelector('.btn-delete');
            if (firstBtn) firstBtn.focus();
            else fileInput.focus();
          });
        }
      });
    }
  });

  deleteSelectedBtn.addEventListener('click', async function () {
    var ids = getCheckedIds();
    if (!ids.length) return;
    // Finding 5.5: Use custom modal instead of confirm()
    var confirmed = await showConfirmModal(
      'Delete Selected Reports',
      'Are you sure you want to delete ' + ids.length + ' selected report(s)?',
      'Delete ' + ids.length + ' Report' + (ids.length !== 1 ? 's' : ''),
      'Cancel'
    );
    if (!confirmed) return;
    deleteSelectedBtn.disabled = true;
    for (var i = 0; i < ids.length; i++) {
      await deleteReport(ids[i]);
    }
    deleteSelectedBtn.disabled = false;
    fileInput.focus();
  });

  /* ---------- loading indicator ---------- */
  function showLoading() {
    // Finding 5.4: Show spinner alongside loading text
    emptyMsg.innerHTML = '<span class="loading-spinner" aria-hidden="true"></span>Loading reports\u2026';
    emptyMsg.style.display = 'block';
  }

  /* ---------- init ---------- */
  showLoading();
  loadReports();
})();
