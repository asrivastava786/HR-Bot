# HR FAQ Bot — Complete Deep Dive

Everything you need to understand the project end-to-end: how it works, why
each piece is designed the way it is, and how to talk about it in a follow-up
conversation.

---

## Table of Contents

1. [The Problem Being Solved](#1-the-problem-being-solved)
2. [How the Pieces Fit Together](#2-how-the-pieces-fit-together)
3. [The Data Layer](#3-the-data-layer)
4. [The Retriever — Four Gates](#4-the-retriever--four-gates)
5. [The Ticket System](#5-the-ticket-system)
6. [The Evaluation Harness](#6-the-evaluation-harness)
7. [Key Design Decisions (with reasoning)](#7-key-design-decisions-with-reasoning)
8. [Reading the Eval Results](#8-reading-the-eval-results)
9. [What the Code Does NOT Do (and why)](#9-what-the-code-does-not-do-and-why)
10. [How to Talk About This in an Interview](#10-how-to-talk-about-this-in-an-interview)

---

## 1. The Problem Being Solved

HR teams repeatedly answer the same policy questions from new hires — vacation
accrual, expense rules, benefits deadlines. The goal is to automate the
repetitive ones while routing the sensitive or ambiguous ones to a human, with
enough context that the human's job is easier, not just different.

**The two failure modes that matter:**

- **Confidently wrong answer** — the bot answers a question incorrectly, the
  employee acts on it. For policy questions, this can have legal or financial
  consequences. This is the severe failure. It is worse than no bot at all.

- **Missing an escalation** — the bot answers a question it should have routed
  to HR (e.g., a harassment question, an FMLA eligibility question). Even a
  correct answer here may not be appropriate — some topics require a human
  regardless of whether the bot "knows" the answer.

Every design decision in this project is ultimately about preventing those two
failures.

---

## 2. How the Pieces Fit Together

```
Employee asks a question
        |
        v
   [ Retriever ]          <-- the brain
        |
   Four gates run
        |
   +---------+---------+
   |                   |
ANSWER             ESCALATE
   |                   |
Return               Create
HR-approved          HR ticket
text + citation      (pre-filled)
        |
  [ Ticket Store ]      <-- SQLite (prototype) / ServiceNow (prod)
```

**Files and what they own:**

| File | Responsibility |
|---|---|
| `data_loader.py` | Reads the spreadsheet, enforces governance (approved-only), builds index phrases |
| `retriever.py` | Embeds questions, searches the index, runs four gates, returns answer or escalation |
| `tickets.py` | Stores escalation records in SQLite; stub for ServiceNow/Jira in production |
| `app.py` | FastAPI: exposes `/ask`, `/ticket`, `/tickets` as HTTP endpoints |
| `ui.py` | Gradio chat interface; auto-opens ticket form on escalation |
| `eval.py` | Measures retrieval accuracy, escalation recall, false escalation rate, threshold sweep |
| `tests/test_retriever.py` | Offline tests (no model download) using a bag-of-words stub embedder |

---

## 3. The Data Layer

### The spreadsheet is the content-management surface

The dataset (`data/hr_policy_faq_dataset.xlsx`) is the only place HR needs to
touch to change what the bot says. No engineer is in the loop for content
updates.

**Key columns and what they do:**

| Column | Role |
|---|---|
| `faq_id` | Unique identifier; used to link retrieval results back to the full record |
| `canonical_question` | The "official" phrasing — indexed as a retrieval key |
| `question_variants` | Pipe-separated alternative phrasings ("How do I\|Can I\|What's the process for") — also indexed |
| `approved_answer` | The answer the bot returns verbatim. HR-approved text; the bot never paraphrases it |
| `status` | `Approved / Draft / Deprecated` — only `Approved` rows are loaded |
| `escalation_required` | Boolean. If True, this topic must always route to a human |
| `escalation_reason` | Why — shown to the employee when escalated ("this involves employment law") |
| `source_title / source_section` | What policy document the answer comes from |
| `effective_date` | When the answer was last updated — shown in the citation |
| `country_scope` | If not "General", the bot adds a caveat ("specifics depend on your location") |
| `employee_type` | If not "All employees", the bot adds a caveat |
| `sensitive_topic` | Informational flag; `escalation_required` is the operational one |

### Governance is enforced at load time, not query time

`data_loader.py` filters to `status == "approved"` when building the index. A
draft row literally cannot appear in results — it was never embedded. This means
HR can work on a draft answer without any risk of it surfacing to employees.

### Question → question indexing (not question → answer)

The retrieval index contains *questions* (canonical + variants), not answers.
When an employee asks something, the system finds the most similar *way of
asking*, then returns the answer attached to that FAQ. This is more robust
than embedding answers directly, because people's phrasing varies much more than
the underlying question.

---

## 4. The Retriever — Four Gates

This is the core of the system. The retriever takes a question, searches the
index, and runs four sequential checks before deciding to answer or escalate.

### How retrieval works

1. The employee's question is converted to a vector (a list of ~384 numbers)
   using the `all-MiniLM-L6-v2` sentence-transformer model.
2. That vector is compared against all indexed question vectors in ChromaDB
   (a vector database) using cosine similarity.
3. The top-3 most similar FAQ questions are returned, each with a similarity
   score between 0 and 1. Score of 1.0 = identical. Score of 0.0 = unrelated.

### The four gates (in order)

#### Gate 1 — Confidence threshold

```
if score < THRESHOLD (default 0.45):
    escalate("low_confidence")
```

If the best match has a similarity score below the threshold, the bot doesn't
know the answer. It escalates rather than returning a wrong answer confidently.

**Why 0.45?** The eval's threshold sweep shows this is roughly the crossover
point between "answering usefully" and "answering wrongly". You tune this using
the sweep: lower threshold = answer more questions but risk more wrong answers;
higher threshold = escalate more but safer. HR's risk tolerance determines the
right setting.

#### Gate 2 — Policy/safety override

```
if faq["escalation_required"] == True:
    escalate("policy_escalation")
```

Even if retrieval found the correct FAQ with high confidence, some topics must
route to a human. Examples: harassment reporting, FMLA eligibility, immigration
status, severance negotiation.

**The critical design insight:** HR owns this flag, not the model. The bot
doesn't decide what's sensitive — HR does, by setting the flag in the
spreadsheet. This means HR can change the sensitivity boundary without any
engineering involvement.

**Why this matters:** A model-based sensitivity classifier would be a second
model to maintain, would hallucinate, and HR couldn't audit or adjust it. A
data flag is transparent, auditable, and HR-controlled.

#### Gate 3 — Query-text keyword guard

```
if query contains sensitive keyword (harass, fmla, terminate, relocation, ...):
    escalate("query_sensitive")
```

Gate 2 only fires if retrieval landed on the *correct* escalation-required FAQ.
Gate 3 covers the blind spot: a sensitive question that retrieves confidently to
the *wrong* non-sensitive FAQ. In that case, Gate 2 never sees an escalation
flag, so without Gate 3 the bot would answer.

**The keyword list is conservative by design** — it over-escalates rather than
under-escalates. A false escalation wastes an employee 30 seconds. A missed
escalation on a harassment question has legal consequences.

**Tunable without a deploy:** HR can extend the keyword list via the
`SENSITIVE_KEYWORDS` environment variable.

#### Gate 4 — Top-k ambiguity

```
for each runner-up in top-3:
    if runner-up is escalation_required
    AND (top1_score - runner_up_score) <= TOPK_MARGIN (default 0.15):
        escalate("topk_ambiguity")
```

This gate catches the cases Gate 3 cannot: sensitive questions whose query text
doesn't contain obvious keywords, but where the correct escalation-required FAQ
appears in the top-3 results close behind the wrong non-sensitive match.

**The logic:** if the bot is "choosing" between a safe answer and a sensitive
topic and the scores are close, that ambiguity is itself a reason to escalate.
The bot is not confident enough in its choice to risk answering something that
might need a human.

**Example from the eval:**
- Query: "I paid for something, can I claim?"
- Top-1: FAQ-010 (non-sensitive, expense claim), score 0.689
- Top-2: escalation-required FAQ, score ~0.55
- Gap: 0.139 < TOPK_MARGIN (0.15) → Gate 4 fires → escalate

### What happens after all four gates pass

The bot returns the answer — the verbatim `approved_answer` text from the
spreadsheet, plus a citation showing which document it came from and the
effective date. If there are location or employee-type caveats, those are
appended.

```json
{
  "action": "answer",
  "score": 0.71,
  "faq_id": "FAQ-005",
  "answer": "Full-time employees accrue 1.5 days of PTO per month...",
  "citation": "Employee Handbook Section 4.2 (updated 2024-01-15)",
  "caveat": "Note: specifics depend on your country/location."
}
```

### The escalation payload

When any gate fires, the response includes why and the bot's best guess:

```json
{
  "action": "escalate",
  "reason": "topk_ambiguity",
  "score": 0.689,
  "message": "This needs a person from HR...",
  "best_guess_faq": "FAQ-010"
}
```

The `best_guess_faq` is key. Even when escalating, the bot tells HR "I *think*
this was about FAQ-010 — I just wasn't sure enough to answer." This turns every
escalation into a signal: if the bot keeps guessing FAQ-010 for a question that
should route to FAQ-023, HR can add the phrasing as a variant to FAQ-023 and
fix future retrieval.

---

## 5. The Ticket System

`tickets.py` is deliberately simple. Every escalation creates a ticket record
in SQLite (prototype) with a payload designed to be *useful to HR*, not just
a log:

| Field | Purpose |
|---|---|
| `question` | What the employee actually asked |
| `trigger_reason` | Which gate fired (`low_confidence`, `policy_escalation`, `query_sensitive`, `topk_ambiguity`) |
| `best_guess_faq` | The FAQ the bot thought was closest (the dataset improvement signal) |
| `best_guess_score` | How confident it was in that guess |
| `created_at` | Timestamp |
| `status` | `open` by default; HR closes it when resolved |

**In production this payload goes to ServiceNow / Jira / email — same fields,
different destination.** The code is structured as a stub so the swap is one
line in `tickets.py`, not a redesign.

**Why `trigger_reason` matters:** HR can filter:
- `low_confidence` tickets → questions not covered by the dataset → add new FAQ rows
- `policy_escalation` tickets → working as designed; HR handles and closes
- `topk_ambiguity` tickets → query ambiguous between safe and sensitive → check if variant should be added

This segmentation turns the ticket queue into a prioritized improvement backlog.

---

## 6. The Evaluation Harness

`eval.py` answers the question: "Does this actually work?" before any employee
sees it.

### The train/test split

The dataset has one canonical question and several variant phrasings per FAQ.
The eval:
- **Indexes**: canonical question + even-indexed variants (training set)
- **Tests on**: odd-indexed variants (held-out set)

This is important. If you tested on the same data you indexed, you'd get 100%
retrieval accuracy because the exact phrases are in the index. By holding out
odd variants, you test whether the bot can handle *new phrasings* of known
questions — which is the actual real-world task.

### What the four metrics measure

#### 1. Retrieval top-1 / top-3 accuracy

Of the held-out variants for answerable FAQs (non-escalation-required), what
fraction did the retriever correctly identify as belonging to the right FAQ?

- **Top-1**: the first result is the correct FAQ
- **Top-3**: the correct FAQ appears anywhere in the top 3

Top-3 is the upper bound for Gate 4's effectiveness — it can only catch
ambiguity if the correct FAQ is in the top-3 to begin with.

#### 2. Escalation confusion matrix

This is the most important metric. For every held-out variant:

```
                     Predicted
                  Escalate  |  Answer
Actual  Escalate |   TP     |   FN   |  ← FN is DANGEROUS
        Answer   |   FP     |   TN   |
```

- **Escalation recall (TP / TP+FN):** what fraction of must-escalate questions
  were correctly escalated. Want 100%. A false negative here means the bot
  answered something sensitive.

- **False-escalation rate (FP / FP+TN):** what fraction of answerable questions
  were needlessly escalated. Costs employee time. Want low, but not at the
  expense of escalation recall.

**The asymmetry is intentional:** a missed escalation (FN) is far more costly
than a false escalation (FP). The system is tuned to prefer FP over FN.

#### 3. Out-of-scope refusal

Can the bot refuse questions that are completely unrelated to HR policy?
("Who won the football match?", "What's the wifi password?")

These should all escalate via Gate 1 (low confidence) because no FAQ matches.

#### 4. Threshold sweep

What happens to answer rate, wrong-answer rate, and escalation recall as you
vary the Gate 1 threshold from 0.30 to 0.55?

This lets you pick the threshold that matches HR's risk tolerance:
- If HR says "never answer anything unless very sure" → higher threshold
- If HR says "answer more, we'll correct mistakes" → lower threshold

**Never optimise answer rate alone.** A high answer rate with wrong answers is
worse than a lower answer rate with correct answers.

---

## 7. Key Design Decisions (with reasoning)

### Decision 1: Extractive answers, not generative

The bot returns the HR-approved text *verbatim*. It does not rephrase, summarize,
or elaborate.

**Why:** A generative layer (GPT, Claude, etc.) rephrasing the answer introduces
the possibility of hallucination — the model slightly changes the meaning of a
legal policy statement. For HR policy, a confident wrong answer is the worst
outcome. Extractive answers eliminate this surface entirely.

**What would change this:** if employees find canned phrasing confusing or
robotic and the eval showed this. Then you'd add a generative rephrasing layer,
but you'd also need a groundedness check (does the rephrased answer faithfully
represent the source passage?) and the eval would need a faithfulness metric.
That's a non-trivial addition. Not worth it until there's evidence the current
approach causes friction.

### Decision 2: HR owns the sensitivity boundary (not the model)

The `escalation_required` flag per FAQ row is set by HR in the spreadsheet.
The model has no say in what's sensitive.

**Why:** A classifier that decides what's sensitive would be a black box that HR
can't audit or adjust. When legal requirements change, or a new policy area
becomes sensitive, HR can flip a flag. No engineering ticket required. No model
retraining. No deployment.

**The deeper point:** The people who know what's sensitive are HR and Legal, not
a language model trained on internet text. This design puts the judgment where
the expertise is.

### Decision 3: Four independent gates rather than one compound rule

Each gate addresses a different failure mode independently. They are not
combined into a single score or a single model.

**Why:** Compound rules create interactions that are hard to reason about. If
Gate 2 and Gate 4 were merged into a single "sensitivity score", you'd lose the
ability to explain why any particular escalation happened. With four independent
gates, every escalation has an unambiguous reason code — which is what the
ticket payload captures. HR can look at "policy_escalation" tickets and know
the bot correctly identified a sensitive topic; they can look at "topk_ambiguity"
tickets and know the bot was confused.

### Decision 4: Spreadsheet as content management, not a CMS or database

HR edits rows in Excel/Google Sheets. The bot re-indexes on restart (or on a
scheduled re-index in production).

**Why:** The alternative — a web CMS, a database with an admin UI, a
Confluence plugin — adds tooling that HR has to learn and that engineering has
to maintain. HR already knows Excel. The governance model (draft → approved →
deprecated via the `status` column) is visible to anyone who can open the file.

**What would change this:** if content volume outgrows a spreadsheet (hundreds
of FAQs across multiple jurisdictions with approval workflows). Then migrate to
a CMS with a proper editorial workflow. But that's a phase-2 decision, not an
MVP constraint.

### Decision 5: Question-to-question indexing, not question-to-answer

The index contains question phrasings. Retrieval finds the most similar *question*
and then returns the answer linked to it.

**Why:** People's phrasing of a question varies much more than the underlying
intent. "How does PTO accrue?", "What's my vacation policy?", "How many days
off do I get?" are all the same question. By indexing all the variant phrasings,
the system is explicitly encoding that variation. By contrast, if you indexed
answers (long prose paragraphs), the similarity scores would be dominated by the
length and vocabulary of the answer, not the question structure.

### Decision 6: Signal-rich ticket payload

Every escalation ticket captures the trigger reason, the bot's best-guess FAQ,
and the confidence score — not just the question text.

**Why:** An escalation ticket that says only "employee asked: I want holiday
next week" tells HR the question but nothing about whether it was the right call
to escalate, or what the bot's retrieval looked like. The enriched payload tells
HR: "the bot guessed FAQ-002 at 0.66 confidence but escalated because the score
was within 0.15 of an escalation-required FAQ." That's actionable — HR can
decide to add "I want holiday next week" as a variant to the correct FAQ.

### Decision 7: Buy (managed services) over build for production

The recommended production path is Amazon Q Business or Bedrock Knowledge Bases,
not a custom vector database.

**Why:** The prototype builds a custom embedding + Chroma stack to demonstrate
the ideas. But in production, managing your own embedding model (keeping it
updated, handling GPU infrastructure, monitoring drift) has a maintenance cost
that compounds. Managed services abstract that. The contract — ingest documents,
answer questions, cite sources — is the same. The internals are the vendor's
problem.

**What would change this:** if the problem required deep customization (HRIS
integration for personalized answers, multi-jurisdiction logic, domain-specific
fine-tuning). Those needs justify owning the stack. A generic policy Q&A bot
does not.

---

## 8. Reading the Eval Results

```
TEST SET: 40 held-out variants (19 answerable, 21 must-escalate) + 4 out-of-scope

1) RETRIEVAL (answerable held-out)
   top-1 accuracy : 12/19 = 63%
   top-3 accuracy : 16/19 = 84%

2) DECISION (threshold = 0.45, topk_margin = 0.15)
   escalation recall      : 20/21 = 95%
   false-escalation rate  : 11/19 = 58%
   !! DANGEROUS: 'I want holiday next week' -> FAQ-002 @ 0.66

3) OUT-OF-SCOPE REFUSAL: 4/4 = 100%
```

### What each number means

**63% top-1 retrieval:** For answerable questions, the bot gets the right FAQ
as its first result 63% of the time. This number improves with more question
variants per FAQ — the more ways of asking each question you index, the more
likely a new phrasing matches something in the index.

**84% top-3 retrieval:** The correct FAQ appears in the top 3 results 84% of
the time. This is the ceiling for Gate 4 to exploit — Gate 4 can only act on
runner-ups it can see.

**95% escalation recall:** Of the 21 must-escalate questions, 20 were correctly
escalated. The 1 miss (`"I want holiday next week"`) cannot be caught by any
gate because the correct escalation-required FAQ doesn't appear in its top-3
at all.

**58% false-escalation rate:** This is high, but inflated by the prototype. Two
reasons:
1. The seed dataset is 52% must-escalate rows — unusual for a real deployment
   where most questions are safe and repetitive. In production the ratio would
   be much lower.
2. Gate 4's TOPK_MARGIN=0.15 is conservative relative to a small corpus where
   score gaps are narrow. A larger dataset spreads scores further apart; Gate 4
   fires less.

In production, target false-escalation rate under 20%. Track it as a week-1
metric and adjust TOPK_MARGIN if needed.

**100% out-of-scope refusal:** Questions completely unrelated to HR policy
(wifi password, sports scores) are correctly escalated via Gate 1 (low
confidence). The bot doesn't hallucinate answers to things not in its dataset.

### The one residual dangerous miss

`"I want holiday next week"` is a colloquial phrasing that doesn't retrieve
near its true escalation-required FAQ. The fix is not in the code — it's in
the dataset. HR adds `"I want holiday next week"` as a variant to the correct
FAQ row. Re-index. Gate 2 now fires correctly. Recall hits 100%.

This is the feedback loop closing: escalation ticket → HR spots missing variant
→ adds it to spreadsheet → re-index → fixed.

---

## 9. What the Code Does NOT Do (and why)

### No generative rephrasing
No GPT/Claude layer rephrasing answers. Reason: hallucination risk for policy
text. Would add: a faithfulness/groundedness check in the eval and a rephrase
step in the retriever. Not worth the risk or complexity until extractive answers
prove insufficient.

### No personalization or HRIS integration
The bot cannot answer "how many vacation days do *I* have left" because that
requires querying Workday/ADP with the employee's ID, handling PII, and managing
auth. This is a different project with a compliance scope. The current bot adds
a caveat for questions that touch running totals: "check Workday for your
personal balance."

### No multi-jurisdiction branching
The dataset has `country_scope` and `employee_type` columns and the bot surfaces
them as answer caveats. But it doesn't route UK employees to UK-specific answers
or contractors to contractor-specific answers. Doing that correctly requires
knowing which jurisdiction each employee is in (HRIS integration) and modeling
the rule differences. Phase 2.

### No reranker
A reranker (a second model that re-scores the top-k results for relevance)
would improve top-1 retrieval accuracy. Overkill at 40 FAQ rows. Revisit if
the corpus grows to hundreds of FAQs and top-1 accuracy stays low.

### No fine-tuning
Retraining the embedding model on this corpus would hurt more than help: the
corpus is tiny, and re-training on every policy update is strictly worse than
instant re-indexing. The off-the-shelf `all-MiniLM-L6-v2` generalizes well for
semantic similarity at this scale.

### No authentication on `/tickets` (prototype deliberate choice)
The ticket endpoint is unauthenticated for demo purposes. In production, ticket
contents may include sensitive questions (harassment, medical leave). Access must
be scoped to HR roles via Okta/Azure AD. The FastAPI layer adds OAuth2 middleware;
the ticket store moves to ServiceNow with its own RBAC.

---

## 10. How to Talk About This in an Interview

### The architecture in one sentence
"It's a four-gate retrieval system: the first gate handles confidence, the second
gate lets HR own the sensitivity boundary via a data flag, the third gate catches
sensitive queries that retrieve to the wrong row, and the fourth gate catches
ambiguity between a safe answer and a sensitive topic in the top-3 results."

### The key insight to lead with
"The hardest part of this problem isn't retrieval — it's the governance. Who
approves the answers? What happens when policy changes? What topics must never
be answered by a bot even if the bot knows the answer? I designed the system so
HR controls all of that without filing an engineering ticket."

### On the eval numbers
"Escalation recall is 95% on a synthetic 40-row dataset. The 1 residual miss
is a colloquial phrasing that doesn't retrieve near its true FAQ — the fix is
adding it as a question variant, which is how the feedback loop is supposed to
work. The false-escalation rate is 58%, which looks high but is inflated by the
prototype having a 52% must-escalate ratio. In a real deployment where most
questions are safe and repetitive, I'd expect that to drop below 20%."

### On build vs buy
"For production I'd use Amazon Q Business or Bedrock Knowledge Bases — the same
contract, managed internals. The prototype exists to demo the four-gate logic
and the eval approach. The decision to build custom retrieval into the prototype
was deliberate: it lets me show the architecture clearly without AWS setup
blocking the demo."

### On what you'd do next
"First: add the one missing phrasing to the dataset and confirm recall hits 100%.
Second: run the bot in shadow mode for two weeks — log what it would have answered
against what HR actually answered — before any employee sees it. Third: wire the
thumbs-down button to an HR review queue so wrong-but-accepted answers don't stay
invisible."

### The question that trips people up
*"Why not just use ChatGPT and feed it the HR handbook?"*

"Because that approach gives you a generative layer you can't audit. If the model
rephrases a policy statement and slightly changes the meaning, you won't know
until an employee acts on it. My system returns HR-approved text verbatim — HR
can see exactly what the bot said because it's the same text they wrote. For
legal and policy content, auditability matters more than fluency."
