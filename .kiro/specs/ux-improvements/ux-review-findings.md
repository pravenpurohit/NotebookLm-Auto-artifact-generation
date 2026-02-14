# UX Review Findings — Task 11.1

Review of all frontend changes against `.kiro/steering/ui-ux-standards.md`.

**Reviewer scope:** artifacts.js, file-browser.js, grid.js, utils.js, styles.css, artifacts.html, file_browser.html, base.html, dashboard.html

---

## Section 5: Interactive Elements & Feedback

### Finding 5.1 — Success toast not manually dismissable
- **File:** `static/js/file-browser.js`, lines 45–51
- **Severity:** Medium
- **Issue:** The upload success toast auto-dismisses after 5 seconds (good, per Req 2.6), but there is no close/dismiss button on it. UX standard §5 requires: "Toast/status messages auto-dismiss but are also manually dismissable."
- **Fix:** Add a dismiss button (×) to the `.upload-success` element, similar to how the error banner has `.btn-dismiss-banner`.

### Finding 5.2 — No loading indicator during artifact deletion
- **File:** `static/js/artifacts.js`, lines 296–330
- **Severity:** Low
- **Issue:** When deleting an artifact, the delete button is not disabled during the async operation. UX standard §5 requires: "Buttons are disabled during async operations to prevent double-submit." A user could click Delete multiple times.
- **Fix:** Disable the delete button at the start of `deleteArtifact()` and re-enable on failure.

### Finding 5.3 — No loading indicator during notebook deletion
- **File:** `static/js/artifacts.js`, lines 340–380
- **Severity:** Low
- **Issue:** Same as 5.2 — the notebook delete button is not disabled during the async DELETE call.
- **Fix:** Disable the button during the operation.

### Finding 5.4 — No loading state on initial artifact page load
- **File:** `static/js/artifacts.js`, line 395
- **Severity:** Low
- **Issue:** The empty message is set to "Loading artifacts…" (good), but there's no spinner or skeleton. The page shows a text-only loading state. UX standard §5 says: "Loading states show a spinner or skeleton, not a frozen UI."
- **Fix:** Add a simple CSS spinner or animated indicator alongside the loading text.

### Finding 5.5 — Confirmation dialogs use generic "OK/Cancel" labels
- **File:** `static/js/artifacts.js`, lines 296, 340; `static/js/file-browser.js`, lines 241, 254
- **Severity:** Medium
- **Issue:** All destructive actions use `confirm()` which shows browser-native "OK/Cancel" buttons. UX standard §11 requires: "Confirmation dialogs use clear action labels (not just 'OK/Cancel')." This applies to artifact deletion, notebook deletion, report deletion, and batch stop.
- **Fix:** Replace `confirm()` with a custom modal dialog that has descriptive action labels like "Delete" / "Keep" or "Delete Notebook" / "Cancel".

---

## Section 6: Forms & Input

### Finding 6.1 — Notebook name input uses `change` event instead of `input`
- **File:** `static/js/file-browser.js`, line 228
- **Severity:** Low
- **Issue:** The notebook name debounce is triggered on `change` event (fires on blur), not `input` event (fires on each keystroke). This means the name isn't saved until the user clicks away. While functional, using `input` with debounce would provide more responsive auto-save behavior.
- **Note:** This is a minor UX improvement, not a standards violation.

### Finding 6.2 — Filter form submission doesn't work with Enter key in all cases
- **File:** `static/js/artifacts.js`, lines 267–270
- **Severity:** Low
- **Issue:** The filter form has a `submit` handler that calls `loadArtifacts(params)` — this re-fetches from the server. Since filtering is client-side on the merged list, pressing Enter triggers an unnecessary network request. The `applyFilters()` function should be called directly instead.
- **Note:** Functionally works but is inefficient.

---

## Section 7: Responsive Design

### Finding 7.1 — Artifact table missing `data-label` pseudo-element on mobile
- **File:** `static/css/styles.css`
- **Severity:** High
- **Issue:** The report table has a `td::before { content: attr(data-label); }` rule for mobile stacked layout (line 703), but the artifact table does NOT have an equivalent rule. On mobile, artifact table cells stack but show no labels, making the data unreadable.
- **Fix:** Add `.artifact-table td::before { content: attr(data-label); ... }` in the mobile media query, matching the report table pattern.

### Finding 7.2 — Notebook group header row doesn't adapt on mobile
- **File:** `static/js/artifacts.js`, lines 158–170; `static/css/styles.css`
- **Severity:** Medium
- **Issue:** The notebook group header row uses `colspan="5"` with inline styles. On mobile where the table becomes stacked cards, this header row will look broken — it becomes a block-level element with no special styling to distinguish it as a group header.
- **Fix:** Add mobile-specific styling for `.notebook-group-header` in the media query.

### Finding 7.3 — Delete Notebook button touch target may be too small
- **File:** `static/js/artifacts.js`, line 167
- **Severity:** Low
- **Issue:** The "Delete Notebook" button uses `btn btn-sm` class (min-height: 36px). On mobile, touch targets should be at least 44×44px per UX standard §7.
- **Fix:** The mobile media query already bumps `.btn-xs` to 44px, but `.btn-sm` is not similarly adjusted. Add a mobile override for `.btn-sm` inside tables.

---

## Section 8: Accessibility (a11y)

### Finding 8.1 — No keyboard dismiss for artifact preview panel
- **File:** `static/js/artifacts.js`, lines 253–260
- **Severity:** High
- **Issue:** The preview panel can only be closed by clicking the "✕" button. There is no Escape key handler. UX standard §8 requires: "Interactive elements are keyboard-operable (Tab, Enter, Escape)." A keyboard user who opens a preview has no keyboard way to close it.
- **Fix:** Add a `keydown` listener for Escape that calls `hidePreview()`.

### Finding 8.2 — No focus management after artifact/notebook deletion
- **File:** `static/js/artifacts.js`, lines 296–380
- **Severity:** Medium
- **Issue:** After deleting an artifact or notebook, the row is removed from the DOM but focus is not moved anywhere. UX standard §8 requires: "Focus is managed after dynamic content changes (modals, deletions)." A keyboard user loses their place.
- **Fix:** After deletion, move focus to the next artifact row, or to the empty message if no artifacts remain. (Note: file-browser.js does this correctly — see line 244.)

### Finding 8.3 — No `aria-live` announcement for artifact deletion success
- **File:** `static/js/artifacts.js`
- **Severity:** Medium
- **Issue:** When an artifact is deleted, the row is silently removed. Screen readers get no announcement. UX standard §8 requires: "Screen reader announcements for dynamic updates (aria-live regions)."
- **Fix:** Add a visually-hidden `aria-live="polite"` region and announce "Artifact deleted" or "Notebook deleted" after successful deletion.

### Finding 8.4 — Preview panel doesn't trap focus
- **File:** `static/js/artifacts.js`, `app/templates/artifacts.html`
- **Severity:** Low
- **Issue:** When the preview panel opens, focus is not moved to it. A keyboard user must Tab through the entire page to reach the preview content. While not a modal (so full focus trapping isn't required), moving focus to the panel on open would improve usability.
- **Fix:** Call `previewPanel.focus()` or `closePreviewBtn.focus()` after showing the preview. Add `tabindex="-1"` to the preview panel.

### Finding 8.5 — Linked badge uses color only
- **File:** `static/js/artifacts.js`, line 162
- **Severity:** Low
- **Issue:** The "Linked" badge uses `background:#28a745;color:#fff` — green background with white text. While it does include the text "Linked" (good), the inline style overrides any potential high-contrast mode. UX standard §8: "Color is never the only means of conveying information." The text label satisfies this, but the inline style is fragile.
- **Fix:** Move the badge styling to CSS class `.badge-linked` instead of inline styles.

### Finding 8.6 — Tooltip not accessible to keyboard users
- **File:** `static/js/grid.js`, lines 170–200
- **Severity:** Medium
- **Issue:** The cell tooltip is triggered only by `mouseover`/`mouseout` and `touchstart`. There is no `focus`/`blur` handler, so keyboard users can never see tooltip content. UX standard §8: "Interactive elements are keyboard-operable."
- **Fix:** Add `focusin`/`focusout` event listeners on grid cells to show/hide the tooltip.

---

## Section 9: Error Handling & Recovery

### Finding 9.1 — Network error on artifact load shows no user-facing message
- **File:** `static/js/artifacts.js`, lines 230–232
- **Severity:** Medium
- **Issue:** If the `loadArtifacts()` catch block fires (network error), it only logs to console. The user sees nothing — the page appears frozen with "Loading artifacts…" forever. UX standard §9: "Network errors suggest checking connection and retrying."
- **Fix:** Show the error banner with a message like "Failed to load artifacts. Check your connection and try refreshing."

### Finding 9.2 — Report load failure shows no user-facing message
- **File:** `static/js/file-browser.js`, lines 115–120
- **Severity:** Medium
- **Issue:** If `loadReports()` fails, it only logs to console. The user sees "Loading reports…" forever with no error indication.
- **Fix:** Show an error message in the empty-msg area or upload-error area.

### Finding 9.3 — Report deletion failure shows no user-facing message
- **File:** `static/js/file-browser.js`, lines 137–142
- **Severity:** Low
- **Issue:** If `deleteReport()` fails, it only logs to console. The user gets no feedback that the deletion failed.
- **Fix:** Show an error message near the report row or in the upload-error area.

---

## Section 10: Performance & Perceived Speed

### Finding 10.1 — Filter submit re-fetches from server unnecessarily
- **File:** `static/js/artifacts.js`, lines 267–270
- **Severity:** Low
- **Issue:** Clicking "Apply" on the filter form calls `loadArtifacts(params)` which re-fetches both local and remote artifacts from the server. Since filtering is client-side on the already-merged list, this is wasteful. The `applyFilters()` function should be called directly.
- **Fix:** Change the filter submit handler to call `applyFilters(getFilterParams())` instead of `loadArtifacts(params)`.

---

## Section 11: Consistency & Polish

### Finding 11.1 — Inline styles on notebook group header and linked badge
- **File:** `static/js/artifacts.js`, lines 162–168
- **Severity:** Low
- **Issue:** The notebook group header uses inline styles (`font-weight:bold;background:#f5f5f5;padding:0.5rem 0.75rem;`) and the linked badge uses inline styles (`background:#28a745;color:#fff;font-size:0.7rem;margin-left:0.25rem;`). These should be CSS classes for consistency and maintainability.
- **Fix:** Create `.notebook-group-header td` and `.badge-linked` CSS classes.

### Finding 11.2 — Delete button styling inconsistency
- **File:** `static/js/artifacts.js` vs `static/js/file-browser.js`
- **Severity:** Low
- **Issue:** In file-browser.js, the delete button uses `btn btn-sm btn-danger` (red). In artifacts.js, the delete button uses `btn btn-sm btn-delete` (no danger class, default styling). Destructive actions should be visually consistent.
- **Fix:** Add `btn-danger` class to artifact delete buttons, or create a consistent `.btn-delete` style.

### Finding 11.3 — "Remote" badge uses inline styles
- **File:** `static/js/artifacts.js`, line 180
- **Severity:** Low
- **Issue:** The "Remote" badge uses `style="font-size:0.7rem;opacity:0.7;"` inline. Should be a CSS class like `.badge-remote`.
- **Fix:** Create `.badge-remote` CSS class.

---

## Summary

| Severity | Count | Key Areas |
|----------|-------|-----------|
| High     | 2     | Missing mobile data-labels for artifact table (7.1), No Escape key for preview (8.1) |
| Medium   | 7     | Toast not dismissable (5.1), OK/Cancel dialogs (5.5), Mobile group header (7.2), Focus after deletion (8.2), aria-live for deletions (8.3), Tooltip keyboard access (8.6), Silent network errors (9.1, 9.2) |
| Low      | 9     | Button disable during async (5.2, 5.3), Loading spinner (5.4), Input event (6.1), Filter efficiency (6.2, 10.1), Touch targets (7.3), Preview focus (8.4), Badge inline styles (8.5, 11.1, 11.2, 11.3), Delete error feedback (9.3) |

**Total findings: 18**
