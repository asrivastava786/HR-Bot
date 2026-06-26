# HR Policy FAQ Bot — Proposal

## The Request (as received)

> "Our HR team spends hours every week answering the same policy questions from
> new hires — things like vacation accrual, expense rules, benefits enrollment
> deadlines. Can we automate this somehow?"

---

## 1. Discovery Questions (Before Building Anything)

The request is scoped to a symptom ("hours per week") rather than a system.
Before committing to any approach, I'd want answers to five things:

**Volume and distribution**
- How many policy questions does HR field per week, roughly? Are they concentrated
  in onboarding windows (first 30/60/90 days) or spread throughout the year?
- What share are genuinely repetitive ("same five questions, different people")
  versus personalized ("what is *my* accrued balance *right now*")?
  The first case is automatable; the second needs HRIS integration and is a
  different project.

**Content and governance**
- Where do the official answers live today — a handbook PDF, a Confluence page,
  a collection of email replies, line-managers' institutional knowledge?
- Who owns each policy, and who has authority to approve the answer the bot gives?
  This is the maintenance question: if HR can't update content without filing an
  IT ticket, the bot will drift out of date faster than it saves time.

**Escalation and risk appetite**
- Are any topics strictly off-limits for a bot — FMLA, immigration status,
  harassment reporting, compensation disputes? HR's list of "never automate
  these" defines Gate 2 of the design before a line of code is written.
- What's the cost of a wrong answer? For "how many vacation days do I get" the
  stakes are low. For "am I entitled to COBRA" they are not. The answer changes
  the threshold you'd set and whether a generative layer is acceptable at all.

**Channel**
- Where do these questions arrive today — Slack, email, a ticketing system?
  The right deployment surface for the bot is wherever the questions already
  show up, not a new portal employees have to find.

---

## 2. Build vs Buy Recommendation

**Recommendation: assemble from managed cloud services (AWS), not build from scratch.**

The core task — "a user asks a question in natural language, the system returns the right passage from an internal document" — is a retrieval problem that vendors have solved. Bespoke vector-search infrastructure has a maintenance tail that compounds; managed services shift that to the vendor.

| | Custom build | Managed (AWS path) | Low-code / iPaaS |
|---|---|---|---|
| **Fit** | Full control | Matches the problem well | Often limited to keyword lookup |
| **Time to first value** | Weeks | Days | Hours |
| **Maintenance** | Team owns infra + model updates | Vendor-managed | Vendor-managed |
| **Personalization ceiling** | Unlimited | High | Low |
| **Cost at low volume** | High (engineer time) | Low | Low |

**Recommended stack:** Amazon Q Business (or Bedrock Knowledge Bases + OpenSearch
Serverless) fronting a Slack app or Teams bot. Content lives in S3 (or Confluence
directly, which Q Business ingests natively). Policy owners update the source; Q
re-indexes automatically.

**Cost model (rough, for budget conversations):**
At ~500 questions/week (a mid-size onboarding cohort), Amazon Q Business runs
~$300–400/month including indexing and query costs. If HR currently spends 4
hours/week answering repetitive questions at a fully-loaded cost of ~$60/hr,
that's ~$960/month of recovered time — the tool pays for itself in the first
month even at 50% deflection. A custom build would cost more in engineer-hours
in month 1 alone, before counting ongoing maintenance. Low-code tools (Notion
AI, Guru) are cheaper but lack the four-gate escalation logic and produce no
structured ticket data for feedback-loop improvement.

**When I'd revise this:** if discovery shows (a) a large share of personalized
questions that need HRIS data, (b) multi-jurisdiction logic that requires
conditional rules per employee type or country, or (c) a need to reuse the same
knowledge layer across many internal domains. Those signal a custom build where
the flexibility is actually needed.

---

## 3. Smallest Version That Delivers Real Value (MVP)

The minimum credible thing is a bot that correctly answers the ten most-asked
policy questions and routes everything else to a human with enough context that
the human spends less time, not more.

**What the MVP does:**

1. HR loads their 10–50 most common Q&A pairs into a spreadsheet (one row per
   question, with the approved answer text and a flag marking sensitive topics).
2. A retrieval layer embeds those questions and matches incoming queries by
   semantic similarity.
3. On a confident match to a non-sensitive row: return the HR-approved answer
   verbatim, with a citation (which document, which section, effective date).
4. On a low-confidence match *or* a sensitive-topic flag: route to a human via
   whatever ticketing/messaging system HR already uses, with a pre-filled payload
   capturing what the employee asked and the bot's best guess at the intent.
5. Deploy in the channel where questions already arrive (Slack is usually right).

**What the MVP explicitly does not do:** access live HRIS data, personalize answers
per employee, support multiple jurisdictions, handle documents outside the seeded
FAQ set, or provide a generative/rephrasing layer.

**Why this scope:** The HR team's time cost is dominated by *repetitive* questions,
not by edge cases. Automating the top 10 probably covers 60–70% of volume. Each
escalation becomes a data signal ("this question wasn't covered, add it") that
improves coverage over time without an engineer in the loop.

**Rollout sequence (shadow mode first, never go live blind):**

The worst way to launch this is to flip it on and hope. The right sequence:

1. **Week 1–2 — shadow mode.** The bot runs silently alongside the existing
   channel. It logs what it *would* have answered (and at what confidence) but
   sends nothing to employees. HR reviews the log daily against what they
   actually answered. This surfaces dataset gaps and threshold mis-settings
   before any employee sees a wrong answer.
2. **Week 3–4 — opt-in.** Available in a dedicated `#hr-bot` Slack channel.
   New hires can try it; HR monitors. Builds trust on both sides. Provides real
   usage data for the first metrics review.
3. **Week 5+ — default.** Bot handles the primary channel. HR retains the
   ability to instantly deprecate any answer row (set `status=deprecated`) if
   something is wrong; re-index takes under a minute.

Shadow mode is non-negotiable. It's the difference between "we think this works"
and "we measured that this works before anyone depended on it."

---

## 4. Measuring Whether It Worked

Three tiers, corresponding to different timeframes:

**Week-1 (deployment sanity)**
- Answer rate: what fraction of submitted questions get a confident answer
  (vs. escalated). Baseline target: ~60%; signals whether the seed dataset is
  too sparse.
- Escalation false-negative rate: what fraction of *sensitive* questions were
  answered rather than escalated. This is the dangerous failure. Target: 0%.

**Month-1 (adoption and quality)**
- Volume deflection: tickets/Slack DMs to HR from new hires, week-over-week, vs.
  the pre-bot baseline. The only number the stakeholder actually cares about.
- Thumbs-down / "not helpful" rate per answered question. HR can review flagged
  answers to catch outdated or wrong policy text before it spreads.

**Quarter-1 (value)**
- HR hours saved (self-reported, or estimated from deflected ticket volume × avg.
  handle time). Should exceed the time HR spends maintaining the dataset; if not,
  adoption is too low or the coverage is wrong.
- Dataset coverage growth: number of distinct intents in the FAQ set. Growing
  coverage means the feedback loop is working.

One metric to explicitly *not* optimise in isolation: answer rate. A bot that
answers 95% of questions but gets 10% of them wrong is worse than one that
answers 60% correctly and escalates the rest.

**Observability (how you know it's degrading before HR tells you):**

Three automated signals, no dashboards required at MVP scale:

- **Escalation rate spike alert:** if the 7-day rolling escalation rate rises
  >20% above baseline, a policy probably changed and the dataset is stale.
  Page the dataset owner, not an engineer.
- **Answer rate floor alert:** if answer rate drops below 20%, something is
  broken (embedding model, index corruption). Page engineering.
- **Weekly gap digest:** every Monday, HR receives a list of the top 10
  questions that were escalated that week with no close FAQ match. These are
  the highest-value rows to add next. No engineer needed; HR uses the digest
  to prioritize spreadsheet updates.

---

## 5. Main Risks

**Wrong answers on policy (the severe failure)**
Policy errors differ from ordinary software bugs: a wrong answer on FMLA
eligibility or expense reimbursement has legal and financial consequences.
*Mitigations:* extractive answers only (return HR-approved text verbatim, no
paraphrasing or generative layer in v1); HR owns the sensitivity flag so sensitive
topics always escalate regardless of retrieval confidence; citation with effective
date on every answer so employees know the source and date.

**Content drift (the slow failure)**
Policy changes, but the bot's dataset doesn't update itself. A 2023 answer to a
2025 question is confidently wrong.
*Mitigations:* the spreadsheet-as-CMS model (HR edits rows; re-indexing is
automatic) means the friction is low. Each row carries an effective date shown
in the citation; stale rows are visible. Quarterly HR review cadence, same as
they'd do for any policy document. Ultimately this is a process problem as much
as a technical one.

**Low adoption (the silent failure)**
If new hires don't use the bot, nothing changes. "Build a portal" almost always
fails; "put it in Slack where questions already arrive" almost always succeeds.
The other adoption risk is HR not trusting the bot and answering questions
directly anyway, which keeps the load on them.
*Mitigations:* deploy in the channel that already has the questions; make
escalation frictionless (one click, pre-filled ticket) so the bot is useful
even when it doesn't know the answer; share deflection metrics with HR so they
can see their time being saved.

**Escalation recall gap**
Gate 2 (the HR-owned sensitivity flag per FAQ row) only fires when retrieval
lands on the *correct* row. A sensitive question that retrieves confidently to
the *wrong* non-sensitive row bypasses Gate 2 entirely and gets answered.
*Mitigations:* Gate 3 — a query-text keyword guard that fires on known
sensitive terms (harassment, FMLA, immigration, termination, etc.) regardless
of what was retrieved. This is implemented in the prototype and tunable via env
var so HR can adjust the keyword list without a deploy. The keyword list is
intentionally conservative: a false escalation costs an employee 30 seconds; a
missed escalation on a harassment question has legal consequences. Run the
eval's escalation-recall metric on every dataset update to catch regressions.

**Feedback loop for accepted-but-wrong answers**
Escalations are captured (the ticket store records every failure). But an answer
the employee accepted that was *wrong* is invisible — no ticket, no signal.
*Mitigations:* the UI has a "send to HR instead" button after every answer
(thumbs-down path). In production, thumbs-down routes to an HR review queue,
not just a ticket. HR resolves it by either correcting the answer row or adding
a variant to improve future retrieval. This closes the loop between wrong
answers and dataset improvement without requiring engineering involvement.

**Content governance and the approval gap**
The spreadsheet model handles `status=draft/approved/deprecated`, but there is
no described workflow for who drafts, who approves, and what happens when Legal
needs to sign off before an answer goes live.
*Mitigations:* define the workflow before launch, not after. Suggested minimum:
policy owner drafts the row (status=draft), HR lead approves (status=approved),
Legal reviews any row touching benefits/leave/compliance before it goes live.
The bot only surfaces `status=approved` rows — this is enforced at load time,
not query time, so a draft row can never accidentally appear.

**Security: ticket access is unauthenticated in the prototype**
The `/tickets` endpoint returns all escalated employee questions with no access
control. In production, ticket contents may be sensitive (an employee asking
about harassment or medical leave). The prototype deliberately leaves this open
for demo purposes; in production, ticket read access must be scoped to HR roles
via the existing identity provider (Okta, Azure AD). The FastAPI layer adds
OAuth2 middleware; the ticket store swaps to ServiceNow/Jira with native RBAC.

---

## What I Deliberately Did Not Build

- **Generative / rephrasing layer.** For policy Q&A, a confidently-wrong answer
  is the worst outcome. Extractive answers (verbatim HR text) eliminate the
  hallucination surface entirely. Generative rephrasing becomes worth considering
  when eval shows canned phrasing causes real UX friction — not before.

- **Personalization / HRIS integration.** Questions like "how many vacation days
  do *I* have left" require authenticated HRIS access, PII handling, and per-
  employee data — a meaningfully different project with a compliance scope that
  would delay the MVP by months. The MVP defers this and adds a caveat ("check
  Workday for your personal balance") to any answer that touches running totals.

- **Multi-jurisdiction / conditional rules.** The dataset carries `country_scope`
  and `employee_type` columns and the bot surfaces them as caveats, but it does
  not branch logic per-employee. Getting this right requires knowing which
  jurisdiction each employee is in (HRIS integration again) and modeling the rule
  differences correctly. Scope for a funded phase 2.

---

## Prototype

The attached prototype demonstrates the four-gate retrieval core against a seeded
40-row FAQ dataset. It is explicitly not production — it is good enough to demo
the central idea in a meeting and run the eval to validate threshold choices.

```
python ui.py          # Gradio chat at localhost:7860
python eval.py        # retrieval + escalation + threshold sweep metrics
pytest -q             # offline gate tests, no model download
```

**Eval results on the 40-row seed dataset (held-out variant split):**

| Metric | Value | Note |
|---|---|---|
| Retrieval top-1 | 63% | Improves with more question variants per FAQ |
| Retrieval top-3 | 84% | Upper bound for Gate 4 to exploit |
| Escalation recall | 95% | 1 residual miss — dataset fix, not code fix |
| False-escalation rate | 58% | High at prototype scale; see below |
| Out-of-scope refusal | 100% | |

The 58% false-escalation rate is inflated by two prototype-scale factors: (a) the
seed dataset is 52% must-escalate rows, far higher than a real deployment where
repetitive safe questions dominate; (b) Gate 4's top-k ambiguity check fires
conservatively on a small corpus where score gaps between FAQs are narrow. In
production, a larger and more diverse FAQ set spreads score distributions, Gate 4
fires less often, and the false-escalation rate drops. Track it as a first-week
metric (target: under 20%) and widen TOPK_MARGIN if the seed dataset is richer.

The one residual dangerous miss (`"I want holiday next week"`) cannot be caught
by any gate without adding it as a variant to the correct escalation-required FAQ
row — that is the feedback loop: escalation ticket → HR adds the phrasing as a
variant → re-index → recall hits 100%.

See `README.md` for the path from this prototype to the managed AWS production
architecture (same contract, different internals).
