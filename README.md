# HR Policy FAQ Bot — prototype

A runnable prototype of the proposal's core: a **retrieval-grounded FAQ bot** that
answers new-hire policy questions, **cites its source**, **escalates to a human**
when it's unsure *or* when the topic is sensitive, and lets the user **raise an HR
ticket** from any escalation.

> **Prototype, not production.** The production recommendation is the AWS-managed
> path (Amazon Q Business / Bedrock Knowledge Bases). This local OSS version exists
> so the idea can be cloned, run, and demoed in minutes. See "Path to production".

## The core idea: two independent gates

| | Trigger | Behaviour |
|---|---|---|
| **Gate 1 — confidence** | best match below `FAQ_THRESHOLD` | "I'm not sure" → offer HR ticket |
| **Gate 2 — policy/safety** | matched row is `escalation_required` | route to a human **even on a confident match** |

Gate 2 is **data-driven**: HR owns the sensitivity boundary via the dataset, not the
model. Answers are **extractive** (HR-approved text, verbatim) so the bot cannot
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

## Tuning the threshold

`FAQ_THRESHOLD` (default 0.45) is the main knob: too low → answers near-misses
(confidently wrong); too high → over-escalates. Use the eval's threshold sweep to
pick the point matching HR's risk tolerance; never optimise answer-rate alone.

## Path to production

Same contract, managed internals:

| Prototype | Production (AWS-managed) |
|---|---|
| `data/*.xlsx` + loader | Handbook chunked into S3; `status`-gated |
| sentence-transformers + Chroma | Bedrock Knowledge Bases (embeddings + OpenSearch) |
| Extractive passage | Bedrock model phrasing *from* the retrieved passage + groundedness check |
| SQLite tickets | ServiceNow / Jira / email + dedup |
| Gradio / FastAPI | Lambda fronting Slack / Teams |

## Files

```
data_loader.py   load xlsx (approved-only), parse variants, build index phrases
retriever.py     embed variants -> retrieve -> 4 gates -> extract + cite  (injectable embedder)
tickets.py       SQLite ticket store (stub for ServiceNow/Jira/email)
app.py           FastAPI: /ask, /ticket, /tickets
ui.py            Gradio chat + conditional HR-ticket form
eval.py          held-out split; retrieval / escalation / refusal / threshold sweep
tests/           offline tests (stub embedder)
DECISIONS.md     why each load-bearing choice, and what was deliberately not built
```
