---
inclusion: manual
---

# UI/UX Design Standards & Guidelines

Usability and design review checklist for the NotebookLM Dashboard. Updated to reflect the current frontend across all pages: `/`, `/dashboard`, `/files`, `/prompts`, `/processing`, `/artifacts`.

## 1. Visual Hierarchy & Layout

- [ ] Clear visual hierarchy: headings, subheadings, body text are distinct sizes
- [ ] Consistent spacing system (4px/8px scale)
- [ ] Content has readable max-width (60-80ch for text, ~1400px for layouts)
- [ ] White space groups related elements
- [ ] Page sections have clear visual boundaries (cards, dividers, background shifts)
- [ ] Empty states have helpful messaging and call-to-action (prompts page, processing page)

## 2. Color & Contrast

- [ ] Text meets WCAG AA contrast ratio (4.5:1 normal, 3:1 large)
- [ ] Status colors paired with text labels — not color-only (processing matrix cells)
- [ ] Color palette consistent across all pages
- [ ] Interactive elements visually distinct from static content
- [ ] Error: red/warm, Success: green, Warning: amber, Disabled: muted
- [ ] Cell status colors: not_started (gray), pending (blue), in_progress (amber), completed (green), failed (red), stopped (orange)

## 3. Typography & Readability

- [ ] Base font size at least 16px (1rem)
- [ ] Line height 1.4–1.6 for body text
- [ ] System font stack for fast rendering
- [ ] No more than 2-3 font sizes per section
- [ ] Left-aligned text (not justified)
- [ ] Truncated text has tooltip or expand mechanism

## 4. Navigation & Wayfinding

Current navigation: Dashboard | File Browser | Prompts | Processing | Artifacts | Logout

- [ ] Current page visually indicated in navigation (`.active` class)
- [ ] Navigation consistent across all pages (via `base.html`)
- [ ] Logo links back to `/`
- [ ] Skip-to-content link for keyboard users
- [ ] Back navigation works (browser back button)
- [ ] "Start Processing" button on `/prompts` navigates to `/processing`

## 5. Interactive Elements & Feedback

- [ ] Buttons have hover, focus, active, and disabled states
- [ ] Loading states show spinner or skeleton, not frozen UI
- [ ] Destructive actions require confirmation via custom `showConfirmModal()`
- [ ] Success/error feedback appears near the triggering action
- [ ] Async operations show progress indicator
- [ ] Buttons disabled during async operations to prevent double-submit
- [ ] Toast messages include both auto-dismiss timer AND manual dismiss button (×)
- [ ] Never use `window.confirm()` or `window.alert()` — use custom modal pattern

## 6. Forms & Input

- [ ] All inputs have visible labels (not just placeholders)
- [ ] Required fields marked
- [ ] Tab order follows visual layout
- [ ] Form submission works with Enter key
- [ ] File inputs show selected file names before upload
- [ ] Template editor validates non-empty content before save
- [ ] Unsaved changes warning on navigation away (`beforeunload`)

## 7. Responsive Design

- [ ] Layout adapts from 320px to 2560px+
- [ ] Tables convert to cards on mobile (processing matrix, report list)
- [ ] Touch targets at least 44x44px on mobile
- [ ] No horizontal scrolling on mobile (except intentional scroll containers like the matrix)
- [ ] Font sizes readable on all screen sizes (no text below 12px)
- [ ] Modals/tooltips don't overflow viewport on small screens
- [ ] `data-label` pseudo-elements on `td` cells for stacked mobile layout
- [ ] Processing matrix: sticky first column for report names during horizontal scroll

## 8. Accessibility (a11y)

- [ ] All images have alt text
- [ ] ARIA landmarks used (main, nav, banner)
- [ ] Interactive elements keyboard-operable (Tab, Enter, Escape)
- [ ] Focus managed after dynamic content changes (modals, deletions, uploads)
- [ ] `aria-live="polite"` region for dynamic updates
- [ ] Color never the only means of conveying information
- [ ] Focus indicators visible and high-contrast
- [ ] Tables use proper `th`/`scope` attributes
- [ ] Panels close on Escape key, receive focus on open (`tabindex="-1"`)
- [ ] After row deletion, focus moves to next row or empty-state message
- [ ] Tooltips accessible via keyboard (`focusin`/`focusout` handlers)

## 9. Error Handling & Recovery

- [ ] Error messages explain what went wrong and how to fix it
- [ ] Network errors suggest checking connection and retrying
- [ ] Failed operations can be retried without re-entering data
- [ ] Empty states guide user to productive next step
- [ ] Errors don't leave UI in broken state
- [ ] Network errors show user-facing message (banner, toast) — never only `console.log`
- [ ] Failed async load replaces loading indicator with error message
- [ ] Deletion failures show feedback near affected row

## 10. Page-Specific Patterns

### Prompts Page (`/prompts`)
- [ ] Drag-and-drop zone has visible label and border
- [ ] Templates grouped by artifact type (Infographic, Audio, Video)
- [ ] Each template shows: number, name, type, audio format badge, edited indicator
- [ ] Selection checkboxes toggle `is_excluded` via API
- [ ] Select All / Deselect All controls
- [ ] Inline editor opens on template click with full content in textarea
- [ ] Save validates non-empty content
- [ ] Empty state prompts user to upload .md files

### Processing Page (`/processing`)
- [ ] Matrix: rows = reports, columns = non-excluded templates
- [ ] Cells color-coded by status with text labels
- [ ] Cell hover/click shows detail tooltip (task ID, start time, elapsed, error)
- [ ] Per-cell action buttons: start, stop, retry, download, preview
- [ ] Batch controls bar: Start All, Pause, Resume, Stop All, Retry Failed
- [ ] Progress summary bar: "X/Y complete, Z in progress, W failed"
- [ ] WebSocket connection with reconnection and disconnection indicator
- [ ] "Download All Completed" button triggers ZIP download
- [ ] Offline markers via localStorage for downloaded artifacts
- [ ] Mobile: card layout below 768px

### File Browser (`/files`)
- [ ] Auto-upload on file selection (no separate Upload button)
- [ ] Progress indicator during upload
- [ ] Success toast with filenames, auto-dismiss after 5s
- [ ] Editable notebook names preserved across uploads
- [ ] Delete with confirmation dialog and cascade warning

### Artifacts Page (`/artifacts`)
- [ ] Shows both local and remote artifacts
- [ ] Error banner if remote fetch fails (local artifacts still shown)
- [ ] Filters apply to both local and remote
- [ ] Delete with confirmation dialog
- [ ] Inline preview for completed artifacts

## 11. Consistency & Polish

- [ ] Button styles consistent across pages (same padding, radius, font)
- [ ] Icon usage consistent (same icon = same meaning)
- [ ] Spacing between sections uniform
- [ ] Transitions subtle and purposeful (150-300ms)
- [ ] No orphaned UI elements
- [ ] Confirmation dialogs use clear action labels ("Delete Notebook" / "Cancel")
- [ ] Inline styles moved to CSS classes
- [ ] Destructive button styling uses shared class (`.btn-danger`)
- [ ] Badge styling uses CSS classes (`.badge-remote`, `.badge-linked`)

## 12. Feature Completeness

- [ ] Every entity has a dedicated browse/list page
- [ ] Users can create, view, edit each entity through the UI
- [ ] Navigation links exist for every management page
- [ ] Empty states guide users to create their first item
- [ ] Bulk operations available where appropriate (Select All, Download All, Start All)
- [ ] Template deletion is the one known gap — `is_excluded` serves as soft delete
