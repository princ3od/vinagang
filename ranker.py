"""Expertise + availability ranking. Deterministic, testable, no LLM needed.
composite = expertise (from Gemini, or the local fallback) x availability factor."""
import re

AVAIL_FACTOR = {"available": 1.0, "soon": 0.9, "busy": 0.75, "ooo": 0.5}
AVAIL_LABEL = {"available": "Available now", "soon": "Free soon", "busy": "Busy today", "ooo": "Out of office"}
TONE = {"available": "success", "soon": "warning", "busy": "warning", "ooo": "danger"}


def tokenize(s):
    return re.findall(r"[a-z0-9]+", (s or "").lower())


def local_rank(query, people):
    """Fallback ranker: score by how many DISTINCT query facets each person covers.
    Keeps the demo alive when the Gemini key is missing or the call fails."""
    facets_wanted = list(dict.fromkeys(w for w in tokenize(query) if len(w) > 2))
    out = []
    for p in people:
        hay = set(tokenize(p.get("role", "")))
        for sk in p.get("skills", []):
            hay.update(tokenize(sk))
        for pr in p.get("projects", []):
            hay.update(tokenize(pr.get("name", "")))
        for c in p.get("certs", []):
            hay.update(tokenize(c.get("name", "")))
        covered = [f for f in facets_wanted if f in hay]
        matched = [sk for sk in p.get("skills", []) if any(f in tokenize(sk) for f in covered)]
        expertise = min(97, 45 + len(covered) * 16 + min(len(matched), 3) * 4)
        rationale = [{"source": "SKILLS", "text": "Strong in " + sk} for sk in matched[:2]]
        if not rationale:
            rationale = [{"source": "HR", "text": p.get("role", "")}]
        out.append({"id": p["id"], "expertise": expertise, "rationale": rationale})
    return out


def rank_experts(query, people, docs, model=None):
    by_id = {p["id"]: p for p in people}
    scored = model["experts"] if model and model.get("experts") else local_rank(query, people)

    experts = []
    for s in scored:
        p = by_id.get(s["id"])
        if not p:
            continue
        av = p.get("availability") or {}
        status = av.get("status", "available")
        factor = AVAIL_FACTOR.get(status, 0.7)
        expertise = max(0, min(100, round(s["expertise"])))
        experts.append({
            "id": p["id"], "name": p["name"], "email": p.get("email"), "slackId": p.get("slackId"),
            "role": p.get("role"), "dept": p.get("dept"),
            "expertise": expertise, "factor": factor, "composite": round(expertise * factor),
            "availability": {
                "status": status, "label": av.get("label", AVAIL_LABEL.get(status)),
                "tone": TONE.get(status, "muted"), "freeAt": av.get("freeAt"),
            },
            "rationale": s.get("rationale", [])[:3],
        })

    experts.sort(key=lambda e: e["composite"], reverse=True)
    for i, e in enumerate(experts):
        e["rank"] = "primary" if i == 0 else "backup" if i == 1 else "related"

    intent = (model or {}).get("intent") or _derive_intent(query, people)
    return {
        "intent": intent,
        "experts": experts[:4],
        "docs": _pick_docs(query, intent, docs),
        "sources": ["Projects", "Docs", "Code", "Jira", "HR", "Certs"],
    }


def _derive_intent(query, people):
    ql = query.lower()
    skills = []
    for p in people:
        for sk in p.get("skills", []):
            if sk.lower() in ql or any(len(w) > 3 and w in ql for w in tokenize(sk)):
                if sk not in skills:
                    skills.append(sk)
    urgency = "high" if re.search(r"urgent|asap|immediately|right now|today|blocked|help|stuck", ql) else "normal"
    if not skills:
        skills = [w for w in tokenize(query) if len(w) > 3][:3]
    return {"skills": skills[:4], "domain": "", "urgency": urgency}


def _pick_docs(query, intent, docs):
    terms = set(tokenize(query))
    for sk in intent.get("skills", []):
        terms.update(tokenize(sk))
    scored = [(sum(1 for t in d.get("tags", []) if t in terms), d) for d in docs]
    scored = [x for x in scored if x[0] > 0]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [d for _, d in scored[:3]]
