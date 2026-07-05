#!/usr/bin/env bash
# Generate a representative repo so ingest_git.py has REAL commits to mine.
# In production you skip this and point ingest_git.py at your actual repos —
# nothing changes but the path. Commits are authored as the real demo people
# across domain folders, so the mined signal maps to them.
set -euo pipefail
REPO="${1:-./sample-repo}"
rm -rf "$REPO"; mkdir -p "$REPO"; git -C "$REPO" init -q

mk () { # area  author  email  count  day(YYYY-MM-DD)
  local area="$1" name="$2" email="$3" count="$4" day="$5" i
  for i in $(seq 1 "$count"); do
    mkdir -p "$REPO/$area"
    echo "change $i" >> "$REPO/$area/file_$i.txt"
    git -C "$REPO" add "$area/file_$i.txt"
    GIT_AUTHOR_NAME="$name" GIT_AUTHOR_EMAIL="$email" \
    GIT_COMMITTER_NAME="$name" GIT_COMMITTER_EMAIL="$email" \
    GIT_AUTHOR_DATE="${day}T10:00:00" GIT_COMMITTER_DATE="${day}T10:00:00" \
    git -C "$REPO" commit -q -m "$area: change $i"
  done
}

mk sap-azure         "Thi"             thi@vinagang.io       14 2026-07-03
mk k8s-cost          "Thi"             thi@vinagang.io        9 2026-06-30
mk azure-landingzone "hoang bui"       hoangbui@vinagang.io  11 2026-07-01
mk gdpr              "hoang bui"       hoangbui@vinagang.io   6 2026-06-27
mk sap-finance       "Khanh Linh Tran" khanhlinh@vinagang.io  7 2026-06-25
mk payments          "Khanh Linh Tran" khanhlinh@vinagang.io 12 2026-07-02

echo "sample repo at $REPO"
git -C "$REPO" shortlog -sne
