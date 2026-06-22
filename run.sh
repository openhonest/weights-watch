#!/bin/sh
# weights-watch scheduled runner. Sources a local .env for OPENROUTER_API_KEY,
# runs the panel, appends to run.log. Point your cron / launchd / systemd timer
# at this script. Edit the .env path if yours lives elsewhere.
cd "$(dirname "$0")" || exit 1
if [ -f .env ]; then
  set -a
  . ./.env
  set +a
fi
echo "=== weights-watch run $(date '+%Y-%m-%d %H:%M:%S') ===" >> run.log
uv run python weights_watch.py >> run.log 2>&1
echo "exit $?" >> run.log
