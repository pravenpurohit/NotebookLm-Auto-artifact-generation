# Role A: Tooling & Vendor Landscape Scout (Deep Research Prompt)

## Purpose
Identify the **best-in-class AI tools** and a coherent **toolchain** to:
- Ingest ~50 Hindi spiritual PDFs (all of which are scanned)
- Summarize and structure content into a beginner-friendly curriculum
- Create multilingual + simple/complex variants
- Create microlearning scripts for videos/illustrations/animations
- Build a website with AI-assisted coding (non-expert coder)
- Generate videos efficiently at scale
- Build a Q&A system grounded in the books (with citations)

## What you must do (constraints)
- Do **not** anchor on any one brand. Provide multiple options per category.
- Assume user is willing to pay for multiple tools, but prefers **low complexity** and **high reliability**.
- Prioritize tools that support **Indian languages** (Hindi + others) and **multilingual workflows**.
- Include **data privacy** and “does vendor use uploaded data for training?” analysis where possible.
- Provide **pricing tiers** and whether an API is available.

## Inputs I will provide (paste below before running)
- Books list: Assume non-published non copyright protected books
- Target languages: Primary language for each state in India + Top 10 global spoken languages
- Audience: All possible: [Beginners / Intermediate / Advanced]. Hence the language simplicity switcher is necessary on website, and transliation, and while creating video scripts, and website design
- Constraints: No constraints on Budget, hosting, etc. But want to keep it simple and as automated and AI based as possible

---

## Primary Deep Research Prompt (copy/paste)

You are **Role A: Tooling & Vendor Landscape Scout**.

Goal: produce a **market map + shortlist** of the best tools and vendors (as of today) for a multilingual spiritual education project based on ~50 Hindi PDFs.

### Project requirements
- Content source: ~50 Hindi spiritual PDFs (all of which are scanned)
- Output: multilingual website (Primary language for each state in India + Top 10 global spoken languages), with:
  - Language switcher
  - Complexity switcher: “Simple daily-use language” vs “Complex/complete language”
- Content strategy:
  - Step-by-step beginner introduction (“learning path”), using AI to select/summarize
  - Ignore very deep content and long stories to keep website concise
  - Create microlearning units: bite-sized, self-sufficient videos/illustrations/animations
- Q&A:
  - Users ask existential/spiritual questions; system answers grounded in book content, with citations.
- Builder skill level:
  - User is not an expert coder; wants AI tools to help build site and content.

### Your tasks
1. Create a **taxonomy of tool categories** needed (end-to-end). Example categories:
   - PDF ingestion & text extraction (Hindi OCR if needed)
   - Knowledge management / notebooking / source-grounded chat
   - Summarization + curriculum generation (structured outputs)
   - Translation & localization management (25 languages, 2 complexity levels)
   - RAG / vector search / embeddings (multilingual)
   - Web build (framework, CMS, hosting, search, analytics)
   - AI coding assistants & site generators (non-coder-friendly)
   - Video generation (text-to-video / avatar video / animation)
   - Voiceover / dubbing / lip-sync (multilingual)
   - Illustration generation & storyboard tools
   - Review & QA tools (fact-checking, hallucination reduction, glossary enforcement)

2. For each category:
   - Identify **top tools (5–10)** and give a **shortlist (top 3)**.
   - Compare on: quality, Indian language support, pricing, privacy, learning curve, integrations/API, reliability, output control.

3. Provide a **recommended default toolchain**:
   - “Best overall” chain (balanced)
   - “Privacy-first” chain
   - “Budget-conscious” chain
   - Each chain should describe: inputs/outputs, how tools connect, and what is manual vs automated.

4. Provide a **decision matrix**:
   - Weighted criteria (weights you choose, justify briefly)
   - Table scoring your top contenders per category

5. Provide **implementation guidance** for a non-coder:
   - What subscriptions to start with
   - Minimal setup steps
   - Common pitfalls

### Output format (strict)
- Section A: Market map diagram (ASCII ok) + tool categories
- Section B: Category-by-category table (tools, pros/cons, pricing, privacy, citations)
- Section C: Recommended toolchains (3 variants)
- Section D: Decision matrix
- Section E: Setup checklist (first 2 weeks)
- Include citations for all factual claims.

### Guardrails
- Be explicit about uncertainties and regional language limitations.
- Do not recommend tools that cannot practically support Hindi + Indian languages at scale.

---

## Follow-up prompts (run after you get initial output)

### A1: Force a privacy deep-dive
Re-check the shortlisted vendors’ data usage policies and enterprise/private options. Create a clear table: “Uploaded content used for training? (Y/N/Unclear)”, “Retention”, “Export options”, “On-prem / self-host options”, “Regional compliance notes (India/EU)”.

### A2: Force a “non-coder” bias
Given the user is a non-expert coder, re-rank the shortlist emphasizing: easiest UX, best templates, best integrations, best support. Provide a “minimum viable stack” that can launch in <30 days.

### A3: Force Indian-language reality check
Audit each proposed tool specifically for **Hindi + other Indian languages**: OCR quality, translation quality, speech synthesis availability, dubbing/lip-sync support, UI localization.

