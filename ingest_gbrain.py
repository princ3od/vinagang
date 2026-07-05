"""Push each person's aggregated profile into gbrain as one page (slug person:<id>).
Re-run after editing data/people.json. Keyword search (gbrain search) needs no embeddings."""
import json
import os
import pathlib
import subprocess

GB = os.environ.get("GBRAIN_BIN", os.path.expanduser("~/.bun/bin/gbrain"))
ROOT = pathlib.Path(__file__).parent
people = json.loads((ROOT / "data" / "people.json").read_text())


def page_text(p):
    lines = [
        f"{p['name']} — {p.get('role', '')}, {p.get('dept', '')}.",
        "Skills: " + ", ".join(p.get("skills", [])) + ".",
    ]
    for pr in p.get("projects", []):
        lines.append(f"Project: {pr.get('role')} on {pr.get('name')} ({pr.get('year')}). {pr.get('outcome', '')}")
    for c in p.get("codeowners", []):
        lines.append(f"Code owner of {c.get('repo')} ({', '.join(c.get('languages', []))}).")
    for j in p.get("jira", []):
        lines.append(f"Resolved {j.get('resolved')} {j.get('component')} tickets.")
    for c in p.get("certs", []):
        lines.append(f"Certified {c.get('name')} ({c.get('issuer')}).")
    g = p.get("git")
    if g:
        lines.append(f"Git: {g.get('commits')} commits across {', '.join(g.get('areas', []))}; last active {g.get('lastActive')}.")
    return "\n".join(lines)


def main():
    for p in people:
        slug = f"person:{p['id']}"
        r = subprocess.run([GB, "put", slug], input=page_text(p), text=True, capture_output=True)
        print(("ok   " if r.returncode == 0 else "ERR  ") + slug + ("" if r.returncode == 0 else " :: " + r.stderr[:120]))
    print(f"done: {len(people)} people ingested into gbrain")


if __name__ == "__main__":
    main()
