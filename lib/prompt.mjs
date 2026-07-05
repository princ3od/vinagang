// Builds the Claude request and parses its JSON reply.
// Claude only judges EXPERTISE. Availability is applied deterministically in rank.mjs.

export function buildRequest(query, people) {
  const profiles = people.map((p) => ({
    id: p.id,
    role: p.role,
    dept: p.dept,
    skills: p.skills,
    projects: (p.projects || []).map((x) => `${x.role} on ${x.name} (${x.year})`),
    codeowner: (p.codeowners || []).map((c) => c.repo),
    jira: (p.jira || []).map((j) => `${j.resolved} ${j.component} tickets`),
    certs: (p.certs || []).map((c) => c.name),
  }));

  const system =
    "You are XpertFinder, a company brain that finds the right internal expert for a question. " +
    "Each employee profile aggregates signals from projects, docs, code ownership, Jira, HR and certifications. " +
    "Score each person's EXPERTISE for the question from 0-100. Do NOT consider availability — that is handled separately. " +
    "Respond with STRICT JSON only, no prose, no markdown fences.";

  const user =
    `Question: "${query}"\n\n` +
    `Profiles:\n${JSON.stringify(profiles)}\n\n` +
    "Return JSON exactly in this shape:\n" +
    '{"intent":{"skills":["..."],"domain":"...","urgency":"high|normal|low"},' +
    '"experts":[{"id":"...","expertise":0,"rationale":[{"source":"PROJECTS|DOCS|CODE|JIRA|HR|CERTS","text":"short reason"}]}]}\n' +
    "Include every profile id. Give each expert up to 3 rationale items, each under 12 words, citing the strongest signal.";

  return { system, user };
}

export function parseModelJSON(text) {
  const m = text.match(/\{[\s\S]*\}/);
  if (!m) throw new Error("no JSON object in model output");
  return JSON.parse(m[0]);
}
