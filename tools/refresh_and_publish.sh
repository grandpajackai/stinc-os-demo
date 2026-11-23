#!/usr/bin/env bash
# Export a sanitized public snapshot for the STINC OS GitHub Pages site and
# push data/live.json if the snapshot changed. Mechanical, no LLM, no Grok.
# Safe to run from launchd. Never force-pushes. Logs errors; does not notify.
set -euo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:${PATH:-}"
export GIT_TERMINAL_PROMPT=0
export TZ="America/New_York"

REPO="$(cd "$(dirname "$0")/.." && pwd)"
PLATFORM="${STINC_PLATFORM:-$HOME/Projects/stinc-platform}"
BRAND="${STINC_BRAND:-$HOME/Projects/content-engine/brands/ralfy-the-plug}"
LOG="${STINC_OSDATA_LOG:-$HOME/Library/Logs/stinc-os-data.log}"
LOCK="$REPO/.git/osdata.lock"
PYTHON="${STINC_PYTHON:-$(command -v python3)}"

mkdir -p "$(dirname "$LOG")"
log() {
  local msg
  msg="$(printf '%s  %s\n' "$(date '+%Y-%m-%d %H:%M:%S %Z')" "$*")"
  printf '%s\n' "$msg" >>"$LOG"
  if [ -t 1 ]; then printf '%s\n' "$msg"; fi
}

fail() {
  log "ERROR: $*"
  exit 1
}

cd "$REPO"
if ! mkdir "$LOCK" 2>/dev/null; then
  if [ -n "$(find "$LOCK" -maxdepth 0 -mmin +60 2>/dev/null)" ]; then
    rmdir "$LOCK"
    mkdir "$LOCK"
  else
    log "SKIP: refresh already running"
    exit 0
  fi
fi
trap 'rmdir "$LOCK" 2>/dev/null || true' EXIT

git remote get-url origin >/dev/null 2>&1 || fail "no origin remote"
if [ -d .git/rebase-merge ] || [ -d .git/rebase-apply ]; then
  fail "rebase in progress; not touching it"
fi

n=1
delay=5
until git fetch -q origin main; do
  [ "$n" -ge 3 ] && fail "fetch failed 3x (network/auth)"
  sleep "$delay"
  n=$((n + 1))
  delay=$((delay * 3))
done

if [ -n "$(git log HEAD..origin/main --oneline 2>/dev/null)" ]; then
  stashed=0
  if ! git diff --quiet -- data/live.json || ! git diff --cached --quiet -- data/live.json; then
    git stash push -q -- data/live.json -m "osdata: pre-pull live.json"
    stashed=1
  fi
  if ! git pull -q --rebase origin main; then
    if [ -d .git/rebase-merge ] || [ -d .git/rebase-apply ]; then
      git rebase --abort || true
    fi
    if [ "$stashed" -eq 1 ]; then git stash pop -q || true; fi
    fail "pull --rebase conflicted or failed; aborted, not force-pushing"
  fi
  if [ "$stashed" -eq 1 ]; then
    git stash pop -q || true
  fi
  log "pulled $(git rev-parse --short HEAD)"
fi

"$PYTHON" "$REPO/tools/export_live_data.py" --platform "$PLATFORM" --brand "$BRAND" --out "$REPO" >>"$LOG" 2>&1
log "exported snapshot"

if ! "$PYTHON" -m unittest discover -s tests -q >>"$LOG" 2>&1; then
  fail "python tests failed; snapshot not committed"
fi
log "python tests passed"
if command -v node >/dev/null 2>&1 && [ -f "$REPO/tests/qa-runtime.cjs" ]; then
  if ! node "$REPO/tests/qa-runtime.cjs" >>"$LOG" 2>&1; then
    fail "qa-runtime tests failed; snapshot not committed"
  fi
  log "qa-runtime tests passed"
fi

changed=1
if git show HEAD:data/live.json >/dev/null 2>&1; then
  if "$PYTHON" - "$REPO" <<'PYCMP'
import json, subprocess, sys
from pathlib import Path

repo = Path(sys.argv[1])

def norm(doc):
    if isinstance(doc, dict):
        doc = dict(doc)
        doc.pop("generated_at", None)
    return json.dumps(doc, sort_keys=True, separators=(",", ":"))

new = json.loads((repo / "data/live.json").read_text(encoding="utf-8"))
try:
    old = json.loads(subprocess.check_output(["git", "show", "HEAD:data/live.json"], text=True))
except Exception:
    sys.exit(1)
sys.exit(0 if norm(new) == norm(old) else 1)
PYCMP
  then
    changed=0
  fi
fi

if [ "$changed" -eq 0 ]; then
  git checkout -q -- data/live.json
  log "snapshot unchanged"
  exit 0
fi

git add -- data/live.json
if [ -d "$REPO/assets/clip-thumbs" ]; then
  git add -- assets/clip-thumbs/*.jpg 2>/dev/null || true
fi
if [ -d "$REPO/assets/emails" ]; then
  git add -A -- assets/emails 2>/dev/null || true
fi
# Never let anything but the public snapshot (and its thumbs) ride along.
while IFS= read -r path; do
  case "$path" in
    data/live.json|assets/clip-thumbs/*.jpg|assets/emails/*.html) continue ;;
  esac
  git reset -q -- "$path"
done < <(git diff --cached --name-only)

if git diff --cached --quiet -- data/live.json assets/clip-thumbs; then
  log "snapshot unchanged"
  exit 0
fi

git commit -q -m "data: refresh live snapshot"
log "committed: $(git log -1 --format='%h %s')"

n=1
delay=5
until git pull -q --rebase origin main; do
  if [ -d .git/rebase-merge ] || [ -d .git/rebase-apply ]; then
    git rebase --abort || true
    fail "pull --rebase conflicted; aborted, local commit kept, not force-pushing"
  fi
  [ "$n" -ge 3 ] && fail "pull failed 3x (network/auth); local commit kept"
  sleep "$delay"
  n=$((n + 1))
  delay=$((delay * 3))
done

if [ -n "$(git log origin/main..HEAD --oneline 2>/dev/null)" ]; then
  git push -q origin main || fail "push failed; local commit kept, not force-pushing"
  log "pushed $(git rev-parse --short HEAD)"
else
  log "up to date with origin/main"
fi
