#!/usr/bin/env bash
# Wait for Vercel's commit status ("Vercel") of $SHA: success -> exit 0; failure/error -> exit 1
# with Vercel's description; pending or absent -> poll until $WAIT_SECONDS (default 1200), then exit 1.
# Needs: gh (GH_TOKEN), SHA, GITHUB_REPOSITORY. Optional: INTERVAL (default 20).
set -u
deadline=$((SECONDS + ${WAIT_SECONDS:-1200}))
while :; do
  # statuses come newest first: the first "Vercel" one is the current state
  row=$(gh api "repos/$GITHUB_REPOSITORY/commits/$SHA/statuses" \
    --jq '[.[] | select(.context == "Vercel")][0] | [.state, .description] | @tsv' 2>/dev/null || true)
  state=${row%%$'\t'*}
  desc=${row#*$'\t'}
  case "$state" in
    success) echo "Vercel: $desc ($SHA)"; exit 0 ;;
    failure|error) echo "::error::Vercel не выкатил фронт — API не выкатываем: $desc"; exit 1 ;;
  esac
  if [ "$SECONDS" -ge "$deadline" ]; then
    echo "::error::Vercel не выкатил фронт за срок ожидания (${state:-нет статуса}) — API не выкатываем"
    exit 1
  fi
  sleep "${INTERVAL:-20}"
done
