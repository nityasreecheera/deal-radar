#!/usr/bin/env bash
#
# Start the API and the web interface in a tmux session named "radar-web".
#
#   ./scripts/web.sh
#
# Then from your own machine:
#   ssh -L 3100:localhost:3100 oci
#   open http://localhost:3100
#
# Watch logs:  tmux attach -t radar-web   (Ctrl-b n switches window)
# Stop:        tmux kill-session -t radar-web
#
# Port 3100 rather than 3000 so this does not collide with the sibling project's
# site, which uses 3000. Same reason the API is on 8100 rather than 8000.

set -uo pipefail

PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# The VM also has Node inside ~/.hermes. Put the system copy first so a Hermes
# update cannot change which Node this builds against.
export PATH="/usr/bin:$PATH"

SESSION="radar-web"

# Patterns are matched inside this file rather than on an ssh command line, where
# pkill would match its own invocation and kill the calling shell.
tmux kill-session -t "$SESSION" 2>/dev/null || true
pkill -f "uvicorn src.api:app" 2>/dev/null || true
pkill -f "next-server" 2>/dev/null || true

sleep 1

tmux new-session -d -s "$SESSION" -n api \
  "cd '$PROJECT' && '$PROJECT/.venv/bin/uvicorn' src.api:app --host 127.0.0.1 --port 8100; read -r"

# Bind to localhost explicitly: Next's dev server otherwise listens on every
# interface, and the tunnel reaches localhost anyway.
tmux new-window -t "$SESSION" -n web \
  "cd '$PROJECT/web' && npm run dev -- -H 127.0.0.1 -p 3100; read -r"

echo "Waiting for both to come up..."

for _ in $(seq 1 40); do
  api=$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 \
    http://127.0.0.1:8100/api/health 2>/dev/null || echo 000)
  web=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 \
    http://127.0.0.1:3100/ 2>/dev/null || echo 000)

  if [ "$api" = "200" ] && [ "$web" = "200" ]; then
    echo "  API  http://127.0.0.1:8100  ok"
    echo "  Web  http://127.0.0.1:3100  ok"
    echo
    echo "From your own machine:"
    echo "  ssh -L 3100:localhost:3100 oci"
    echo "  then open http://localhost:3100"
    exit 0
  fi

  sleep 2
done

echo "  API $api / Web $web — one did not start. Check: tmux attach -t $SESSION"
exit 1
