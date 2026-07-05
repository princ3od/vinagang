"""Mine a real git repo for a code-ownership signal and merge it into data/people.json.
  python ingest_git.py [repo_path]   (default: ./sample-repo; run make_sample_repo.sh first)
In production, point it at your real repos and update AREA_TO_PERSON / the author emails."""
import collections
import json
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).parent
REPO = sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "sample-repo")

# Top-level repo folder -> person id in data/people.json.
AREA_TO_PERSON = {
    "sap-azure": "sarah-chen",
    "k8s-cost": "tomas-fischer",
    "azure-landingzone": "marcus-rivera",
    "gdpr": "aiko-tanaka",
    "sap-finance": "priya-nair",
    "payments": "ben-osei",
}


def git(*args):
    return subprocess.run(["git", "-C", REPO, *args], capture_output=True, text=True, check=True).stdout


def main():
    log = git("log", "--numstat", "--pretty=format:C|%h|%ae|%ad", "--date=short")
    stats = collections.defaultdict(lambda: {"commits": 0, "areas": collections.Counter(), "last": ""})
    counted, commit, date = set(), None, None
    for line in log.splitlines():
        if line.startswith("C|"):
            _, commit, _email, date = line.split("|")
        elif line.strip():
            parts = line.split("\t")
            if len(parts) != 3:
                continue
            area = parts[2].split("/")[0]
            pid = AREA_TO_PERSON.get(area)
            if not pid:
                continue
            s = stats[pid]
            if (pid, commit) not in counted:
                s["commits"] += 1
                counted.add((pid, commit))
            s["areas"][area] += 1
            if date > s["last"]:
                s["last"] = date

    people = json.loads((ROOT / "data" / "people.json").read_text())
    repo_name = os.path.basename(os.path.abspath(REPO))
    for p in people:
        s = stats.get(p["id"])
        if s:
            p["git"] = {
                "commits": s["commits"],
                "areas": [a for a, _ in s["areas"].most_common()],
                "lastActive": s["last"],
                "repo": repo_name,
            }
    (ROOT / "data" / "people.json").write_text(json.dumps(people, indent=2, ensure_ascii=False) + "\n")

    for p in people:
        g = p.get("git")
        if g:
            print(f"  {p['name']:16} {g['commits']:2} commits  {g['areas']}  last {g['lastActive']}")
    print("merged git signal into data/people.json")


if __name__ == "__main__":
    main()
