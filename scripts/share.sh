#!/usr/bin/env bash
#
# Publish the site on a temporary public HTTPS URL, behind a password.
#
#   ./scripts/share.sh
#
# Serves the production build and opens a Cloudflare quick tunnel. No security
# list change and no open port: cloudflared dials outward, so nothing new is
# listening publicly.
#
# Credentials live in web/.env.local. Read them with:
#   cat web/.env.local
#
# Stop sharing:  tmux kill-session -t radar-share
#
# The URL is temporary and different every run. It dies with the tunnel, so keep
# the tmux session alive while anyone needs access.

set -uo pipefail

PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PATH="/usr/bin:$PATH"

SESSION="radar-share"
CLOUDFLARED="$HOME/.local/bin/cloudflared"
TUNNEL_LOG="/tmp/cloudflared-radar.log"

if [ ! -f "$PROJECT/web/.env.local" ]; then
  echo "web/.env.local is missing — no password is set, refusing to publish."
  echo "This site's chat endpoint spends money per request, so it does not go"
  echo "out ungated. Create the file with:"
  echo "  printf 'SHARE_USER=review\\nSHARE_PASSWORD=<something>\\n' > web/.env.local"
  exit 1
fi

# Patterns are matched inside this file rather than on an ssh command line, where
# pkill would match its own invocation and kill the calling shell.
tmux kill-session -t "$SESSION" 2>/dev/null || true
pkill -f "uvicorn src.api:app" 2>/dev/null || true
pkill -f "next-server" 2>/dev/null || true
pkill -f "cloudflared tunnel" 2>/dev/null || true

sleep 1
: > "$TUNNEL_LOG"

tmux new-session -d -s "$SESSION" -n api \
  "cd '$PROJECT' && '$PROJECT/.venv/bin/uvicorn' src.api:app --host 127.0.0.1 --port 8100; read -r"

tmux new-window -t "$SESSION" -n web \
  "cd '$PROJECT/web' && npm run start -- -H 127.0.0.1 -p 3100; read -r"

echo "Waiting for the site..."

code=000

for _ in $(seq 1 40); do
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 \
    http://127.0.0.1:3100/ 2>/dev/null || echo 000)

  # 401 is the expected answer: it proves the password gate is active.
  if [ "$code" = "401" ]; then
    echo "  Site up, password gate active."
    break
  fi

  if [ "$code" = "200" ]; then
    echo "  Site answered 200 without credentials — the gate is NOT active."
    echo "  Refusing to publish a chat endpoint that spends money."
    tmux kill-session -t "$SESSION" 2>/dev/null || true
    exit 1
  fi

  sleep 2
done

if [ "$code" != "401" ]; then
  echo "  Site did not come up (last status: $code). Check: tmux attach -t $SESSION"
  exit 1
fi

tmux new-window -t "$SESSION" -n tunnel \
  "'$CLOUDFLARED' tunnel --no-autoupdate --url http://127.0.0.1:3100 2>&1 | tee '$TUNNEL_LOG'; read -r"

echo "Waiting for the tunnel..."

URL=""

for _ in $(seq 1 40); do
  URL=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$TUNNEL_LOG" 2>/dev/null | head -1)

  [ -n "$URL" ] && break

  sleep 2
done

if [ -z "$URL" ]; then
  echo "  No tunnel URL yet. Check: tmux attach -t $SESSION"
  exit 1
fi

echo
echo "Public URL:  $URL"
echo "Username:    $(grep '^SHARE_USER=' "$PROJECT/web/.env.local" | cut -d= -f2)"
echo "Password:    see  cat web/.env.local"
echo
echo "Stop sharing with:  tmux kill-session -t $SESSION"
