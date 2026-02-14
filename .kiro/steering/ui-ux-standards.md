---
inclusion: manual
---

# UI/UX Design Standards & Guidelines

Senior-level usability and design review checklist for web applications.

## 1. Visual Hierarchy & Layout

- [ ] Clear visual hierarchy: headings, subheadings, body text are distinct sizes
- [ ] Consistent spacing system (margins, padding follow a scale like 4px/8px)
- [ ] Content has a readable max-width (60-80ch for text, ~1400px for layouts)
- [ ] White space is used intentionally to group related elements
- [ ] Page sections have clear visual boundaries (cards, dividers, background shifts)
- [ ] Empty states have helpful messaging and a clear call-to-action

## 2. Color & Contrast

- [ ] Text meets WCAG AA contrast ratio (4.5:1 for normal text, 3:1 for large)
- [ ] Status colors are not the sole indicator — pair with icons or text labels
- [ ] Color palette is consistent across all pages
- [ ] Interactive elements are visually distinct from static content
- [ ] Error states use red/warm tones; success uses green; warnings use amber
- [ ] Disabled states are visually muted but still readable

## 3. Typography & Readability

- [ ] Base font size is at least 16px (1rem) for body text
- [ ] Line height is 1.4–1.6 for body text
- [ ] Font stack includes system fonts for fast rendering
- [ ] No more than 2-3 font sizes per page section
- [ ] Text is left-aligned (not justified) for readability
- [ ] Truncated text has a tooltip or expand mechanism to reveal full content

## 4. Navigation & Wayfinding

- [ ] Current page/section is visually indicated in navigation
- [ ] Navigation is consistent across all pages
- [ ] Logo/brand links back to the main entry point
- [ ] Breadcrumbs or page titles orient the user
- [ ] Back navigation works as expected (browser back button)
- [ ] Skip-to-content link for keyboard users

## 5. Interactive Elements & Feedback

- [ ] Buttons have visible hover, focus, active, and disabled states
- [ ] Loading states show a spinner or skeleton, not a frozen UI
- [ ] Destructive actions require confirmation before executing
- [ ] Success/error feedback appears near the action that triggered it
- [ ] Form inputs show validation errors inline, not just at the top
- [ ] Async operations show progress or at minimum a loading indicator
- [ ] Buttons are disabled during async operations to prevent double-submit
- [ ] Toast/status messages auto-dismiss but are also manually dismissable
- [ ] Toast/status messages must include a dismiss button (×) in addition to auto-dismiss timers
- [ ] Destructive actions must use custom confirmation modals with descriptive action labels (e.g. "Delete Notebook" / "Cancel"), not browser `confirm()` with generic "OK/Cancel"
- [ ] Delete buttons must be disabled at the start of async operations and re-enabled only on failure, to prevent double-submit
- [ ] Loading text (e.g. "Loading artifacts…") must be accompanied by a spinner or animated indicator — text alone is not sufficient

## 6. Forms & Input

- [ ] All inputs have visible labels (not just placeholders)
- [ ] Required fields are marked
- [ ] Placeholder text is supplementary, not the only label
- [ ] Tab order follows visual layout (left-to-right, top-to-bottom)
- [ ] Form submission works with Enter key
- [ ] File inputs show selected file names before upload
- [ ] Input fields have appropriate autocomplete attributes
- [ ] Filter forms should use client-side filtering when data is already loaded — avoid unnecessary network requests on form submit

## 7. Responsive Design

- [ ] Layout adapts gracefully from 320px to 2560px+
- [ ] Tables convert to cards or stacked layout on mobile
- [ ] Touch targets are at least 44x44px on mobile
- [ ] No horizontal scrolling on mobile (except intentional scroll containers)
- [ ] Font sizes remain readable on all screen sizes (no text below 12px)
- [ ] Modals/tooltips don't overflow the viewport on small screens
- [ ] All data tables using stacked mobile layout must have `data-label` pseudo-elements on `td` cells (via `td::before { content: attr(data-label); }`) — not just some tables
- [ ] Group header rows (e.g. notebook headers with `colspan`) need mobile-specific styling (left border accent, distinct background) since `colspan` breaks in stacked layout
- [ ] `.btn-sm` inside tables must have a 44px minimum touch target on mobile — add a media query override matching the `.btn-xs` pattern

## 8. Accessibility (a11y)

- [ ] All images have alt text (decorative images use alt="" or aria-hidden)
- [ ] ARIA landmarks are used (main, nav, banner, complementary)
- [ ] Interactive elements are keyboard-operable (Tab, Enter, Escape)
- [ ] Focus is managed after dynamic content changes (modals, deletions)
- [ ] Screen reader announcements for dynamic updates (aria-live regions)
- [ ] Color is never the only means of conveying information
- [ ] Focus indicators are visible and high-contrast
- [ ] Tables use proper th/scope attributes
- [ ] Preview/detail panels must have an Escape key handler to close, and must receive focus on open (add `tabindex="-1"` and call `.focus()`)
- [ ] After deleting a row from a list/table, focus must move to the next row or to the empty-state message — never leave focus orphaned
- [ ] Dynamic content changes (deletions, loads, status updates) must be announced via a visually-hidden `aria-live="polite"` region
- [ ] Tooltips must be accessible via keyboard — add `focusin`/`focusout` handlers, not just `mouseover`/`mouseout`

## 9. Error Handling & Recovery

- [ ] Error messages explain what went wrong and how to fix it
- [ ] Network errors suggest checking connection and retrying
- [ ] Failed operations can be retried without re-entering data
- [ ] 404/empty states guide the user to a productive next step
- [ ] Errors don't leave the UI in a broken or unrecoverable state
- [ ] Network errors must show a user-facing message (banner, inline error, or toast) — never only `console.log`
- [ ] If an async load fails, replace the loading indicator with an error message — never leave the UI stuck on "Loading…"
- [ ] Deletion failures must show user-facing feedback near the affected row or in a status area

## 10. Performance & Perceived Speed

- [ ] Initial page load shows content or skeleton within 1-2 seconds
- [ ] Optimistic UI updates where safe (update UI before server confirms)
- [ ] Large lists use pagination or virtual scrolling
- [ ] Static assets are cacheable (versioned URLs or cache headers)
- [ ] No layout shifts after page load (reserve space for async content)

## 11. Consistency & Polish

- [ ] Button styles are consistent (same padding, radius, font across pages)
- [ ] Icon usage is consistent (same icon = same meaning everywhere)
- [ ] Spacing between sections is uniform
- [ ] Transitions/animations are subtle and purposeful (150-300ms)
- [ ] No orphaned UI elements (buttons that do nothing, empty containers)
- [ ] Confirmation dialogs use clear action labels (not just "OK/Cancel")
- [ ] Move inline styles to CSS classes for consistency and maintainability — avoid `style="..."` in JS-generated HTML
- [ ] Destructive button styling must be consistent across all pages — use a shared class (`.btn-delete` or `.btn-danger`) rather than mixing conventions
- [ ] Badge styling (e.g. "Remote", "Linked") must use CSS classes (`.badge-remote`, `.badge-linked`) not inline styles

## 12. Project-Specific UX Patterns

Patterns discovered during the NotebookLM Dashboard UX review. Apply these when building similar features.

### Table Patterns
- [ ] When adding a new table that uses mobile stacked layout, always add `data-label` attributes on `<td>` elements and the corresponding `td::before` CSS rule in the mobile media query — copy the pattern from the report table
- [ ] Group header rows in tables (e.g. notebook headers) should use a CSS class (`.notebook-group-header`) with mobile-specific styling (left border accent, padding, distinct background)

### Deletion UX
- [ ] All delete flows must follow this pattern: (1) custom confirmation modal with descriptive labels, (2) disable button during async, (3) remove row on success, (4) move focus to next row or empty message, (5) announce via `aria-live` region, (6) show error on failure
- [ ] File browser already implements focus management after deletion — use it as the reference pattern for other pages

### Preview/Detail Panels
- [ ] Panels that overlay content must: (1) receive focus on open, (2) close on Escape key, (3) have a visible close button
- [ ] Add `tabindex="-1"` to the panel container so it can receive programmatic focus

### Toast Messages
- [ ] All toast/status messages must include both auto-dismiss (timer) and manual dismiss (× button)
- [ ] Pattern: create the toast element with a `.btn-dismiss` child, wire up click handler to remove, and set `setTimeout` for auto-dismiss
