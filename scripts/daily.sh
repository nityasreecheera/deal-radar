#!/usr/bin/env bash
#
# One radar run, for cron.
#
# Writes the digest to outputs/digests/ and appends to a log. Delivery is opt-in
# via RADAR_SEND=1, because push needs a messaging platform credentialed in
# Hermes and there is no point failing the whole run when there isn't one.
#
# Install:  crontab -e   then add
#   0 13 * * 1-5 /home/opc/deal-radar/scripts/daily.sh
#
# 13:00 UTC is roughly 9am US Eastern, and weekdays only because EDGAR does not
# publish at weekends. The run itself uses a three-day window, so a Monday run
# still picks up anything filed late on Friday.

set -uo pipefail

PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$PROJECT/outputs/logs"
LOG="$LOG_DIR/radar.log"

mkdir -p "$LOG_DIR"

stamp() {
  # Date is read at run time rather than passed in, so the log line reflects
  # when the run actually happened.
  date -u '+%Y-%m-%dT%H:%M:%SZ'
}

log() {
  echo "[$(stamp)] $*" >> "$LOG"
}

cd "$PROJECT" || {
  log "FATAL could not enter $PROJECT"
  exit 1
}

if [ ! -x "$PROJECT/.venv/bin/python" ]; then
  log "FATAL no virtualenv at $PROJECT/.venv"
  exit 1
fi

# Every thesis, one message. Without --all this runs config/thesis.yaml
# alone, which is how four domains sat unscheduled while looking configured.
ARGS=(run --all)

if [ "${RADAR_SEND:-0}" = "1" ]; then
  ARGS+=(--send)
fi

log "START ${ARGS[*]}"

# stdout is the digest, stderr is the commentary. Both go to the log, but the
# digest is also saved as its own file by the run itself.
if OUTPUT=$("$PROJECT/.venv/bin/python" -m src.cli "${ARGS[@]}" 2>&1); then
  echo "$OUTPUT" >> "$LOG"
  log "OK"
else
  status=$?
  echo "$OUTPUT" >> "$LOG"
  log "FAILED exit=$status"
  exit "$status"
fi
