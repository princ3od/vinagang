"""Gemini call — stdlib only (urllib), no extra dependency.
Gemini judges EXPERTISE; availability is applied separately in ranker.py."""
import json
import urllib.request


def build_request(query, people):
    profiles = []
    for p in people:
        profiles.append({
            "id": p["id"], "role": p.get("role"), "dept": p.get("dept"), "skills": p.get("skills", []),
            "projects": ["{} on {} ({})".format(x.get("role"), x.get("name"), x.get("year")) for x in p.get("projects", [])],
            "codeowner": [c.get("repo") for c in p.get("codeowners", [])],
            "jira": ["{} {} tickets".format(j.get("resolved"), j.get("component")) for j in p.get("jira", [])],
            "certs": [c.get("name") for c in p.get("certs", [])],
        })
    system = (
        "You are XpertFinder, a company brain that finds the right internal expert for a question. "
        "Each employee profile aggregates signals from projects, docs, code ownership, Jira, HR and certifications. "
        "Score each person's EXPERTISE for the question from 0-100. Do NOT consider availability. "
        "Respond with STRICT JSON only."
    )
    user = (
        'Question: "{}"\n\nProfiles:\n{}\n\n'.format(query, json.dumps(profiles))
        + 'Return JSON exactly: {"intent":{"skills":["..."],"domain":"...","urgency":"high|normal|low"},'
        + '"experts":[{"id":"...","expertise":0,"rationale":[{"source":"PROJECTS|DOCS|CODE|JIRA|HR|CERTS","text":"short reason"}]}]}\n'
        + "Include every profile id. Up to 3 rationale items each, under 12 words."
    )
    return system, user


def parse_model_json(text):
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object in model output")
    return json.loads(text[start:end + 1])


def call_gemini(query, people, model, api_key):
    if not api_key:
        raise ValueError("no GEMINI_API_KEY")
    system, user = build_request(query, people)
    url = "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent".format(model)
    body = json.dumps({
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {"responseMimeType": "application/json", "maxOutputTokens": 1600, "temperature": 0.2},
    }).encode()
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"x-goog-api-key": api_key, "content-type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    parts = (data.get("candidates") or [{}])[0].get("content", {}).get("parts", [])
    text = "".join(pt.get("text", "") for pt in parts)
    return parse_model_json(text)
