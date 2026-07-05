"""XpertFinder Slack bot — Socket Mode (no public URL / ngrok needed).
  /xpert <question>  -> Gemini ranks seeded experts -> replies with the best reachable one
  [Connect me]       -> opens a direct DM with that expert, cutting the manager relay.
"""
import os
import re
import json
import subprocess
from pathlib import Path

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from ranker import rank_experts
from gemini_client import call_gemini, generate_text

ROOT = Path(__file__).parent


def load_env(path):
    """Tiny .env loader so we don't need python-dotenv."""
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


load_env(ROOT / ".env")

people = json.loads((ROOT / "data" / "people.json").read_text())
docs = json.loads((ROOT / "data" / "docs.json").read_text())
MODEL = os.environ.get("MODEL", "gemini-2.5-flash")
GBRAIN_BIN = os.environ.get("GBRAIN_BIN", os.path.expanduser("~/.bun/bin/gbrain"))
USE_GBRAIN = os.environ.get("USE_GBRAIN", "").lower() in ("1", "true", "yes")
TONE_EMOJI = {"success": ":large_green_circle:", "warning": ":large_yellow_circle:", "danger": ":red_circle:"}

app = App(token=os.environ["SLACK_BOT_TOKEN"])


_STOP = {"i", "the", "a", "an", "to", "of", "for", "and", "or", "how", "do", "does",
         "we", "our", "us", "who", "what", "is", "are", "with", "in", "on", "at", "can",
         "me", "my", "need", "help", "want", "please", "about", "this", "that", "have"}


def gbrain_ids(query, k=8):
    """Candidate person ids via gbrain keyword search — one search per content word,
    ranked by how many words hit each person. None if gbrain is unavailable/empty.
    (gbrain search is strict tsvector AND, so a whole NL question matches nothing;
    per-word OR-union handles real questions without needing an embedding provider.)"""
    terms = [w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 2 and w not in _STOP]
    if not terms:
        return None
    hits = {}
    try:
        for term in terms[:5]:
            out = subprocess.run([GBRAIN_BIN, "search", term], capture_output=True, text=True, timeout=8)
            if out.returncode != 0:
                continue
            for pid in set(re.findall(r"person:([a-z0-9-]+)", out.stdout)):
                hits[pid] = hits.get(pid, 0) + 1
    except Exception as e:  # noqa: BLE001 — any failure means "use the full directory"
        print("[gbrain] search failed, using full directory:", e)
        return None
    ranked = sorted(hits, key=lambda pid: hits[pid], reverse=True)
    return ranked[:k] or None


def answer(query):
    # Retrieval: gbrain narrows the directory first (flagged, with fallback to all).
    pool, retrieval = people, "all"
    if USE_GBRAIN:
        ids = gbrain_ids(query)
        subset = [p for p in people if p["id"] in ids] if ids else []
        if subset:
            pool, retrieval = subset, "gbrain"

    model, source = None, "gemini"
    try:
        model = call_gemini(query, pool, MODEL, os.environ.get("GEMINI_API_KEY"))
    except Exception as e:  # noqa: BLE001 — any failure falls back to the local ranker
        source = "fallback"
        print("[ask] using local fallback:", e)
    result = rank_experts(query, pool, docs, model)
    result["source"] = source
    result["retrieval"] = retrieval
    return result


def blocks_for(query, result):
    experts = result["experts"]
    if not experts:
        return [{"type": "section", "text": {"type": "mrkdwn", "text": "I couldn't find anyone for that."}}]

    top = experts[0]
    av = top["availability"]
    why = "\n".join("- *{}* — {}".format(r["source"], r["text"]) for r in top.get("rationale", []))
    blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": "*You asked:* {}".format(query)}},
        {"type": "section", "text": {"type": "mrkdwn", "text": (
            "{} *{}* — {}\n{} · match *{}* ({} x {})".format(
                TONE_EMOJI.get(av["tone"], ":white_circle:"), top["name"], top["role"],
                av["label"], top["composite"], top["expertise"], top["factor"]))}},
    ]
    if why:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": why}})
    blocks.append({"type": "actions", "elements": [{
        "type": "button", "style": "primary",
        "text": {"type": "plain_text", "text": "Connect me with " + top["name"].split()[0]},
        "action_id": "connect_expert",
        "value": json.dumps({"slackId": top["slackId"], "name": top["name"], "query": query}),
    }]})
    if len(experts) > 1:
        b = experts[1]
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn",
            "text": "Backup: *{}* ({})".format(b["name"], b["availability"]["label"])}]})
    if result.get("docs"):
        links = " · ".join("<{}|{}>".format(d["url"], d["title"]) for d in result["docs"])
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": "Docs: " + links}]})
    return blocks


@app.command("/xpert")
def handle_xpert(ack, respond, command):
    ack()
    query = (command.get("text") or "").strip()
    if not query:
        respond("Ask me something, e.g. `/xpert how do I deploy SAP to Azure?`")
        return
    respond(blocks=blocks_for(query, answer(query)), response_type="ephemeral")


def default_intro(requester, name, query):
    first = name.split()[0] if name else "there"
    return (
        "Hi {} :wave: <@{}> here — I could use your help with this:\n"
        "> {}\n\nDo you have ~15 minutes? (Found you via XpertFinder — no manager relay needed.)"
    ).format(first, requester, query)


def intro_view(draft, meta):
    return {
        "type": "modal",
        "callback_id": "send_intro",
        "private_metadata": json.dumps(meta),
        "title": {"type": "plain_text", "text": "Intro to " + meta["name"][:18]},
        "submit": {"type": "plain_text", "text": "Send"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": [
            {"type": "section", "text": {"type": "mrkdwn", "text": "To *{}* about:\n> {}".format(meta["name"], meta["query"])}},
            {"type": "input", "block_id": "draft",
             "label": {"type": "plain_text", "text": "Message (edit before sending)"},
             "element": {"type": "plain_text_input", "action_id": "message", "multiline": True, "initial_value": draft}},
            {"type": "actions", "elements": [
                {"type": "button", "action_id": "refine_draft", "text": {"type": "plain_text", "text": ":sparkles: Refine with AI"}}
            ]},
        ],
    }


@app.action("connect_expert")
def handle_connect(ack, body, client):
    """Open an editable draft modal instead of sending immediately."""
    ack()
    payload = json.loads(body["actions"][0]["value"])
    meta = {
        "slackId": payload.get("slackId"),
        "name": payload["name"],
        "query": payload["query"],
        "requester": body["user"]["id"],
    }
    meta["draft"] = default_intro(meta["requester"], meta["name"], meta["query"])
    client.views_open(trigger_id=body["trigger_id"], view=intro_view(meta["draft"], meta))


@app.action("refine_draft")
def handle_refine(ack, body, client):
    """Rewrite the current draft with Gemini and update the modal in place."""
    ack()
    meta = json.loads(body["view"]["private_metadata"])
    try:
        current = body["view"]["state"]["values"]["draft"]["message"]["value"] or meta["draft"]
    except Exception:  # noqa: BLE001
        current = meta["draft"]
    prompt = (
        "Rewrite this short outreach message to a colleague named {} about the question below. "
        "Keep it friendly, concise, professional, under 45 words. First person, as the sender. "
        "Do NOT add a signature, sign-off, or placeholders like [Your Name]. "
        "Return ONLY the message text, no preamble.\n\n"
        "Question: {}\n\nCurrent message:\n{}"
    ).format(meta["name"], meta["query"], current)
    try:
        refined = generate_text(prompt, MODEL, os.environ.get("GEMINI_API_KEY")) or current
    except Exception as e:  # noqa: BLE001 — if Gemini fails, keep the current text
        print("[refine] failed:", e)
        refined = current
    meta["draft"] = refined
    client.views_update(view_id=body["view"]["id"], view=intro_view(refined, meta))


@app.view("send_intro")
def handle_send_intro(ack, body, client):
    """On submit, open the DM and post the (edited) message — cutting the manager relay."""
    ack()
    meta = json.loads(body["view"]["private_metadata"])
    message = body["view"]["state"]["values"]["draft"]["message"]["value"] or meta["draft"]
    requester = meta["requester"]
    try:
        res = client.conversations_open(users="{},{}".format(requester, meta["slackId"]))
        client.chat_postMessage(channel=res["channel"]["id"], text=message)
    except Exception as e:  # noqa: BLE001 — placeholder ids fall back to DMing the requester
        print("[send_intro] falling back to requester DM:", e)
        client.chat_postMessage(channel=requester, text=message + "\n\n_(demo mode: swap {}'s placeholder Slack id for a real user id in data/people.json)_".format(meta["name"]))


if __name__ == "__main__":
    print("XpertFinder bot starting (Socket Mode, model: {})".format(MODEL))
    SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"]).start()
