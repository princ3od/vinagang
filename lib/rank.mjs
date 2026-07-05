// The "availability as a ranking factor" logic — deterministic, testable, no LLM.
// composite = expertise (from Claude, or the local fallback) × availability factor.

export const AVAIL_FACTOR = { available: 1.0, soon: 0.9, busy: 0.75, ooo: 0.5 };
export const AVAIL_LABEL = { available: "Available now", soon: "Free soon", busy: "Busy today", ooo: "Out of office" };
const TONE = { available: "success", soon: "warning", busy: "warning", ooo: "danger" };

function tokenize(s) {
  return (s || "").toLowerCase().match(/[a-z0-9]+/g) || [];
}

// Fallback ranker used when the Anthropic API key is missing or the call fails.
// Scores by how many DISTINCT query facets a person covers (so "SAP, SAP, SAP" counts once,
// and covering both "sap" and "azure" beats covering either alone) — keeps the demo alive offline.
export function localRank(query, people) {
  const facetsWanted = [...new Set(tokenize(query).filter((w) => w.length > 2))];
  return people.map((p) => {
    const hay = new Set([
      ...tokenize(p.role),
      ...(p.skills || []).flatMap(tokenize),
      ...(p.projects || []).flatMap((x) => tokenize(x.name)),
      ...(p.certs || []).flatMap((c) => tokenize(c.name)),
    ]);
    const covered = facetsWanted.filter((f) => hay.has(f));
    const matched = (p.skills || []).filter((sk) => covered.some((f) => tokenize(sk).includes(f)));
    const expertise = Math.min(97, 45 + covered.length * 16 + Math.min(matched.length, 3) * 4);
    const rationale = matched.slice(0, 2).map((sk) => ({ source: "SKILLS", text: `Strong in ${sk}` }));
    return { id: p.id, expertise, rationale: rationale.length ? rationale : [{ source: "HR", text: p.role }] };
  });
}

export function rankExperts(query, people, docs, model) {
  const byId = Object.fromEntries(people.map((p) => [p.id, p]));
  const scored = model?.experts?.length ? model.experts : localRank(query, people);

  const experts = scored
    .map((s) => {
      const p = byId[s.id];
      if (!p) return null;
      const status = p.availability?.status || "available";
      const factor = AVAIL_FACTOR[status] ?? 0.7;
      const expertise = Math.max(0, Math.min(100, Math.round(s.expertise)));
      const composite = Math.round(expertise * factor);
      return {
        id: p.id,
        name: p.name,
        email: p.email,
        slackId: p.slackId,
        role: p.role,
        dept: p.dept,
        expertise,
        factor,
        composite,
        availability: {
          status,
          label: p.availability?.label || AVAIL_LABEL[status],
          tone: TONE[status] || "muted",
          freeAt: p.availability?.freeAt || null,
        },
        rationale: (s.rationale || []).slice(0, 3),
      };
    })
    .filter(Boolean)
    .sort((a, b) => b.composite - a.composite);

  experts.forEach((e, i) => {
    e.rank = i === 0 ? "primary" : i === 1 ? "backup" : "related";
  });

  const intent = model?.intent || deriveIntent(query, people);
  return {
    intent,
    experts: experts.slice(0, 4),
    docs: pickDocs(query, intent, docs),
    sources: ["Projects", "Docs", "Code", "Jira", "HR", "Certs"],
  };
}

function deriveIntent(query, people) {
  const ql = query.toLowerCase();
  const skills = [
    ...new Set(
      (people.flatMap((p) => p.skills || [])).filter(
        (sk) => ql.includes(sk.toLowerCase()) || tokenize(sk).some((w) => w.length > 3 && ql.includes(w))
      )
    ),
  ].slice(0, 4);
  const urgency = /urgent|asap|immediately|right now|today|blocked|help|stuck/.test(ql) ? "high" : "normal";
  return {
    skills: skills.length ? skills : tokenize(query).filter((w) => w.length > 3).slice(0, 3),
    domain: "",
    urgency,
  };
}

function pickDocs(query, intent, docs) {
  const terms = new Set([...tokenize(query), ...(intent.skills || []).flatMap(tokenize)]);
  return docs
    .map((d) => ({ d, score: (d.tags || []).reduce((n, t) => n + (terms.has(t) ? 1 : 0), 0) }))
    .filter((x) => x.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, 3)
    .map((x) => x.d);
}
