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
from gemini_client import call_gemini

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


def gbrain_ids(query, k=8):
    """Candidate person ids from gbrain keyword search, or None if unavailable."""
    try:
        out = subprocess.run([GBRAIN_BIN, "search", query], capture_output=True, text=True, timeout=8)
        if out.returncode != 0:
            return None
        seen, ordered = set(), []
        for pid in re.findall(r"person:([a-z0-9-]+)", out.stdout):
            if pid not in seen:
                seen.add(pid)
                ordered.append(pid)
        return ordered[:k] or None
    except Exception as e:  # noqa: BLE001 — any failure means "use the full directory"
        print("[gbrain] search failed, using full directory:", e)
        return None


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


@app.action("connect_expert")
def handle_connect(ack, body, client, respond):
    ack()
    payload = json.loads(body["actions"][0]["value"])
    requester = body["user"]["id"]
    name, query, expert_slack = payload["name"], payload["query"], payload.get("slackId")
    intro = (
        ":wave: *Intro by XpertFinder.* <@{}> has a question and *{}* is the best person to help:\n"
        "> {}\n\nNo manager relay needed — take it from here.".format(requester, name, query)
    )
    try:
        # Real magic: open a direct group DM between the requester and the expert.
        # Requires the expert's real workspace user id in data/people.json.
        res = client.conversations_open(users="{},{}".format(requester, expert_slack))
        client.chat_postMessage(channel=res["channel"]["id"], text=intro)
        respond("Done — I opened a DM with {}. Check your messages. :tada:".format(name))
    except Exception as e:  # noqa: BLE001 — placeholder ids fall back to DMing the requester
        print("[connect] falling back to requester DM:", e)
        client.chat_postMessage(channel=requester, text=intro + "\n\n_(demo mode: swap {}'s placeholder Slack id for a real user id in data/people.json)_".format(name))
        respond("Sent you the intro to {} (demo mode).".format(name))


if __name__ == "__main__":
    print("XpertFinder bot starting (Socket Mode, model: {})".format(MODEL))
    SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"]).start()
