#!/usr/bin/env bash
#
# Copy the radar's database off the VM and onto this Mac.
#
# The database only ever existed on the server. When Oracle's free trial ended
# it stopped the instance and then deleted it, and for two days it was an open
# question whether 783 judgements still existed anywhere. They did — the boot
# volume outlived the instance — but that was luck, not design.
#
# Run it from cron on the Mac rather than from the VM, so a backup keeps
# happening when the VM is the thing that is broken.
#
#   0 20 * * *  /Users/you/deal-radar/scripts/backup-to-local.sh >> /tmp/radar-backup.log 2>&1
#
set -euo pipefail

HOST="${RADAR_HOST:-oci}"
REMOTE="${RADAR_REMOTE:-deal-radar/data/radar.sqlite}"
DEST="${RADAR_BACKUPS:-$HOME/deal-radar-backups}"
KEEP="${RADAR_KEEP:-30}"

stamp=$(date +%Y%m%d-%H%M)
target="$DEST/$stamp"

mkdir -p "$target"

# Copy to a temporary name and move it into place, so an interrupted transfer
# never leaves a half-written file looking like a good backup.
if ! scp -q "$HOST:$REMOTE" "$target/radar.sqlite.part"; then
    rmdir "$target" 2>/dev/null || true
    echo "$(date -u +%FT%TZ) FAILED: could not reach $HOST"
    exit 1
fi

mv "$target/radar.sqlite.part" "$target/radar.sqlite"

# A file that is not a readable database is not a backup, however many bytes it
# has. Checking here means a corrupt copy is caught on the day it happens
# rather than on the day it is needed.
rows=$(sqlite3 "$target/radar.sqlite" "select count(*) from candidate" 2>/dev/null || echo "")

if [ -z "$rows" ] || [ "$rows" -lt 1 ]; then
    echo "$(date -u +%FT%TZ) FAILED: copied file is not a usable database"
    mv "$target" "$target.suspect"
    exit 1
fi

# Keep the secrets too. Restoring the database without them means a working
# radar that cannot judge anything and a site nobody can log into.
scp -q "$HOST:deal-radar/.env" "$target/env-root.txt" 2>/dev/null || true
scp -q "$HOST:deal-radar/web/.env.local" "$target/env-web.txt" 2>/dev/null || true
chmod 600 "$target"/env-*.txt 2>/dev/null || true

echo "$(date -u +%FT%TZ) ok: $rows judgements -> $target"

# Old backups are deleted only after a new one has been verified, so a run that
# fails leaves yesterday's copy alone.
# awk rather than `head -n -N`, which is a GNU extension: this runs on the Mac,
# where head refuses a negative count.
ls -1d "$DEST"/20* 2>/dev/null | sort |
    awk -v keep="$KEEP" '{ all[NR] = $0 } END { for (i = 1; i <= NR - keep; i++) print all[i] }' |
    while read -r old; do
    rm -rf "$old"
    echo "$(date -u +%FT%TZ) pruned $old"
done
