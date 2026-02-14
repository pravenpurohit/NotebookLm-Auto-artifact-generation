---
inclusion: manual
---

# Usability Expert Review

Heuristic usability review for the NotebookLM Dashboard. Evaluates end-to-end user flows, task completion paths, cognitive load, information architecture, and interaction friction. Applies Nielsen's usability heuristics and task-oriented analysis to any application feature.

## 1. Task Completion Analysis

For every user-facing feature, verify the complete task flow:

- [ ] User can discover how to start the task (discoverability)
- [ ] User can complete the task without external help or documentation
- [ ] Task has a clear beginning, middle, and end state
- [ ] Number of steps to complete the task is minimized (no unnecessary clicks/pages)
- [ ] User receives confirmation that the task completed successfully
- [ ] User can recover from mistakes at any point in the flow without starting over
- [ ] Task progress is visible when the operation takes more than 1 second
- [ ] Multi-step tasks show where the user is in the process (progress indicator or breadcrumb)

## 2. Visibility of System Status (Nielsen #1)

- [ ] System responds to every user action within 100ms (visual acknowledgment)
- [ ] Operations taking >1s show a loading indicator
- [ ] Operations taking >10s show progress or estimated time remaining
- [ ] Background operations have a visible status indicator (not just console logs)
- [ ] State changes are reflected immediately in the UI (optimistic updates or real-time sync)
- [ ] Connection status is visible when the app depends on a live connection (WebSocket, SSE)
- [ ] Errors are surfaced in the UI, not silently swallowed

## 3. Match Between System and Real World (Nielsen #2)

- [ ] Labels and terminology match what users expect (no internal jargon)
- [ ] Actions are named from the user's perspective ("Download Report" not "GET /api/artifacts")
- [ ] Status values use human-readable labels ("Processing..." not "in_progress")
- [ ] Icons have universally understood meaning or are paired with text labels
- [ ] Date/time formats match user locale expectations
- [ ] File sizes shown in human-readable units (KB, MB)

## 4. User Control and Freedom (Nielsen #3)

- [ ] Destructive actions are reversible or require explicit confirmation
- [ ] Long-running operations can be cancelled
- [ ] User can navigate away and return without losing work
- [ ] Modal dialogs have a clear dismiss/cancel path (Escape key, X button, Cancel button)
- [ ] Batch operations can be partially undone (stop individual items)
- [ ] Browser back button works as expected (no broken history states)
- [ ] Form data persists across accidental navigation (or user is warned before losing it)

## 5. Consistency and Standards (Nielsen #4)

- [ ] Same action produces the same result everywhere in the app
- [ ] Button placement is consistent (primary action on the right or bottom)
- [ ] Confirmation dialogs use consistent language and button order
- [ ] Status indicators use the same visual language across all pages
- [ ] Navigation patterns are identical on every page
- [ ] Error message format is consistent (same structure, same tone)
- [ ] Empty states follow the same pattern (icon + message + call-to-action)

## 6. Error Prevention (Nielsen #5)

- [ ] Dangerous actions are visually distinct (red button, warning icon)
- [ ] Inputs are constrained to valid values where possible (dropdowns, date pickers)
- [ ] File upload validates type and size before sending to server
- [ ] Duplicate submissions are prevented (button disabled during async operations)
- [ ] User is warned before navigating away from unsaved changes
- [ ] Concurrent conflicting operations are blocked with a clear message (e.g., 409 Conflict)

## 7. Recognition Rather Than Recall (Nielsen #6)

- [ ] All available actions are visible or easily discoverable (no hidden menus for primary actions)
- [ ] Previously entered data is pre-filled when returning to a form
- [ ] Related information is co-located (user doesn't need to remember data from another page)
- [ ] Search and filter are available on lists with more than 10 items
- [ ] Recently used items or frequently accessed features are surfaced
- [ ] Tooltips or inline help explain non-obvious controls

## 8. Flexibility and Efficiency of Use (Nielsen #7)

- [ ] Power users have keyboard shortcuts or batch operations for repetitive tasks
- [ ] Bulk actions available (Select All, Start All, Download All)
- [ ] Drag-and-drop supported where it reduces friction (file upload)
- [ ] Frequently used actions are accessible in fewer clicks than rare actions
- [ ] Default values are sensible and reduce required input
- [ ] Advanced options are hidden but accessible (progressive disclosure)

## 9. Aesthetic and Minimalist Design (Nielsen #8)

- [ ] Each page element serves a purpose — no decorative-only elements that compete for attention
- [ ] Primary action is visually dominant on each page
- [ ] Secondary actions are visually subordinate (outline buttons, text links)
- [ ] Information density is appropriate — not too sparse, not overwhelming
- [ ] Whitespace is used to group related elements and separate unrelated ones
- [ ] Status messages disappear after they are no longer relevant (auto-dismiss toasts)

## 10. Help Users Recognize, Diagnose, and Recover from Errors (Nielsen #9)

- [ ] Error messages are written in plain language (no error codes, no stack traces)
- [ ] Error messages explain what went wrong AND what the user can do about it
- [ ] Error state provides a clear path to retry or fix the issue
- [ ] Partial failures show which items succeeded and which failed
- [ ] Network errors suggest checking connection and offer a retry button
- [ ] Validation errors appear next to the relevant field, not in a generic banner

## 11. Help and Documentation (Nielsen #10)

- [ ] First-time users can understand the app without reading documentation
- [ ] Empty states serve as onboarding (explain what the page is for and how to get started)
- [ ] Complex features have inline help or tooltips
- [ ] Error messages link to relevant help when applicable (e.g., "Run `playwright install chromium`")
- [ ] Terminology is consistent between UI labels and any documentation

## 12. Information Architecture

- [ ] Navigation structure matches user mental model (task-oriented grouping)
- [ ] Page titles clearly describe the page content
- [ ] Related features are grouped together in navigation
- [ ] User can reach any primary feature within 2 clicks from the home page
- [ ] Breadcrumbs or page titles provide location context
- [ ] Cross-page workflows have clear navigation links between steps

## 13. Cognitive Load Assessment

- [ ] Each page has a single primary purpose (not overloaded with unrelated features)
- [ ] Decision points present no more than 5-7 options at once
- [ ] Complex workflows are broken into discrete steps
- [ ] Status information is summarized before showing details (overview first, drill down on demand)
- [ ] Users are not required to hold information in memory across page transitions
- [ ] Defaults and smart suggestions reduce the number of decisions users must make

## 14. Flow Continuity and Interruption Recovery

- [ ] User can resume a multi-step workflow after a browser refresh
- [ ] Session expiry during a workflow provides a clear path to re-authenticate and continue
- [ ] Background operations continue when the user navigates to a different page
- [ ] Returning to a page shows the current state, not a stale snapshot
- [ ] WebSocket/SSE reconnection restores the UI to the correct state without user action
- [ ] Crash recovery resumes in-progress work transparently

## 15. Cross-Page Workflow Friction

For workflows that span multiple pages, verify:

- [ ] Each step links to the next step (no dead ends)
- [ ] User doesn't need to manually remember IDs, names, or selections across pages
- [ ] State set on one page (e.g., template selection) is reflected on dependent pages (e.g., processing matrix)
- [ ] Navigation between workflow steps is bidirectional (can go back and forward)
- [ ] Completing a workflow redirects to a meaningful destination (not a blank page)
