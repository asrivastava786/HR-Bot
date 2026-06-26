"""FastAPI service.

    uvicorn app:app --reload
    POST /ask     {"question": "..."}                  -> answer or escalate
    POST /ticket  {"question","trigger_reason",...}     -> create HR ticket
    GET  /tickets                                       -> list tickets
"""

from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional

from retriever import Retriever
import tickets

app = FastAPI(title="HR FAQ Bot (prototype)")
retriever = Retriever()


class Query(BaseModel):
    question: str


class Ticket(BaseModel):
    question: str
    trigger_reason: str
    best_guess_faq: Optional[str] = None
    best_guess_score: Optional[float] = None


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/ask")
def ask(q: Query):
    return retriever.ask(q.question)


@app.post("/ticket")
def ticket(t: Ticket):
    return tickets.create_ticket(t.question, t.trigger_reason,
                                 t.best_guess_faq, t.best_guess_score)


@app.get("/tickets")
def all_tickets():
    return tickets.list_tickets()
