"""Evaluation harness.

Uses the dataset as its own ground truth, with a TRAIN/TEST split on variants so
retrieval numbers reflect generalization to unseen phrasings, not memorization.

  Split:   index canonical_question + even-indexed variants;
           hold out odd-indexed variants as the test set.

  Metrics:
    1. Retrieval top-1 / top-3   (answerable held-out queries)
    2. Decision confusion matrix (answer vs escalate) + escalation recall
       and false-escalation rate -- protecting against the severe failure:
       answering something that should have escalated.
    3. Out-of-scope refusal rate (crafted off-topic queries -> must escalate)
    4. Threshold sweep: answer-rate vs wrong-answer-rate across thresholds.

  Note: because the bot is extractive, retrieval-correct == answer-correct.
  That equivalence breaks the moment a generative layer is added; then a
  groundedness/faithfulness check would be required here too.

    python eval.py
"""

from data_loader import load_faqs, index_phrases
from retriever import Retriever, TOPK_MARGIN, _SENSITIVE_RE

OUT_OF_SCOPE = [
    "What's the office wifi password?",
    "Can I bring my dog to the office?",
    "Who won the football match last night?",
    "What's the best lunch place near the office?",
]


def _train_filter(faq_id, i):
    return i % 2 == 0  # index even-indexed variants only


def _collect(embed_fn=None):
    """One pass: for every test query, record matched faq_id + score (no gating),
    so thresholds can be swept analytically without re-embedding."""
    faqs = load_faqs()
    by_id = {f["faq_id"]: f for f in faqs}
    phrases = index_phrases(faqs, variant_filter=_train_filter)

    # threshold=0 so Gate 1 never fires; we read raw match + score.
    r = Retriever(faqs=faqs, embed_fn=embed_fn, threshold=0.0, phrases=phrases)

    rows = []  # (query, true_id, should_escalate, top3, top1_id, top1_score)
    for f in faqs:
        for i, v in enumerate(f["variants"]):
            if i % 2 == 1:  # held-out
                top3 = r.topk(v, 3)
                rows.append((v, f["faq_id"], f["escalate"], top3,
                             top3[0][0], top3[0][1]))
    oos = [(q, None, True, r.topk(q, 3), r.topk(q, 1)[0][0], r.topk(q, 1)[0][1])
           for q in OUT_OF_SCOPE]
    return by_id, rows, oos


def _decide(query, should_escalate_match, score, top3, by_id, threshold):
    """Reproduce the four-gate decision analytically."""
    # Gate 1 -- confidence
    if score < threshold:
        return "escalate"
    # Gate 2 -- matched row is escalation_required
    if should_escalate_match:
        return "escalate"
    # Gate 3 -- query text contains sensitive keyword
    if _SENSITIVE_RE.search(query):
        return "escalate"
    # Gate 4 -- any runner-up is escalation_required within TOPK_MARGIN
    for alt_id, alt_score in top3[1:]:
        if by_id[alt_id]["escalate"] and (score - alt_score) <= TOPK_MARGIN:
            return "escalate"
    return "answer"


def run(embed_fn=None, default_threshold=0.45,
        sweep=(0.30, 0.35, 0.40, 0.45, 0.50, 0.55)):
    by_id, rows, oos = _collect(embed_fn)

    answerable = [r for r in rows if not r[2]]
    must_escalate = [r for r in rows if r[2]]

    print(f"\nTEST SET: {len(rows)} held-out variants "
          f"({len(answerable)} answerable, {len(must_escalate)} must-escalate) "
          f"+ {len(oos)} out-of-scope\n")

    # 1. Retrieval (answerable only)
    top1 = sum(r[4] == r[1] for r in answerable)
    top3 = sum(r[1] in [x[0] for x in r[3]] for r in answerable)
    n = max(len(answerable), 1)
    print("1) RETRIEVAL (answerable held-out)")
    print(f"   top-1 accuracy : {top1}/{len(answerable)} = {top1/n:.0%}")
    print(f"   top-3 accuracy : {top3}/{len(answerable)} = {top3/n:.0%}\n")

    # 2. Decision confusion matrix at default threshold
    tp = fn = fp = tn = 0
    danger = []
    for q, true_id, should_esc, top3l, m_id, score in rows:
        m_esc = by_id[m_id]["escalate"]
        action = _decide(q, m_esc, score, top3l, by_id, default_threshold)
        if should_esc and action == "escalate":
            tp += 1
        elif should_esc and action == "answer":
            fn += 1
            danger.append((q, m_id, score))
        elif not should_esc and action == "escalate":
            fp += 1
        else:
            tn += 1
    recall = tp / max(tp + fn, 1)
    far = fp / max(fp + tn, 1)
    print(f"2) DECISION (threshold = {default_threshold}, topk_margin = {TOPK_MARGIN})")
    print(f"   escalation recall      : {tp}/{tp+fn} = {recall:.0%}  "
          f"(want 100% -- never answer a must-escalate question)")
    print(f"   false-escalation rate  : {fp}/{fp+tn} = {far:.0%}  "
          f"(answerable that got needlessly escalated)")
    if danger:
        print("   !! DANGEROUS (answered when it should have escalated):")
        for q, m, s in danger:
            print(f"      - '{q}' -> {m} @ {s}")
    else:
        print("   (no dangerous misses)")
    print()

    # 3. Out-of-scope refusal
    refused = sum(
        _decide(r[0], by_id[r[4]]["escalate"], r[5], r[3], by_id, default_threshold)
        == "escalate" for r in oos)
    print("3) OUT-OF-SCOPE REFUSAL")
    print(f"   refused/escalated : {refused}/{len(oos)} = {refused/len(oos):.0%}\n")

    # 4. Threshold sweep
    print("4) THRESHOLD SWEEP")
    print(f"   {'thr':>5} {'answer%':>8} {'wrong-answers':>14} {'esc-recall':>11}")
    for thr in sweep:
        answered = wrong = etp = efn = 0
        for q, true_id, should_esc, top3l, m_id, score in rows:
            action = _decide(q, by_id[m_id]["escalate"], score, top3l, by_id, thr)
            if action == "answer":
                answered += 1
                if should_esc or m_id != true_id:
                    wrong += 1
            if should_esc:
                etp += action == "escalate"
                efn += action == "answer"
        rate = answered / len(rows)
        er = etp / max(etp + efn, 1)
        print(f"   {thr:>5.2f} {rate:>7.0%} {wrong:>14} {er:>10.0%}")
    print("\n   (wrong-answers includes any must-escalate row that got answered.)")


if __name__ == "__main__":
    run()
