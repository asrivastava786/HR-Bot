"""Load the HR FAQ dataset (xlsx) into clean records.

Governance is enforced here: only `status == Approved` rows are loaded, so the
bot can never surface draft or deprecated policy. Each column maps to a role:
  canonical_question + variants  -> retrieval keys (what we embed)
  approved_answer                -> the grounded answer text (extractive)
  source_* + effective_date      -> citation + freshness
  escalation_required/sensitive  -> Gate 2 (safety override)
  country_scope/employee_type    -> answer caveats
"""

import os
import pandas as pd

DATA_PATH = os.getenv(
    "FAQ_DATA",
    os.path.join(os.path.dirname(__file__), "data", "hr_policy_faq_dataset.xlsx"),
)


def _variants(cell):
    if not isinstance(cell, str):
        return []
    return [v.strip() for v in cell.split("|") if v.strip()]


def _text(v):
    return v.strip() if isinstance(v, str) else ""


def load_faqs(path=DATA_PATH):
    df = pd.read_excel(path, sheet_name="FAQ_Dataset")
    df = df[df["status"].astype(str).str.lower() == "approved"]

    faqs = []
    for _, r in df.iterrows():
        faqs.append({
            "faq_id": r["faq_id"],
            "category": r["category"],
            "intent": r["intent"],
            "canonical_question": r["canonical_question"],
            "variants": _variants(r["question_variants"]),
            "answer": r["approved_answer"],
            "source": f'{_text(r["source_title"])} {_text(r["source_section"])}'.strip(),
            "effective_date": str(r["effective_date"])[:10],
            "country_scope": _text(r["country_scope"]) or "General",
            "employee_type": _text(r["employee_type"]) or "All employees",
            "sensitive": bool(r["sensitive_topic"]),
            "escalate": bool(r["escalation_required"]),
            "escalation_reason": _text(r["escalation_reason"]),
            "policy_owner": _text(r["policy_owner"]),
        })
    return faqs


def index_phrases(faqs, variant_filter=None):
    """Build the list of phrases to embed: canonical_question + variants, each
    tagged with its faq_id. `variant_filter(faq_id, i)` -> bool lets the eval
    hold out specific variants from the index (train/test split)."""
    phrases = []
    for f in faqs:
        phrases.append({"text": f["canonical_question"], "faq_id": f["faq_id"]})
        for i, v in enumerate(f["variants"]):
            if variant_filter is None or variant_filter(f["faq_id"], i):
                phrases.append({"text": v, "faq_id": f["faq_id"]})
    return phrases


if __name__ == "__main__":
    faqs = load_faqs()
    print(f"Loaded {len(faqs)} approved FAQs")
    print(f"Total index phrases: {len(index_phrases(faqs))}")
    print(f"Escalation-required: {sum(f['escalate'] for f in faqs)}")
