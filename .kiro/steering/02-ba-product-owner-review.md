---
inclusion: manual
---

# Business Analyst & Product Owner Review Standards

Senior BA and PO review checklist for the NotebookLM Dashboard project. Covers requirements quality, user journey coverage, test traceability, and product completeness.

## 1. Requirements Completeness

- [x] Every user-facing feature has a user story with "As a... I want... So that..." format
- [x] Each user story has measurable acceptance criteria using WHEN/SHALL/IF/THEN language
- [x] Edge cases are explicitly called out in acceptance criteria
- [x] Error scenarios have defined behavior
- [x] Requirements cover the full CRUD lifecycle for each entity
- [x] Cross-cutting concerns addressed: authentication, authorization, data validation
- [x] Requirements are traceable: each has a unique ID referenced in design and tasks

## 2. User Journey Coverage

- [x] Happy path fully specified for each feature
- [x] Error recovery paths defined
- [x] First-time user experience considered (empty states, prompts to upload)
- [x] Power user workflows supported (batch operations, Select All/Deselect All)
- [x] Data loss prevention addressed (unsaved changes warning, confirmation dialogs)
- [x] Session management covered (login, logout, session-based auth)

## 3. Acceptance Criteria Quality

- [x] Criteria are testable
- [x] Criteria are unambiguous
- [x] Criteria include positive and negative cases
- [x] Criteria specify exact behavior
- [x] Timing/performance criteria specified where relevant (2-second status update, 2-hour timeout)
- [x] Data integrity criteria cover cascade behavior

## 4. Test Case Coverage Review

- [x] Every backend-testable acceptance criterion has at least one test
- [x] Test cases cover boundary values (empty inputs, zero files, missing artifacts)
- [x] Integration tests verify end-to-end flows
- [x] Property-based tests validate 6 correctness properties
- [x] 316 tests passing (unit + property-based)

## 5. Product Gaps Analysis

- [x] CRUD audit complete for all entities
- [x] Feedback audit complete for all user actions
- [x] Validation audit complete for all inputs
- [x] Error message audit complete
- [ ] Template deletion not implemented (excluded templates are hidden via `is_excluded`)
- [ ] No onboarding/first-run experience for new users
- [ ] No search/filter on the prompts page

## 6. Data Integrity & Consistency

- [x] Cascade delete defined: report deletion cascades to cells
- [x] Notebook deletion cascades to local cells and artifacts
- [x] Duplicate detection via content hashing (reports) and prompt hashing (templates)
- [x] Deduplication key: (report_id, template_id) for generation cells
- [x] Conflict resolution: user-edited names protected from automatic overwrite

## 7. Non-Functional Requirements

- [x] Performance: 2-second status update via WebSocket
- [x] Scalability: semaphore-bounded concurrent SDK calls (max 5)
- [x] Security: path traversal protection, input validation, parameterized SQL
- [x] Responsive design: 320px to 2560px, mobile card layout below 768px
- [x] Crash recovery: in-progress tasks resume on restart

## CRUD Completeness (All Specs Combined)

| Entity | Create | Read | Update | Delete | Notes |
|--------|--------|------|--------|--------|-------|
| Reports | ✅ Upload PDF/MD | ✅ List | ✅ Edit notebook name | ✅ Delete + cascade | Complete |
| Templates | ✅ Upload .md / auto-load | ✅ List/Browse grouped | ✅ Edit content, toggle exclusion | ❌ Not implemented | `is_excluded` hides them |
| Artifacts | ✅ Generate | ✅ List/Preview/Download | N/A | ✅ Delete (local + remote) | Complete |
| Notebooks | ✅ Create via generation | ✅ List remote | N/A | ✅ Delete (remote + cascade) | Complete |
| Generation Cells | ✅ Auto-created | ✅ Grid view | ✅ Status transitions | ✅ Cascade with report/notebook | Complete |

## Feedback Completeness (All Specs Combined)

| Action | Success Feedback | Error Feedback | Confirmation |
|--------|-----------------|----------------|--------------|
| File upload | ✅ Toast with filenames | ✅ Error with reason | N/A (auto-upload) |
| Template upload | ✅ Per-file message | ✅ Per-file error | N/A |
| Template edit | ✅ Save confirmation | ✅ Validation error (empty content) | N/A |
| Template toggle | ✅ Immediate UI update | ✅ API error | N/A |
| Batch start | ✅ Status with enqueued/skipped counts | ✅ Error banner | N/A |
| Artifact download | ✅ Browser download | ✅ 404 message | N/A |
| Artifact delete | ✅ Row removed | ✅ Error message | ✅ Confirm dialog |
| Notebook delete | ✅ Rows removed | ✅ Error message | ✅ Confirm dialog |
| Report delete | ✅ Row removed | ✅ Error message | ✅ Confirm dialog |
| Duplicate detected | ✅ Warning dialog | N/A | ✅ Reuse/create option |
| Remote fetch fail | ✅ Error banner | N/A | N/A |
| WebSocket disconnect | ✅ Disconnection indicator | N/A | N/A |

## Validation Completeness

| Input | Validation | Backend | Frontend |
|-------|-----------|---------|----------|
| Report file format | PDF/MD only | ✅ | ✅ |
| Report file size | 50MB max | ✅ (413) | — |
| Template file format | .md only | ✅ | ✅ |
| Template content | Non-empty | ✅ | ✅ |
| Filename sanitization | Path traversal prevention | ✅ | — |
| Artifact ID format | Remote ID parsing | ✅ | — |
| Report/Template existence | 404 on missing | ✅ | — |
| Artifact path | Within output directory | ✅ | — |

## Acceptance Criteria Coverage Summary (Active Spec)

The prompt-management-and-processing-view spec has 11 requirements with 69 acceptance criteria:

| Requirement | AC Count | Backend Testable | Manual Only | Property Tests |
|-------------|----------|-----------------|-------------|----------------|
| Req 1: SDK Fix | 10 | 10 | 0 | 2 (P1) |
| Req 2: Upload | 8 | 6 | 2 | 1 (P2) |
| Req 3: Browsing | 7 | 1 | 6 | 1 (P6) |
| Req 4: Editing | 5 | 2 | 3 | 0 |
| Req 5: Matrix | 6 | 1 | 5 | 1 (P3) |
| Req 6: Real-Time | 5 | 2 | 3 | 0 |
| Req 7: Dedup | 7 | 7 | 0 | 2 (P4, P5) |
| Req 8: Long-Run | 5 | 5 | 0 | 0 |
| Req 9: Deletion | 5 | 4 | 1 | 0 |
| Req 10: Offline | 6 | 3 | 3 | 0 |
| Req 11: Nav | 5 | 2 | 3 | 0 |
| **TOTAL** | **69** | **43** | **26** | **6 properties** |

## End-to-End Workflow Validation

Every user journey must be walkable from start to finish.

### Key User Journeys

1. **Upload → Browse → Process → Monitor → Download**
   - Upload files on `/files` → Upload/select prompts on `/prompts` → Navigate to `/processing` → Start batch → Monitor via WebSocket → Download artifacts (individual or ZIP)
   - Status: ✅ Complete

2. **Edit prompt → Re-process → Verify new artifact**
   - Edit template content on `/prompts` → New content hash computed → Re-run generates new artifact
   - Status: ✅ Complete

3. **Delete report → Verify cascade**
   - Delete report on `/files` → Cells deleted → Offer to delete remote notebook
   - Status: ✅ Complete

4. **Crash recovery**
   - App restarts → Detects in-progress cells → Resumes polling → Status updates via WebSocket
   - Status: ✅ Complete

### Journey Gaps

- [ ] No guided first-time experience — new users see empty pages with no direction
- [ ] Template selection on `/prompts` is disconnected from `/processing` — user must navigate between pages
- [ ] No "re-process only changed files" workflow despite content hashing capability

## Entity Management UI Audit

| Entity | Browse Page | Create UI | Edit UI | Delete UI | Notes |
|--------|------------|-----------|---------|-----------|-------|
| Reports | `/files` | ✅ Upload | ✅ Edit name | ✅ Delete | Complete |
| Templates | `/prompts` | ✅ Upload .md | ✅ Edit content, toggle | ❌ No delete | Hidden via `is_excluded` |
| Artifacts | `/artifacts` | ✅ Generate | N/A | ✅ Delete | Complete |
| Notebooks | `/artifacts` | ✅ Auto-create | N/A | ✅ Delete | Remote only |
| Generation Cells | `/processing` | ✅ Auto-create | ✅ Start/Stop/Retry | ✅ Cascade | Complete |
