"""XpertFinder Slack bot — Socket Mode (no public URL / ngrok needed).
  /xpert <question>  -> Gemini ranks seeded experts -> replies with the best reachable one
  [Connect me]       -> opens a direct DM with that expert, cutting the manager relay.
"""
import os
import json
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
TONE_EMOJI = {"success": ":large_green_circle:", "warning": ":large_yellow_circle:", "danger": ":red_circle:"}

app = App(token=os.environ["SLACK_BOT_TOKEN"])


def answer(query):
    model, source = None, "gemini"
    try:
        model = call_gemini(query, people, MODEL, os.environ.get("GEMINI_API_KEY"))
    except Exception as e:  # noqa: BLE001 — any failure falls back to the local ranker
        source = "fallback"
        print("[ask] using local fallback:", e)
    result = rank_experts(query, people, docs, model)
    result["source"] = source
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
    tag = "ranked by Gemini" if result.get("source") != "fallback" else "offline ranker"
    blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": "_" + tag + "_"}]})
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
