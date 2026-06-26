# Decisions

Short record of the load-bearing choices, *why*, and what would make me revisit.

### 1. Buy/assemble before building (managed AWS), not a custom system
**Why:** generic policy lookup is a solved problem; a bespoke build's cost is the
maintenance tail, not the first version. We haven't sized the volume or the
generic-vs-personalized split yet.
**Revisit when:** discovery shows a large share of personalized questions, multi-
jurisdiction logic, or a need to reuse this across many internal knowledge domains.

### 2. Extractive answers, not generative
**Why:** returning HR-approved text verbatim removes the hallucination surface
entirely. For policy, a confidently-wrong answer is the worst outcome.
**Revisit when:** canned phrasing causes real UX friction; then add a generative
layer that rephrases *from* the retrieved passage, plus a groundedness check in eval.

### 3. Two independent gates, with escalation as a DATA flag (not a model inference)
**Why:** confidence alone is unsafe — a sensitive question (harassment, immigration)
can be retrieved with high confidence and must still route to a human. Encoding
`escalation_required` per row lets **HR own the sensitivity boundary**, not the model.
**Revisit when:** the flag set proves too coarse (e.g. needs per-jurisdiction rules).

### 4. Index the question variants, not the answers
**Why:** matching a user's phrasing against known *ways of asking* (question→question)
is far more robust than question→answer. The dataset's `question_variants` are the
retrieval keys.
**Revisit when:** never, for this approach — but variants must be maintained as the
question space grows.

### 5. The spreadsheet is the content-management surface
**Why:** HR edits rows (add a variant, fix an answer, flip `status` to deprecated),
we re-index — no engineer in the loop for content. Directly answers the
maintenance-burden risk. Loader enforces `status == Approved`.
**Revisit when:** content volume outgrows a spreadsheet; migrate to a CMS/S3 + KB.

### 6. Tickets route escalations to a human, with a signal-rich payload
**Why:** "route to a human" needs a destination. Capturing the trigger reason and the
bot's best failed guess turns every escalation into a dataset-improvement signal.
**Revisit:** swap the SQLite stub for ServiceNow/Jira/email; add dedup/rate-limiting.

---

## Deliberately NOT built (and why)
- **Reranker** — overkill at this corpus size; top-1 vs top-3 in eval would tell us if it'd even help.
- **Fine-tuning** — re-training on every policy edit is strictly worse than instant re-indexing.
- **Multi-agent / orchestration framework** — the job is "match and return"; a graph is muscle the problem doesn't ask for.
- **Personalization / HRIS integration** — needs auth + PII + compliance; a funded phase-2 decision, not an MVP.

## Known gaps (would address next)
- Escalation recall is gated by retrieval accuracy — a sensitive question mis-retrieved to a non-sensitive row gets answered. Eval surfaces these; mitigate by raising retrieval quality and by widening Gate 2 (e.g. escalate when top-2 disagree).
- `employee_type` is a second personalization axis (new-hire vs full-time) the MVP doesn't condition on.
- No draft/deprecated rows in the dataset to test that governance filter under load.
