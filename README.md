# XpertFinder

**Cut the manager relay.** You have a question, someone two teams over knows the answer — but today it crawls through a chain of managers and back. XpertFinder deletes that middleman: ask in Slack, and it introduces you *directly* to the exact person who can help — ranked by real expertise signals and by **who's actually reachable right now**.

Built for c0mpiled pt 3 — YC RFS challenge #1 (*Company Brain — structuring internal knowledge for AI execution*). LLM: **Gemini**.

## Two surfaces (same brain)

| Surface | File | Status |
|---|---|---|
| **Slack bot** (primary) | `bot.py` | Python + Slack Bolt, **Socket Mode** (no public URL / ngrok) |
| Web app (optional backup demo) | `server.mjs` | Zero-dep Node, same data + ranking |

Both share `data/`, the same availability ranking, and the same Gemini prompt. Pick the Slack bot for the demo — it *is* the "cut the middleman" story: the intro happens where the conversation already lives.

## Slack bot — quickstart

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # fill in the two Slack tokens + GEMINI_API_KEY
python bot.py               # connects over Socket Mode, no tunnel needed
```

Then in Slack: `/xpert I need help deploying SAP to Azure` → the bot replies with the best reachable expert and a **Connect me** button that opens a direct DM.

Runs with **no Gemini key** too (local fallback ranker, shown as "offline ranker").

### One-time Slack app setup (~5 min, no ngrok)

**Fast path — from the manifest:** api.slack.com/apps → Create New App → **From an app manifest** → pick your workspace → paste [`slack-manifest.yaml`](slack-manifest.yaml). That pre-configures the bot, `/xpert`, scopes, Socket Mode, and interactivity in one shot. Then:

1. **Basic Information → App-Level Tokens → Generate**, scope `connections:write` → `SLACK_APP_TOKEN` (`xapp-...`).
2. **Install to Workspace → Bot User OAuth Token** → `SLACK_BOT_TOKEN` (`xoxb-...`).
3. Put both in `.env`.
4. **Make the direct-DM magic real:** set each expert's `slackId` in `data/people.json` to a **real workspace user id** (your demo teammates). Otherwise the bot falls back to DMing you the intro (demo mode).

## How it works

```
/xpert <question>
  → Gemini scores each seeded profile's EXPERTISE (+ rationale)
  → ranker.py applies the availability factor:  composite = expertise × factor
       available ×1.0 · free soon ×0.9 · busy ×0.75 · OOO ×0.5
  → re-sort → best REACHABLE expert (not just the smartest)
  → [Connect me] → conversations_open(you, expert) → intro posted → relay deleted
```

Gemini judges expertise; code judges availability. The multiplier is deterministic and explainable ("96 × 0.5"), so the recommendation can route around an unavailable expert — and you can defend every number.

## Files

| Path | What |
|------|------|
| `bot.py` | Slack bot: `/xpert` command + `Connect me` action (Socket Mode) |
| `ranker.py` | Availability factor + composite + re-sort + local fallback |
| `gemini_client.py` | Gemini request builder + call (stdlib urllib, no dep) |
| `data/people.json` | 6 seeded experts across all 6 signal types |
| `data/docs.json` | Seeded related documentation |
| `server.mjs`, `public/`, `lib/` | Optional Node web-app backup surface |

## Seeded scenarios (bulletproof for the demo)

- **"I need help deploying SAP to Azure"** → Sarah Chen (primary), Marcus Rivera (backup) — the hero.
- **"Who owns the payments service?"** → Ben Osei.
- **"Kubernetes cost tuning"** → Tomás Fischer.
- **"GDPR data-retention rules"** → Aiko Tanaka.

## Task split — 2 engineers, ~5h (12:00–17:00)

**Eng 1 — bot + Slack**
- Slack app setup (steps above), verify `/xpert` + Connect over Socket Mode
- Map seeded experts to real teammate user ids so the group DM really opens
- Own the ≤90s demo video + the "availability re-routes" beat

**Eng 2 — brain + data**
- Enrich `data/people.json` / `docs.json`, tune the ranking prompt in `gemini_client.py`
- Stretch: ingest profiles into **GBrain** (the required platform) and retrieve top-k before ranking — on-theme + engineering lift

## Demo script (~90s)

1. "You have a question. Someone two teams over knows the answer. Today it goes you → your lead → their lead → the person → and all the way back. Days."
2. In Slack: `/xpert how do I deploy SAP to Azure?` → point at the *why* signals and the availability.
3. "It finds the smartest person you can **actually reach** — 96 × availability."
4. Click **Connect me** → a real DM with the expert opens on screen. "The relay is gone. That's XpertFinder."
