"""Retrieval-grounded FAQ logic with FOUR independent gates.

  Gate 1 (confidence):    best similarity < threshold  -> escalate ("don't know")
  Gate 2 (policy):        matched row is escalation_required -> escalate
                          EVEN on a confident match (e.g. harassment, immigration)
  Gate 3 (query text):    query contains a known sensitive keyword -> escalate
                          regardless of what was retrieved
  Gate 4 (top-k ambiguity): any of top-3 results is escalation_required AND
                          its score is within TOPK_MARGIN of top-1 -> escalate
                          (catches: sensitive question retrieves confidently to
                          the WRONG non-sensitive row, but the correct sensitive
                          row still appears in top-3)

Gates 2+3 cover known-sensitive topics. Gate 4 covers the residual blind spot:
a query ambiguous between a safe FAQ and a sensitive one, where the bot "chose
wrong" but the sensitive FAQ is still a plausible match. Conservative by design:
a false escalation costs 30 seconds; a missed sensitive escalation has legal cost.

Answers are extractive (the HR-approved text, verbatim) so the bot cannot
hallucinate a policy. The embedder is injectable so the logic is testable
offline; by default it uses sentence-transformers (all-MiniLM-L6-v2).
"""

import os
import re
import chromadb

from data_loader import load_faqs, index_phrases

MODEL_NAME = "all-MiniLM-L6-v2"
THRESHOLD = float(os.getenv("FAQ_THRESHOLD", "0.45"))
# If any top-3 result is escalation_required and within this margin of top-1,
# treat the query as ambiguous and escalate. Tunable via env var.
TOPK_MARGIN = float(os.getenv("FAQ_TOPK_MARGIN", "0.15"))

_DEFAULT_SENSITIVE_KEYWORDS = (
    "harass,discriminat,terminat,fired,laid off,layoff,fmla,immigration,visa,"
    "leave of absence,medical leave,disability,accommodation,complaint,grievance,"
    "investigation,whistleblow,retaliat,cobra,severance,wrongful,relocation"
)
_SENSITIVE_RE = re.compile(
    "|".join(re.escape(k.strip()) for k in
             os.getenv("SENSITIVE_KEYWORDS", _DEFAULT_SENSITIVE_KEYWORDS).split(",")),
    re.IGNORECASE,
)

ESCALATION_MSG = {
    "low_confidence":    "I'm not confident I have the right answer for that one.",
    "policy_escalation": "This needs a person from HR -- it's a topic I shouldn't answer directly.",
    "query_sensitive":   "This needs a person from HR -- it's a topic I shouldn't answer directly.",
    "topk_ambiguity":    "This needs a person from HR -- it's a topic I shouldn't answer directly.",
}


class Retriever:
    def __init__(self, faqs=None, embed_fn=None, threshold=THRESHOLD,
                 phrases=None, persist_dir=None):
        self.faqs = faqs if faqs is not None else load_faqs()
        self.by_id = {f["faq_id"]: f for f in self.faqs}
        self.threshold = threshold
        self._embed_fn = embed_fn
        self._model = None

        self.client = (chromadb.PersistentClient(path=persist_dir)
                       if persist_dir else chromadb.EphemeralClient())
        try:
            self.client.delete_collection("hr_faq")
        except Exception:
            pass
        self.collection = self.client.create_collection(
            name="hr_faq", metadata={"hnsw:space": "cosine"})
        self._index(phrases if phrases is not None else index_phrases(self.faqs))

    def embed(self, texts):
        if self._embed_fn is not None:
            return self._embed_fn(texts)
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(MODEL_NAME)
        return self._model.encode(texts, normalize_embeddings=True).tolist()

    def _index(self, phrases):
        self.collection.add(
            ids=[f'p{i}' for i in range(len(phrases))],
            embeddings=self.embed([p["text"] for p in phrases]),
            metadatas=[{"faq_id": p["faq_id"]} for p in phrases],
        )

    def _caveat(self, faq):
        notes = []
        if faq["country_scope"] != "General":
            notes.append("specifics depend on your country/location")
        if faq["employee_type"] not in ("All employees", "General", ""):
            notes.append(f'this applies to: {faq["employee_type"].lower()}')
        return ("Note: " + "; ".join(notes) + ".") if notes else None

    def topk(self, question, k=3):
        res = self.collection.query(query_embeddings=self.embed([question]),
                                    n_results=k)
        return [(m["faq_id"], round(1.0 - d, 3))
                for m, d in zip(res["metadatas"][0], res["distances"][0])]

    def ask(self, question):
        res = self.collection.query(query_embeddings=self.embed([question]),
                                    n_results=3)
        if not res["ids"] or not res["ids"][0]:
            return {"action": "escalate", "reason": "low_confidence",
                    "score": 0.0, "message": ESCALATION_MSG["low_confidence"],
                    "best_guess_faq": None}

        top = [(res["metadatas"][0][i]["faq_id"],
                round(1.0 - res["distances"][0][i], 3))
               for i in range(len(res["ids"][0]))]

        faq_id, score = top[0]
        faq = self.by_id[faq_id]

        # Gate 1 -- confidence
        if score < self.threshold:
            return {"action": "escalate", "reason": "low_confidence",
                    "score": score, "message": ESCALATION_MSG["low_confidence"],
                    "best_guess_faq": faq_id}

        # Gate 2 -- policy/safety override (fires even on a confident match)
        if faq["escalate"]:
            return {"action": "escalate", "reason": "policy_escalation",
                    "score": score, "message": ESCALATION_MSG["policy_escalation"],
                    "escalation_reason": faq["escalation_reason"],
                    "best_guess_faq": faq_id}

        # Gate 3 -- query-text keyword guard
        if _SENSITIVE_RE.search(question):
            return {"action": "escalate", "reason": "query_sensitive",
                    "score": score, "message": ESCALATION_MSG["query_sensitive"],
                    "best_guess_faq": faq_id}

        # Gate 4 -- top-k ambiguity: if any runner-up is escalation_required
        # and scores within TOPK_MARGIN of top-1, the query is ambiguous between
        # a safe answer and a sensitive topic -- escalate rather than guess.
        for alt_id, alt_score in top[1:]:
            if self.by_id[alt_id]["escalate"] and (score - alt_score) <= TOPK_MARGIN:
                return {"action": "escalate", "reason": "topk_ambiguity",
                        "score": score, "message": ESCALATION_MSG["topk_ambiguity"],
                        "best_guess_faq": faq_id}

        # Answer
        return {"action": "answer", "score": score, "faq_id": faq_id,
                "answer": faq["answer"],
                "citation": f'{faq["source"]} (updated {faq["effective_date"]})',
                "caveat": self._caveat(faq)}
