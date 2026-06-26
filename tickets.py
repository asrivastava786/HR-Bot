"""Ticket store — the 'route to a human' backend.

PROTOTYPE ONLY: writes to a local SQLite file. In production this same payload
becomes a ServiceNow / Jira / Zendesk ticket or an email to HR -- one swap, same
fields. The payload is deliberately signal-rich: it captures WHY the bot
escalated and its best failed guess, so HR can tell "bad phrasing the bot should
have caught" from "genuinely uncovered policy" -- which is how the dataset
improves over time.
"""

import os
import sqlite3
import datetime

DB = os.getenv("TICKET_DB", os.path.join(os.path.dirname(__file__), "tickets.db"))

_VALID_TRIGGERS = {"low_confidence", "policy_escalation", "user_rejected"}


def _conn():
    c = sqlite3.connect(DB)
    c.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            question TEXT NOT NULL,
            trigger_reason TEXT NOT NULL,
            best_guess_faq TEXT,
            best_guess_score REAL,
            status TEXT NOT NULL DEFAULT 'open'
        )""")
    return c


def create_ticket(question, trigger_reason, best_guess_faq=None,
                  best_guess_score=None):
    if trigger_reason not in _VALID_TRIGGERS:
        trigger_reason = "low_confidence"
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    c = _conn()
    cur = c.execute(
        "INSERT INTO tickets (created_at, question, trigger_reason, "
        "best_guess_faq, best_guess_score, status) VALUES (?,?,?,?,?,?)",
        (ts, question, trigger_reason, best_guess_faq, best_guess_score, "open"))
    c.commit()
    tid = cur.lastrowid
    c.close()
    return {"ticket_id": tid, "created_at": ts, "status": "open",
            "trigger_reason": trigger_reason}


def list_tickets():
    c = _conn()
    rows = c.execute(
        "SELECT id, created_at, question, trigger_reason, best_guess_faq, "
        "best_guess_score, status FROM tickets ORDER BY id DESC").fetchall()
    c.close()
    cols = ["id", "created_at", "question", "trigger_reason",
            "best_guess_faq", "best_guess_score", "status"]
    return [dict(zip(cols, r)) for r in rows]
