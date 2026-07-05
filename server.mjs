// XpertFinder — zero-dependency Node server (needs Node 18+ for global fetch).
// Serves the static UI and two endpoints: /api/ask (Claude ranking) and /api/slack (webhook intro).
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, join, extname, normalize } from "node:path";
import { rankExperts } from "./lib/rank.mjs";
import { buildRequest, parseModelJSON } from "./lib/prompt.mjs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const PORT = process.env.PORT || 3000;
const MODEL = process.env.MODEL || "gemini-2.5-flash";
const PUBLIC = join(__dirname, "public");

const people = JSON.parse(await readFile(join(__dirname, "data/people.json"), "utf8"));
const docs = JSON.parse(await readFile(join(__dirname, "data/docs.json"), "utf8"));

const MIME = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".svg": "image/svg+xml" };

async function callGemini(query) {
  const key = process.env.GEMINI_API_KEY;
  if (!key) throw new Error("no GEMINI_API_KEY");
  const { system, user } = buildRequest(query, people);
  const res = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${MODEL}:generateContent`, {
    method: "POST",
    headers: { "x-goog-api-key": key, "content-type": "application/json" },
    body: JSON.stringify({
      systemInstruction: { parts: [{ text: system }] },
      contents: [{ role: "user", parts: [{ text: user }] }],
      generationConfig: { responseMimeType: "application/json", maxOutputTokens: 1600, temperature: 0.2 },
    }),
  });
  if (!res.ok) throw new Error(`Gemini ${res.status}: ${await res.text()}`);
  const data = await res.json();
  const text = (data.candidates?.[0]?.content?.parts || []).map((p) => p.text || "").join("");
  return parseModelJSON(text);
}

function readBody(req) {
  return new Promise((resolve) => {
    let b = "";
    req.on("data", (c) => (b += c));
    req.on("end", () => resolve(b));
  });
}

function sendJSON(res, obj, code = 200) {
  res.writeHead(code, { "content-type": "application/json" });
  res.end(JSON.stringify(obj));
}

async function serveStatic(req, res) {
  const rel = req.url === "/" ? "/index.html" : req.url.split("?")[0];
  const full = normalize(join(PUBLIC, rel));
  if (!full.startsWith(PUBLIC)) return sendJSON(res, { error: "forbidden" }, 403);
  try {
    const buf = await readFile(full);
    res.writeHead(200, { "content-type": MIME[extname(full)] || "text/plain" });
    res.end(buf);
  } catch {
    res.writeHead(404, { "content-type": "text/plain" });
    res.end("not found");
  }
}

const server = createServer(async (req, res) => {
  try {
    if (req.method === "POST" && req.url === "/api/ask") {
      const { query } = JSON.parse((await readBody(req)) || "{}");
      if (!query) return sendJSON(res, { error: "query required" }, 400);
      let model = null;
      let source = "gemini";
      try {
        model = await callGemini(query);
      } catch (e) {
        source = "fallback";
        console.warn("[ask] using local fallback:", e.message);
      }
      return sendJSON(res, { ...rankExperts(query, people, docs, model), source });
    }

    if (req.method === "POST" && req.url === "/api/slack") {
      const { name, email, message } = JSON.parse((await readBody(req)) || "{}");
      const webhook = process.env.SLACK_WEBHOOK_URL;
      if (!webhook) {
        return sendJSON(res, { ok: true, simulated: true, note: "No SLACK_WEBHOOK_URL set — intro was simulated." });
      }
      const payload = {
        text: `XpertFinder intro request → ${name}`,
        blocks: [
          { type: "section", text: { type: "mrkdwn", text: `*XpertFinder intro* — <mailto:${email}|${name}>` } },
          { type: "section", text: { type: "mrkdwn", text: message } },
        ],
      };
      const sres = await fetch(webhook, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(payload),
      });
      return sendJSON(res, { ok: sres.ok });
    }

    return serveStatic(req, res);
  } catch (e) {
    sendJSON(res, { error: e.message }, 500);
  }
});

server.listen(PORT, () => console.log(`XpertFinder → http://localhost:${PORT}  (model: ${MODEL})`));
