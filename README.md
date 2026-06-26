
# HR Policy FAQ Bot — prototype

<img src="live-badge.svg" alt="Live"/> **[Try the live demo →](https://huggingface.co/spaces/Ads786/hr-faq-bot)**

A runnable prototype of the proposal's core: a **retrieval-grounded FAQ bot** that
answers new-hire policy questions, **cites its source**, **escalates to a human**
when it's unsure *or* when the topic is sensitive, and lets the user **raise an HR
ticket** from any escalation.

> **Prototype, not production.** This local OSS version exists so the idea can be
> cloned, run, and demoed in minutes. See "Path to production" for how these
> components map to managed enterprise services.

## The core idea: four independent gates

| | Trigger | Behaviour |
|---|---|---|
| **Gate 1 — confidence** | best match below `FAQ_THRESHOLD` | "I'm not sure" → offer HR ticket |
| **Gate 2 — policy/safety** | matched row is `escalation_required` | route to a human **even on a confident match** |
| **Gate 3 — query keywords** | question text contains a sensitive term | escalate regardless of what was retrieved |
| **Gate 4 — top-k ambiguity** | a runner-up in top-3 is sensitive and scores close to top-1 | escalate when the bot is choosing between safe and sensitive |

Gate 2 is **data-driven**: HR owns the sensitivity boundary via the dataset, not the
model. Gates 3 and 4 close the blind spot where a sensitive question retrieves
confidently to the *wrong* non-sensitive row, bypassing Gate 2.
Answers are **extractive** (HR-approved text, verbatim) so the bot cannot
hallucinate a policy.

## Run it

```bash
pip install -r requirements.txt

python ui.py                  # chat UI + ticket form  -> http://localhost:7860
# or the API:
uvicorn app:app --reload
curl -s localhost:8000/ask -H 'content-type: application/json' \
     -d '{"question":"how does vacation accrue?"}' | python -m json.tool
```

First run downloads the ~80MB embedding model (all-MiniLM-L6-v2) once.

Try in the UI: a normal question (answers + cites), "How do I report harassment?"
(sensitive → escalates), "What's the wifi password?" (out of scope → low confidence).
Each escalation opens a pre-filled HR ticket.

## Evaluate it

```bash
python eval.py
```

Uses the dataset as ground truth with a **train/test split on variants** (index
canonical + even variants, test on held-out odd variants). Reports retrieval
top-1/top-3, an escalation confusion matrix (protecting against the severe failure —
answering a must-escalate question), out-of-scope refusal, and a **threshold sweep**
(answer-rate vs wrong-answers). Because the bot is extractive, retrieval-correct ==
answer-correct; that equivalence would break if a generative layer were added.

## Test it

```bash
pytest -q          # offline: stub embedder, no model download, no network
```

## Tuning the knobs

`FAQ_THRESHOLD` (default `0.45`) — Gate 1 knob: too low → answers near-misses
(confidently wrong); too high → over-escalates.

`FAQ_TOPK_MARGIN` (default `0.15`) — Gate 4 knob: how close a sensitive runner-up
must be to top-1 to trigger ambiguity escalation.

`SENSITIVE_KEYWORDS` — Gate 3 knob: comma-separated list HR can extend without a
deploy (e.g. `SENSITIVE_KEYWORDS=harass,fmla,relocation,cobra`).

Use the eval's threshold sweep to find the setting matching HR's risk tolerance.
Never optimise answer-rate alone.

## Path to production

Same contract, managed internals:

| Prototype | Production |
|---|---|
| `data/*.xlsx` + loader | Handbook chunked into a managed knowledge base; `status`-gated |
| sentence-transformers + Chroma | Managed embeddings + vector search (cloud provider of choice) |
| Extractive passage | Generative rephrasing *from* retrieved passage + groundedness check |
| SQLite tickets | ServiceNow / Jira / email + dedup |
| Gradio / FastAPI | Slack / Teams bot fronting the same API |

## Files

```
data_loader.py   load xlsx (approved-only), parse variants, build index phrases
retriever.py     embed variants -> retrieve -> 4 gates -> extract + cite  (injectable embedder)
tickets.py       SQLite ticket store (stub for ServiceNow/Jira/email)
app.py           FastAPI: /ask, /ticket, /tickets
ui.py            Gradio chat + conditional HR-ticket form
eval.py          held-out split; retrieval / escalation / refusal / threshold sweep
tests/           offline tests, 7 cases covering all four gates (stub embedder, no download)
PROPOSAL.md      written proposal: discovery questions, build/buy rec, MVP, metrics, risks
```
