#!/bin/bash
# ship.sh with gcloud, curl and batch.sh stubbed: a failing deploy, smoke or batch stops it before the promote line,
# it never runs update-traffic, and the keys never reach its output.   bash test_ship.sh
set -u
HERE=$(cd "$(dirname "$0")" && pwd); W=$(mktemp -d); trap 'rm -rf "$W"' EXIT
mkdir -p "$W/bin" "$W/app"; cp "$HERE/ship.sh" "$W/"
cat > "$W/bin/gcloud" <<'EOF'
#!/bin/bash
echo "$*" >> "$W/gcloud.log"
for a; do [ "${prev:-}" = --env-vars-file ] && { cat "$a"; stat -c %a "$a"; } >> "$W/envfile.log"; prev=$a; done
case "$*" in
  *"run deploy"*) exit "${DEPLOY_RC:-0}";;
  *"services describe"*) printf 'old\thttps://old---svc.run.app\n\t\nt1\thttps://t1---svc.run.app\n';;
esac
EOF
cat > "$W/bin/curl" <<'EOF'
#!/bin/bash
echo "$*" >> "$W/curl.log"; exit "${CURL_RC:-0}"
EOF
cat > "$W/batch.sh" <<'EOF'
#!/bin/bash
echo "$* DIST=$DIST" >> "$W/batch.log"; exit "${BATCH_RC:-0}"
EOF
chmod +x "$W/bin/"* "$W/batch.sh"
printf 'OPENAI_API_KEY="sk-secret-one"\nexport GOOGLE_TILES_KEY=tiles-secret-two\n' > "$W/env"
export W PATH="$W/bin:$PATH" SVC=svc PROJECT=p REGION=r BUCKET=b REFERER=https://svc.run.app/ JOB=j ENV_FILE=$W/env

fails=0
run() {  # run <name> <want-exit 0|1> [VAR=value ...]
  local name=$1 want=$2; shift 2
  rm -f "$W"/*.log
  out=$(cd "$W/app" && env "$@" bash "$W/ship.sh" t1 2>&1); rc=$?
  ok=1
  if [ "$want" = 0 ]; then [ $rc = 0 ] && grep -q 'update-traffic svc --region r --project p --to-tags t1=100' <<<"$out" || ok=0
  else [ $rc != 0 ] && ! grep -q update-traffic <<<"$out" || ok=0; fi
  grep -q 'sk-secret-one\|tiles-secret-two' <<<"$out" && ok=0          # keys never printed
  grep -q -- '--to-tags' "$W/gcloud.log" 2>/dev/null && ok=0          # never promotes itself
  [ $ok = 1 ] && echo "ok   $name" || { echo "FAIL $name (rc $rc)"; echo "$out" | sed 's/^/    /'; fails=$((fails + 1)); }
}
run pass 0
grep -q -- '--remove-tags old$' <<<"$out" && ! grep -q 'remove-tags' "$W/gcloud.log" \
  && echo "ok   pass: prints the old-tag cleanup, runs none" || { echo "FAIL pass: old-tag cleanup"; fails=$((fails + 1)); }
grep -q -- '--no-traffic --tag t1' "$W/gcloud.log" && ! grep -q 'secret' "$W/gcloud.log" \
  && grep -qx "OPENAI_API_KEY: 'sk-secret-one'" "$W/envfile.log" && grep -qx "GOOGLE_TILES_KEY: 'tiles-secret-two'" "$W/envfile.log" \
  && grep -qx 600 "$W/envfile.log" \
  && grep -q '^t1 https://t1---svc.run.app DIST=/out/none' "$W/batch.log" && echo "ok   pass: deploy flags, keys and batch args" \
  || { echo "FAIL pass: deploy flags, keys or batch args"; fails=$((fails + 1)); }
run deploy-fails 1 DEPLOY_RC=1
run smoke-fails 1 CURL_RC=22
[ -e "$W/batch.log" ] && { echo "FAIL smoke-fails: batch ran after a failed smoke"; fails=$((fails + 1)); }
run batch-fails 1 BATCH_RC=1
grep -q -- '--remove-tags t1 ' "$W/gcloud.log" && echo "ok   batch-fails: drops its own tag" \
  || { echo "FAIL batch-fails: tag t1 left warm"; fails=$((fails + 1)); }
run no-keys 1 ENV_FILE=/dev/null
[ $fails = 0 ] && echo "PASS test_ship.sh" || { echo "FAIL test_ship.sh: $fails"; exit 1; }
