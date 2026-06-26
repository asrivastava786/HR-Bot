"""Gradio demo UI:  python ui.py  ->  http://localhost:7860

Chat with grounded answers + citations. When the bot escalates (low confidence
or a sensitive topic) a pre-filled HR ticket form appears. After any answer, a
"Send this to HR instead" button lets the user escalate manually.
"""

import gradio as gr

from retriever import Retriever
import tickets

# Gradio 5.x requires type="messages" explicitly; 6.x removed the parameter
# (messages became the default). Detect at runtime so the same code runs both
# locally (6.x) and on HF Spaces (5.x).
_GR_MAJOR = int(gr.__version__.split(".")[0])
_CHATBOT_KWARGS = {"height": 380, **({"type": "messages"} if _GR_MAJOR < 6 else {})}

retriever = Retriever()

REASON_LABEL = {
    "low_confidence": "Low confidence -- the bot wasn't sure it had the right answer",
    "policy_escalation": "Sensitive topic -- this must be handled by a person in HR",
    "user_rejected": "The answer wasn't helpful",
}


def _format(out):
    if out["action"] == "answer":
        txt = out["answer"]
        if out.get("caveat"):
            txt += f"\n\n_{out['caveat']}_"
        return txt + f"\n\n-- {out['citation']} - confidence {out['score']}"
    txt = out["message"]
    if out.get("escalation_reason"):
        txt += f"\n\n_Why: {out['escalation_reason']}_"
    return txt


def on_ask(question, history):
    if not question.strip():
        return history, "", {}, gr.update(), gr.update(), gr.update()
    out = retriever.ask(question)
    history = history + [
        {"role": "user", "content": question},
        {"role": "assistant", "content": _format(out)},
    ]
    last = {
        "question": question,
        "trigger_reason": out.get("reason", "user_rejected"),
        "best_guess_faq": out.get("best_guess_faq") or out.get("faq_id"),
        "best_guess_score": out.get("score"),
    }
    if out["action"] == "escalate":  # auto-open pre-filled ticket
        return (history, "", last, gr.update(visible=True),
                gr.update(value=question),
                gr.update(value=REASON_LABEL.get(last["trigger_reason"],
                                                 last["trigger_reason"])))
    return history, "", last, gr.update(visible=False), gr.update(), gr.update()


def open_ticket(last):
    last = last or {}
    return (gr.update(visible=True),
            gr.update(value=last.get("question", "")),
            gr.update(value=REASON_LABEL.get(last.get("trigger_reason"),
                                             last.get("trigger_reason", ""))))


def submit_ticket(question, last):
    last = last or {}
    res = tickets.create_ticket(
        question or last.get("question", ""),
        last.get("trigger_reason", "user_rejected"),
        last.get("best_guess_faq"),
        last.get("best_guess_score"))
    return (gr.update(visible=False),
            f"Ticket #{res['ticket_id']} created and routed to HR "
            f"({res['trigger_reason']}).")


with gr.Blocks(title="HR Policy FAQ (prototype)") as demo:
    gr.Markdown("## HR Policy FAQ -- prototype\n"
                "Grounded answers with citations. Low-confidence or sensitive "
                "questions route to HR via a ticket.")
    last = gr.State({})
    chat = gr.Chatbot(**_CHATBOT_KWARGS)
    with gr.Row():
        box = gr.Textbox(placeholder="Ask a policy question...", scale=8,
                         show_label=False)
        send = gr.Button("Send", scale=1, variant="primary")
    not_helpful = gr.Button("Send this to HR instead", size="sm")

    with gr.Group(visible=False) as ticket_panel:
        gr.Markdown("### Escalate to HR")
        t_question = gr.Textbox(label="Your question")
        t_reason = gr.Textbox(label="Reason", interactive=False)
        t_submit = gr.Button("Create ticket", variant="primary")
    confirm = gr.Markdown("")

    gr.Examples(
        ["How does vacation accrue?",
         "How do I report harassment?",        # sensitive -> escalate
         "Can I expense a client dinner?",
         "What's the office wifi password?"],   # out of scope -> low confidence
        inputs=box)

    outputs = [chat, box, last, ticket_panel, t_question, t_reason]
    send.click(on_ask, [box, chat], outputs)
    box.submit(on_ask, [box, chat], outputs)
    not_helpful.click(open_ticket, [last], [ticket_panel, t_question, t_reason])
    t_submit.click(submit_ticket, [t_question, last], [ticket_panel, confirm])

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0")
