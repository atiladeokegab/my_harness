#!/bin/bash
# Usage: ship.sh <tag>   (run from the app checkout)  - SKILL.md §9 in one step: tagged no-traffic deploy, smoke, GPU batch.
# Env: SVC PROJECT REGION BUCKET REFERER JOB ENV_FILE (a .env holding OPENAI_API_KEY and GOOGLE_TILES_KEY),
#      optional SMOKE_PATH (e.g. /api/places/tower-bridge). Exits non-zero on any failure.
# It never promotes: on a pass it prints the update-traffic command for a person or the lead agent to run.
set -uo pipefail
T=${1:?usage: ship.sh <tag>}; : "${SVC:?}" "${PROJECT:?}" "${REGION:?}" "${BUCKET:?}" "${REFERER:?}" "${JOB:?}" "${ENV_FILE:?}"
[ -r "$ENV_FILE" ] || { echo "FAIL: cannot read ENV_FILE"; exit 2; }
# Read the keys without sourcing the file (sourcing runs it). Values never reach stdout, stderr or disk.
key() { sed -n "s/^\(export \)\{0,1\}$1=//p" "$ENV_FILE" | tail -1 | sed 's/^["'\'']//; s/["'\'']$//'; }
OPENAI=$(key OPENAI_API_KEY); TILES=$(key GOOGLE_TILES_KEY)
[ -n "$OPENAI" ] && [ -n "$TILES" ] || { echo "FAIL: OPENAI_API_KEY or GOOGLE_TILES_KEY missing from ENV_FILE"; exit 2; }

# The Makefile's flags, less --allow-unauthenticated: the service is already public and the tag inherits it,
# so the flag is only an IAM write. The keys go through a 0600 YAML file, never gcloud's argv (visible in ps).
KD=$(umask 077; mktemp -d); trap 'rm -rf "$KD"' EXIT
yq() { printf "'%s'" "${1//\'/\'\'}"; }   # YAML single-quoted scalar
(umask 077; { echo "OPENAI_API_KEY: $(yq "$OPENAI")"; echo "GOOGLE_TILES_KEY: $(yq "$TILES")"; } > "$KD/env.yaml")
unset OPENAI TILES
echo "deploy $SVC tag $T (no traffic)"
timeout 1200 gcloud run deploy "$SVC" --source . --region "$REGION" --project "$PROJECT" --no-traffic --tag "$T" \
  --max-instances 2 --min-instances 1 --memory 2Gi --cpu 2 --timeout 300 \
  --env-vars-file "$KD/env.yaml" --quiet || { echo "FAIL: deploy"; exit 1; }
rm -rf "$KD"

# Every tagged revision keeps its own --min-instances warm and billed (26 stale tags cost ~£25/day in Nov 2026),
# so a failed check drops its tag and the promote step drops the others.
fail() { echo "FAIL: $1"
  timeout 120 gcloud run services update-traffic "$SVC" --region "$REGION" --project "$PROJECT" --remove-tags "$T" --quiet \
    >/dev/null 2>&1 && echo "removed tag $T"; exit 1; }
TR=$(timeout 60 gcloud run services describe "$SVC" --region "$REGION" --project "$PROJECT" \
  --flatten=status.traffic --format='value(status.traffic.tag,status.traffic.url)')
URL=$(awk -F'\t' -v t="$T" '$1 == t { print $2; exit }' <<<"$TR")
OLD=$(awk -F'\t' -v t="$T" '$1 != "" && $1 != t { print $1 }' <<<"$TR" | paste -sd, -)
case "$URL" in https://*) echo "tag URL $URL";; *) fail "no URL for tag $T";; esac

for p in / ${SMOKE_PATH:-}; do
  curl -fsS --max-time 60 -o /dev/null "$URL$p" || fail "smoke $URL$p"
done
echo "smoke ok"

PROJECT=$PROJECT BUCKET=$BUCKET REFERER=$REFERER JOB=$JOB DIST=/out/none "$(dirname "$0")/batch.sh" "$T" "$URL" \
  || fail "GPU batch"

echo "PASS $T. Look at the contact sheet, then promote as its own step:"
echo "  gcloud run services update-traffic $SVC --region $REGION --project $PROJECT --to-tags $T=100"
[ -n "$OLD" ] && echo "  gcloud run services update-traffic $SVC --region $REGION --project $PROJECT --remove-tags $OLD"
echo "Rejected instead: --remove-tags $T, or it stays warm and billed."
