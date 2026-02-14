/**
 * artifacts.js – Artifact browser for the NotebookLM Dashboard.
 *
 * Handles artifact listing, filtering, preview, and download.
 * Fetches both local and remote artifacts, merges them with deduplication,
 * and applies filters uniformly.
 *
 * Depends on utils.js for escapeHtml, formatDate helpers.
 *
 * Requirements: 1.1, 1.3, 1.4, 1.5, 11.1, 11.2, 11.3, 11.4, 11.5, 11.6
 */
(function () {
  'use strict';

  var tbody = document.getElementById('artifact-tbody');
  var emptyMsg = document.getElementById('empty-msg');
  var filterForm = document.getElementById('filter-form');
  var clearBtn = document.getElementById('btn-clear-filters');
  var previewPanel = document.getElementById('artifact-preview');
  var previewTitle = document.getElementById('preview-title');
  var previewContent = document.getElementById('preview-content');
  var closePreviewBtn = document.getElementById('btn-close-preview');
  var errorBanner = document.getElementById('remote-error-banner');
  var errorBannerMsg = errorBanner ? errorBanner.querySelector('.remote-error-msg') : null;
  var dismissBannerBtn = errorBanner ? errorBanner.querySelector('.btn-dismiss-banner') : null;
  var announcements = document.getElementById('artifact-announcements');

  /** Full merged artifact list (unfiltered). */
  var allArtifacts = [];
  /** Currently displayed (filtered) artifact list. */
  var artifacts = [];

  /* ---------- helpers ---------- */

  function typeBadgeClass(type) {
    var map = { infographic: 'badge-info', audio: 'badge-audio', video: 'badge-video' };
    return map[type] || '';
  }

  /**
   * Announce a message to screen readers via aria-live region (Finding 8.3).
   */
  function announce(message) {
    if (announcements) {
      announcements.textContent = message;
    }
  }

  /**
   * Show a custom confirmation modal instead of browser confirm() (Finding 5.5).
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
      confirmBtn.textContent = confirmLabel || 'Delete';

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

  /* ---------- error banner ---------- */

  function showErrorBanner(message) {
    if (!errorBanner) return;
    if (errorBannerMsg) errorBannerMsg.textContent = message;
    errorBanner.style.display = '';
  }

  function hideErrorBanner() {
    if (!errorBanner) return;
    errorBanner.style.display = 'none';
  }

  if (dismissBannerBtn) {
    dismissBannerBtn.addEventListener('click', hideErrorBanner);
  }

  /* ---------- merge ---------- */

  /**
   * Merge local and remote artifacts, deduplicating on
   * (source_notebook_id, artifact_name). Local artifacts take priority.
   * Result is sorted by created_at descending.
   */
  function mergeArtifacts(local, remote) {
    var localKeys = {};
    local.forEach(function (a) {
      if (a.source_notebook_id && a.artifact_name) {
        localKeys[a.source_notebook_id + '||' + a.artifact_name] = true;
      }
    });

    var uniqueRemote = remote.filter(function (a) {
      if (!a.source_notebook_id || !a.artifact_name) return true;
      return !localKeys[a.source_notebook_id + '||' + a.artifact_name];
    });

    var merged = local.concat(uniqueRemote);
    merged.sort(function (a, b) {
      var da = a.created_at || '';
      var db = b.created_at || '';
      if (da > db) return -1;
      if (da < db) return 1;
      return 0;
    });

    return merged;
  }

  /* ---------- filter ---------- */

  function applyFilters(params) {
    if (!params || Object.keys(params).length === 0) {
      artifacts = allArtifacts;
    } else {
      artifacts = allArtifacts.filter(function (a) {
        if (params.source_location) {
          if (!a.source_location || a.source_location !== params.source_location) return false;
        }
        if (params.source_filename) {
          var sourceMatch = a.source_filename || a.source_notebook_title || '';
          if (sourceMatch !== params.source_filename) return false;
        }
        if (params.artifact_type && a.artifact_type !== params.artifact_type) {
          return false;
        }
        return true;
      });
    }
    render();
  }

  /* ---------- render ---------- */

  function groupByNotebook(list) {
    var groups = {};
    var order = [];
    list.forEach(function (a) {
      var nbId = a.source_notebook_id || '_ungrouped';
      if (!groups[nbId]) {
        var title = a.source_notebook_title || a.source_filename || 'Local Artifacts';
        groups[nbId] = { notebookId: nbId, notebookTitle: title, artifacts: [] };
        order.push(nbId);
      }
      groups[nbId].artifacts.push(a);
    });
    return order.map(function (id) { return groups[id]; });
  }

  function render() {
    tbody.innerHTML = '';
    emptyMsg.textContent = 'No artifacts found.';
    emptyMsg.style.display = artifacts.length ? 'none' : 'block';
    document.getElementById('artifact-table').style.display = artifacts.length ? '' : 'none';

    var notebookGroups = groupByNotebook(artifacts);

    notebookGroups.forEach(function (group) {
      if (group.notebookId !== '_ungrouped') {
        var headerTr = document.createElement('tr');
        headerTr.className = 'notebook-group-header';
        headerTr.setAttribute('data-notebook-id', group.notebookId);

        // Finding 8.5/11.1: Use CSS class instead of inline styles for linked badge
        var linkedBadge = '';
        var isLinked = group.artifacts.some(function (a) { return a.is_linked; });
        if (isLinked) {
          linkedBadge = ' <span class="badge badge-linked">Linked</span>';
        }
        // Finding 11.1: Removed inline styles from header td — now uses .notebook-group-header td CSS
        headerTr.innerHTML =
          '<td colspan="5">' +
          escapeHtml(group.notebookTitle) + linkedBadge +
          ' <button class="btn btn-sm btn-danger btn-delete-notebook" data-notebook-id="' + escapeAttr(group.notebookId) + '" data-notebook-title="' + escapeAttr(group.notebookTitle) + '" type="button" aria-label="Delete notebook ' + escapeAttr(group.notebookTitle) + '">Delete Notebook</button>' +
          '</td>';
        tbody.appendChild(headerTr);
      }

      group.artifacts.forEach(function (a) {
        var sourceName = a.source_filename || a.source_notebook_title || '—';
        var isRemote = a.is_remote;
        var actionsHtml;

        if (isRemote) {
          // Finding 11.3: Use CSS class instead of inline styles for remote badge
          actionsHtml =
            '<span class="badge badge-remote">Remote</span> ' +
            '<button class="btn btn-sm btn-delete" data-id="' + escapeAttr(a.id) + '" data-name="' + escapeAttr(a.artifact_name) + '" type="button" aria-label="Delete ' + escapeAttr(a.artifact_name) + '">Delete</button>';
        } else {
          // Finding 11.2: Added btn-danger class for consistent destructive button styling
          actionsHtml =
            '<button class="btn btn-sm btn-preview" data-id="' + a.id + '" data-type="' + a.artifact_type + '" data-name="' + escapeAttr(a.artifact_name) + '" type="button" aria-label="Preview ' + escapeAttr(a.artifact_name) + '">Preview</button> ' +
            '<a class="btn btn-sm" href="/api/artifacts/' + a.id + '" download aria-label="Download ' + escapeAttr(a.artifact_name) + '">Download</a> ' +
            '<button class="btn btn-sm btn-delete" data-id="' + escapeAttr(a.id) + '" data-name="' + escapeAttr(a.artifact_name) + '" type="button" aria-label="Delete ' + escapeAttr(a.artifact_name) + '">Delete</button>';
        }

        var tr = document.createElement('tr');
        tr.setAttribute('data-notebook-id', a.source_notebook_id || '');
        tr.innerHTML =
          '<td data-label="Name">' + escapeHtml(a.artifact_name) + '</td>' +
          '<td data-label="Type"><span class="badge ' + typeBadgeClass(a.artifact_type) + '">' + escapeHtml(a.artifact_type) + '</span></td>' +
          '<td data-label="Source">' + escapeHtml(sourceName) + '</td>' +
          '<td data-label="Created">' + formatDate(a.created_at) + '</td>' +
          '<td data-label="Actions">' + actionsHtml + '</td>';
        tbody.appendChild(tr);
      });
    });
  }

  /* ---------- API ---------- */

  async function loadArtifacts(params) {
    hideErrorBanner();

    try {
      var results = await Promise.allSettled([
        fetch('/api/artifacts').then(function (r) { return r.ok ? r.json() : []; }),
        fetch('/api/artifacts/remote').then(function (r) { return r.ok ? r.json() : { artifacts: [], error: 'Remote fetch failed' }; })
      ]);

      var localArtifacts = [];
      var remoteArtifacts = [];

      if (results[0].status === 'fulfilled') {
        localArtifacts = results[0].value || [];
      }

      if (results[1].status === 'fulfilled') {
        var remoteData = results[1].value || {};
        remoteArtifacts = remoteData.artifacts || [];
        if (remoteData.error) {
          showErrorBanner('Could not load remote artifacts: ' + remoteData.error);
        }
      } else {
        showErrorBanner('Could not load remote artifacts. Showing local artifacts only.');
      }

      allArtifacts = mergeArtifacts(localArtifacts, remoteArtifacts);
      applyFilters(params);
    } catch (e) {
      console.error('Failed to load artifacts', e);
      // Finding 9.1: Show user-facing error instead of silent failure
      showErrorBanner('Failed to load artifacts. Check your connection and try refreshing.');
      // Replace loading indicator with empty state
      allArtifacts = [];
      applyFilters(params);
    }
  }

  function getFilterParams() {
    var params = {};
    var loc = document.getElementById('filter-location').value.trim();
    var fname = document.getElementById('filter-filename').value.trim();
    var type = document.getElementById('filter-type').value;
    if (loc) params.source_location = loc;
    if (fname) params.source_filename = fname;
    if (type) params.artifact_type = type;
    return params;
  }

  /* ---------- preview ---------- */

  function showPreview(id, type, name) {
    previewTitle.textContent = name;
    previewContent.innerHTML = '';

    var src = '/api/artifacts/' + id + '/preview';

    if (type === 'infographic') {
      var img = document.createElement('img');
      img.src = src;
      img.alt = name;
      previewContent.appendChild(img);
    } else if (type === 'audio') {
      var audio = document.createElement('audio');
      audio.controls = true;
      audio.src = src;
      previewContent.appendChild(audio);
    } else if (type === 'video') {
      var video = document.createElement('video');
      video.controls = true;
      video.src = src;
      previewContent.appendChild(video);
    }

    previewPanel.style.display = 'block';
    // Finding 8.4: Move focus to preview panel on open
    previewPanel.focus();
  }

  function hidePreview() {
    previewPanel.style.display = 'none';
    previewContent.innerHTML = '';
  }

  /* ---------- delete ---------- */

  /**
   * Delete an artifact after user confirmation (Req 4.1, 4.4, 4.5).
   * Uses custom modal (Finding 5.5) and manages focus after deletion (Finding 8.2).
   */
  async function deleteArtifact(artifactId, artifactName, btnElement) {
    var confirmed = await showConfirmModal(
      'Delete Artifact',
      'Are you sure you want to delete "' + artifactName + '"?',
      'Delete',
      'Keep'
    );
    if (!confirmed) return;

    // Finding 5.2: Disable button during async operation
    btnElement.disabled = true;

    try {
      var response = await fetch('/api/artifacts/' + encodeURIComponent(artifactId), {
        method: 'DELETE',
      });

      if (!response.ok) {
        var errData = await response.json().catch(function () { return {}; });
        var errMsg = errData.detail || 'Failed to delete artifact';
        showErrorBanner('Delete failed: ' + errMsg);
        btnElement.disabled = false;
        return;
      }

      allArtifacts = allArtifacts.filter(function (a) { return a.id !== artifactId; });
      artifacts = artifacts.filter(function (a) { return a.id !== artifactId; });

      // Finding 8.2: Determine next focusable element before removing row
      var row = btnElement.closest('tr');
      var nextRow = row ? row.nextElementSibling : null;
      if (row) row.remove();

      // Finding 8.3: Announce deletion to screen readers
      announce('Artifact "' + artifactName + '" deleted.');

      // Finding 8.2: Move focus to next row's delete button, or empty message
      if (artifacts.length === 0) {
        emptyMsg.textContent = 'No artifacts found.';
        emptyMsg.style.display = 'block';
        document.getElementById('artifact-table').style.display = 'none';
        emptyMsg.setAttribute('tabindex', '-1');
        emptyMsg.focus();
      } else if (nextRow) {
        var nextBtn = nextRow.querySelector('.btn-delete, .btn-delete-notebook');
        if (nextBtn) nextBtn.focus();
      }
    } catch (e) {
      console.error('Failed to delete artifact', e);
      showErrorBanner('Delete failed: ' + e.message);
      btnElement.disabled = false;
    }
  }

  /**
   * Delete a notebook after user confirmation (Req 5.1, 5.4, 5.5).
   * Uses custom modal (Finding 5.5) and manages focus after deletion (Finding 8.2).
   */
  async function deleteNotebook(notebookId, notebookTitle, btnElement) {
    var confirmed = await showConfirmModal(
      'Delete Notebook',
      'Are you sure you want to delete notebook "' + notebookTitle + '" and all its artifacts?',
      'Delete Notebook',
      'Keep'
    );
    if (!confirmed) return;

    // Finding 5.3: Disable button during async operation
    btnElement.disabled = true;

    try {
      var response = await fetch('/api/notebooks/' + encodeURIComponent(notebookId), {
        method: 'DELETE',
      });

      if (!response.ok) {
        var errData = await response.json().catch(function () { return {}; });
        var errMsg = errData.detail || 'Failed to delete notebook';
        showErrorBanner('Delete failed: ' + errMsg);
        btnElement.disabled = false;
        return;
      }

      allArtifacts = allArtifacts.filter(function (a) { return a.source_notebook_id !== notebookId; });
      artifacts = artifacts.filter(function (a) { return a.source_notebook_id !== notebookId; });

      // Find next group header before removing rows
      var allRows = tbody.querySelectorAll('tr[data-notebook-id]');
      var lastRemovedIndex = -1;
      var rowArray = Array.from(allRows);
      rowArray.forEach(function (row, idx) {
        if (row.dataset.notebookId === notebookId) {
          lastRemovedIndex = idx;
          row.remove();
        }
      });

      // Finding 8.3: Announce deletion to screen readers
      announce('Notebook "' + notebookTitle + '" and all its artifacts deleted.');

      // Finding 8.2: Move focus after deletion
      if (artifacts.length === 0) {
        emptyMsg.textContent = 'No artifacts found.';
        emptyMsg.style.display = 'block';
        document.getElementById('artifact-table').style.display = 'none';
        emptyMsg.setAttribute('tabindex', '-1');
        emptyMsg.focus();
      } else {
        // Focus the next available group header or delete button
        var remainingRows = tbody.querySelectorAll('tr');
        if (remainingRows.length > 0) {
          var nextFocusRow = remainingRows[Math.min(lastRemovedIndex, remainingRows.length - 1)];
          var nextBtn = nextFocusRow ? nextFocusRow.querySelector('.btn-delete-notebook, .btn-delete') : null;
          if (nextBtn) nextBtn.focus();
        }
      }
    } catch (e) {
      console.error('Failed to delete notebook', e);
      showErrorBanner('Delete failed: ' + e.message);
      btnElement.disabled = false;
    }
  }

  /* ---------- events ---------- */

  // Finding 10.1: Filter submit uses client-side filtering instead of re-fetching
  filterForm.addEventListener('submit', function (e) {
    e.preventDefault();
    var params = getFilterParams();
    applyFilters(params);
  });

  clearBtn.addEventListener('click', function () {
    filterForm.reset();
    applyFilters({});
  });

  tbody.addEventListener('click', function (e) {
    var btn = e.target.closest('.btn-preview');
    if (btn) {
      showPreview(btn.dataset.id, btn.dataset.type, btn.dataset.name);
      return;
    }

    var nbDelBtn = e.target.closest('.btn-delete-notebook');
    if (nbDelBtn) {
      var notebookId = nbDelBtn.dataset.notebookId;
      var notebookTitle = nbDelBtn.dataset.notebookTitle;
      deleteNotebook(notebookId, notebookTitle, nbDelBtn);
      return;
    }

    var delBtn = e.target.closest('.btn-delete');
    if (delBtn) {
      var artifactId = delBtn.dataset.id;
      var artifactName = delBtn.dataset.name;
      deleteArtifact(artifactId, artifactName, delBtn);
    }
  });

  closePreviewBtn.addEventListener('click', hidePreview);

  // Finding 8.1: Escape key handler for preview panel
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && previewPanel.style.display !== 'none') {
      hidePreview();
    }
  });

  /* ---------- init ---------- */
  // Finding 5.4: Show spinner alongside loading text
  emptyMsg.innerHTML = '<span class="loading-spinner" aria-hidden="true"></span>Loading artifacts\u2026';
  loadArtifacts();

  // Expose mergeArtifacts for testing
  if (typeof window !== 'undefined') {
    window._artifactsModule = {
      mergeArtifacts: mergeArtifacts
    };
  }
})();
