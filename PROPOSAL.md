# HR Policy FAQ Assistant — Proposal

## 1. Problem Framing

The request is intentionally broad:

> “Our HR team spends hours every week answering the same policy questions from new hires — things like vacation accrual, expense rules, benefits enrollment deadlines. Can we automate this somehow?”

I would not start by building a general-purpose HR chatbot. The core problem is repetitive policy Q&A, but the real constraints are policy correctness, ownership, employee trust, escalation, and maintenance.

My recommendation is to start with a governed HR policy answer service: a small assistant that answers only from approved HR content, cites the source, and escalates anything uncertain, sensitive, or personalized.

The goal of the MVP is not to automate HR fully. The goal is to safely reduce repeated manual answers while creating a feedback loop for improving HR knowledge content over time.

---

## 2. Assumptions

For this proposal, I assume:

* The first users are new hires, not all employees globally.
* HR already has policy answers somewhere: handbook, intranet pages, PDFs, spreadsheets, Confluence, Workday articles, or email templates.
* The initial scope is repetitive policy questions, not employee-specific questions.
* The assistant should not access live HRIS/payroll/benefits data in the MVP.
* HR remains the owner of policy content and final authority for sensitive or exceptional cases.
* Incorrect answers can create trust, compliance, or legal risk, so the system must be conservative.

---

## 3. Discovery Questions Before Building

Before choosing a tool or implementation path, I would clarify five areas.

### Volume and question types

* How many HR policy questions are received per week?
* What are the top 20–30 repeated questions?
* Are these mostly during onboarding, or continuous throughout the year?
* What percentage are general policy questions versus personalized questions?

This distinction matters. “How many vacation days do full-time employees accrue?” is a good automation candidate. “How many vacation days do I personally have left?” requires authenticated HRIS integration and should be out of scope for the MVP.

### Source of truth and governance

* Where do official policy answers live today?
* Who owns each policy?
* Who approves the answer the assistant is allowed to show?
* How often do policies change?
* Is Legal or Compliance required to approve certain answers?

The assistant is only as reliable as the content governance behind it.

### Risk and escalation

* Which topics should never be answered automatically?
* What should happen for sensitive topics such as harassment, immigration, medical leave, termination, compensation disputes, or legal questions?
* What confidence level is acceptable before the assistant answers?
* Who receives escalated questions?

### Channel and user experience

* Where do new hires ask these questions today: Slack, Teams, email, ServiceNow, Workday, intranet?
* Should the assistant live in that same channel?
* Should escalation create a ticket, send a message to HR, or route to an existing queue?

### Success criteria

* What would make this worth continuing after 4–6 weeks?
* Is the main target HR hours saved, faster response time, fewer tickets, better onboarding experience, or all of these?
* What baseline do we have today?

---

## 4. Build vs Buy Recommendation

I would not recommend building a full custom chatbot platform from scratch for the first version.

The best first approach is to assemble from managed enterprise services where possible, while keeping the design portable. If the company is AWS-first, this could use Amazon Q Business or Bedrock Knowledge Bases. If the company is Microsoft-first, the equivalent path could be Teams, Copilot Studio, Azure AI Search, and Azure OpenAI. If the company already has ServiceNow, Workday, Guru, or an internal knowledge base, those should also be evaluated first.

The key decision is not “LLM or no LLM.” The key decision is whether the system can support:

* approved source content,
* citations,
* confidence-based escalation,
* sensitive-topic routing,
* audit logs,
* HR-owned content updates,
* and measurement.

### Recommendation

Start with a lightweight custom retrieval layer or managed knowledge-base tool over a curated HR FAQ dataset. Use existing enterprise channels for the interface. Avoid full custom infrastructure unless discovery shows that the use case requires complex personalization, multi-country policy logic, or reuse across many internal knowledge domains.

### Why not pure low-code only?

A low-code FAQ or workflow tool may be enough if the content is simple and clean. However, many low-code tools become limiting when we need custom confidence gates, sensitive-topic detection, structured escalation data, evaluation, and policy-version auditability.

### Why not full custom immediately?

A full custom AI system creates unnecessary engineering and maintenance cost before proving value. The hard part is not vector search. The hard part is content ownership, correctness, adoption, and ongoing governance.

---

## 5. Smallest Valuable MVP

The smallest useful version is a “New Hire HR Policy Assistant” that answers only a curated set of approved questions.

### MVP scope

* 10–50 high-frequency new-hire FAQ entries.
* Each FAQ has an approved answer, policy source, owner, effective date, category, and sensitivity flag.
* Semantic retrieval over approved questions and variants.
* Source citation on every answer.
* Confidence thresholding.
* Sensitive-topic escalation.
* Basic audit logging.
* Feedback capture: helpful / not helpful / send to HR.
* Deployment in the channel where HR questions already arrive, such as Slack or Teams.

### Out of scope for MVP

* Live HRIS or payroll integration.
* Personalized employee-specific answers.
* Multi-country policy branching.
* Autonomous HR case resolution.
* Broad document ingestion across all HR material.
* Generative rephrasing of policy answers.

### Why this scope

The HR team’s time is likely consumed by repeated questions, not edge cases. Automating the top 10–30 questions may cover a meaningful share of volume while keeping risk low. Every escalation becomes a useful signal for which FAQ rows to improve next.

---

## 6. Technical Design

### High-level architecture

```text
[Employee / New Hire]
        |
        v
[Slack / Teams / Web UI]
        |
        v
[API Layer]
        |
        v
[Question Router]
   |          |             |
Sensitive   FAQ Match      Low Confidence
   |          |             |
   v          v             v
[HR Queue] [Approved FAQ Index] [HR Queue]
              |
              v
       [Cited Answer]
              |
              v
[Audit Log + Feedback + Analytics]
```

### Main components

**User interface**

The assistant should be available where questions already arrive: Slack, Teams, or an existing HR portal. I would avoid creating a new destination unless necessary.

**FAQ knowledge base**

The MVP can start with a spreadsheet or simple CMS containing:

* FAQ ID,
* canonical question,
* question variants,
* approved answer,
* category,
* source document,
* section reference,
* effective date,
* policy owner,
* sensitivity flag,
* approval status.

Only approved rows should be indexed.

**Retrieval layer**

For the prototype, sentence-transformers/all-MiniLM-L6-v2 is sufficient. It is lightweight, fast, local, and good enough for semantic FAQ retrieval.

The retrieval layer should return top-k matches, not only the top-1 result. This allows the system to detect ambiguity and avoid answering when multiple FAQ entries are too close.

**Answer decision layer**

The assistant should not answer simply because a match was found. It should apply explicit gates.

```text
Gate 1: Is the query sensitive?
        If yes, escalate.

Gate 2: Is there an approved FAQ match?
        If no, escalate.

Gate 3: Is confidence above threshold?
        If no, escalate.

Gate 4: Are top-k results ambiguous?
        If yes, ask a clarification question or escalate.

Gate 5: Is the answer personalized or employee-specific?
        If yes, route to HRIS or HR, not the FAQ assistant.
```

**Answer builder**

For MVP, I would return approved answer text with minimal formatting. I would not use an LLM to freely rewrite HR policy in v1.

Answer format:

```text
Short answer:
[Approved answer]

Source:
[Policy name, section, effective date]

Contact HR if:
[Exception or escalation guidance]
```

**Context strategy**

The MVP should maintain only short-lived session context for follow-up questions. For example, if the user asks “What if I miss it?” after a benefits-enrollment answer, the assistant can interpret “it” as the enrollment deadline.

It should not store long-term employee memory. Conversation context helps interpret the question, but the answer must always come from approved HR content.

**Audit and analytics**

Each interaction should log:

* timestamp,
* user question,
* matched FAQ ID,
* confidence score,
* top-k candidates,
* answer returned or escalated,
* escalation reason,
* source policy version,
* feedback signal.

This is important for debugging, compliance review, and improving coverage.

---

## 7. Rollout Plan

I would not launch directly to all employees.

### Phase 1: Shadow mode

The assistant runs silently alongside HR. It logs what it would have answered, but employees do not see the answer. HR reviews the output daily.

Goal:

* validate thresholds,
* find missing FAQ entries,
* identify sensitive-topic misses,
* tune escalation behavior before real use.

### Phase 2: Opt-in pilot

The assistant is made available in a dedicated Slack or Teams channel for new hires. HR monitors usage and reviews feedback.

Goal:

* test adoption,
* measure answer helpfulness,
* confirm escalation quality,
* build trust with HR.

### Phase 3: Default entry point

If quality is acceptable, the assistant becomes the first line for common new-hire policy questions. HR remains responsible for escalations and policy updates.

---

## 8. Measuring Success

I would measure success across adoption, effectiveness, and risk.

### Adoption metrics

* Number of questions asked per week.
* Percentage of new hires using the assistant.
* Repeat usage rate.
* Most common question categories.

### Effectiveness metrics

* Deflection rate: percentage of questions answered without HR involvement.
* Reduction in HR tickets or direct messages.
* Estimated HR hours saved.
* Average response time.
* Helpful / not helpful feedback rate.

### Quality and risk metrics

* HR-reviewed answer correctness.
* Escalation recall for sensitive questions.
* Low-confidence rate.
* Out-of-scope refusal accuracy.
* Wrong-answer rate.
* Stale-policy incidents.

I would not optimize answer rate alone. A bot that answers 95% of questions but gives risky or incorrect answers is worse than a bot that answers 60% correctly and escalates the rest.

### MVP success criteria

After 4–6 weeks, I would consider the MVP successful if:

* it deflects a meaningful share of repetitive questions,
* HR approves at least 80–90% of sampled answers,
* sensitive-topic escalation has near-zero misses,
* HR spends less time answering repetitive questions,
* and the feedback loop identifies clear FAQ improvements.

---

## 9. Main Risks and Mitigations

### Wrong policy answers

This is the highest-risk failure. HR policy errors can create employee trust, compliance, legal, or financial problems.

Mitigation:

* answer only from approved content,
* include citations,
* use confidence thresholds,
* escalate sensitive or uncertain questions,
* review sampled answers with HR.

### Content drift

Policies change. A correct answer today may become wrong later.

Mitigation:

* assign policy owners,
* include effective dates and review dates,
* support draft / approved / deprecated status,
* re-index automatically after approved updates,
* send weekly stale-content or missing-content reports to HR.

### Low adoption

If employees keep asking HR directly, the system does not reduce workload.

Mitigation:

* deploy in the existing HR question channel,
* keep answers short and cited,
* make escalation easy,
* share deflection and quality metrics with HR.

### Sensitive-topic misses

A sensitive question may retrieve a non-sensitive FAQ row and get answered incorrectly.

Mitigation:

* use both FAQ-level sensitivity flags and query-text sensitive keyword detection,
* tune the sensitive-topic list conservatively,
* test escalation recall on every dataset update.

### Maintenance burden

If HR cannot update the dataset easily, the assistant will become stale.

Mitigation:

* start with a spreadsheet or simple CMS,
* make HR the content owner,
* index only approved rows,
* generate a weekly gap digest of unanswered questions.

### Privacy and access control

Employee questions may contain sensitive personal information.

Mitigation:

* avoid long-term memory in MVP,
* minimize stored data,
* restrict ticket and audit-log access to HR roles,
* integrate with SSO/RBAC in production,
* define retention rules before launch.

---

## 10. What I Deliberately Did Not Build

* I did not build live HRIS, payroll, or benefits integration. Employee-specific questions require authentication, PII handling, and stronger access controls. That is a separate phase.
* I did not build a general HR chatbot for every policy and country. Multi-jurisdiction logic increases risk and slows validation.
* I did not add a generative rephrasing layer. For HR policy Q&A, returning approved answers is safer than generating fluent but potentially inaccurate wording.
* I did not build a full admin workflow. For the MVP, a spreadsheet or simple CMS is enough to validate value before investing in content-management tooling.

---

## 11. Prototype Summary

The prototype demonstrates the core behavior only:

* Seeded HR FAQ dataset.
* Semantic retrieval using sentence-transformers/all-MiniLM-L6-v2.
* Top-k matching.
* Confidence thresholding.
* Sensitive-topic escalation.
* Source citation.
* Basic audit logging.
* Evaluation questions for retrieval and escalation behavior.

It is explicitly not production-ready. Its purpose is to show the central idea: answer approved repetitive questions, refuse or escalate uncertain/sensitive questions, and capture signals that help HR improve the knowledge base.

Example commands:

```text
python ui.py
python eval.py
pytest -q
```

The production version would replace local files and local embeddings with managed identity, managed search or knowledge-base services, HR-owned content workflows, RBAC, monitoring, and integration with the company’s preferred HR ticketing system.
