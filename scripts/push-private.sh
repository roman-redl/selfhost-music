#!/usr/bin/env bash
# Sync the gitignored docs/private/ into the private handoff repo and push.
# Also picks up session handoff files agents write into handoff/sessions/.
# Usage: scripts/push-private.sh  (HANDOFF_REPO=path to override the clone location)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HANDOFF="${HANDOFF_REPO:-$HOME/personal-projects/handoff}"
DEST="$HANDOFF/selfhost-music"

[ -d "$REPO_ROOT/docs/private" ] || { echo "docs/private not found" >&2; exit 1; }
[ -d "$HANDOFF/.git" ] || { echo "handoff repo missing at $HANDOFF (clone roman-redl/handoff first)" >&2; exit 1; }

mkdir -p "$DEST"
# Mirror semantics: deletions in docs/private propagate to the handoff copy.
rsync -a --delete --exclude '.DS_Store' --exclude '__pycache__' --exclude '*.pyc' \
    "$REPO_ROOT/docs/private/" "$DEST/"

git -C "$HANDOFF" add -A
if git -C "$HANDOFF" diff --cached --quiet; then
    echo "handoff: nothing to sync"
else
    git -C "$HANDOFF" commit -m "sync $(date '+%F %H:%M'): selfhost-music private docs + sessions"
    git -C "$HANDOFF" push
    echo "handoff: pushed"
fi
