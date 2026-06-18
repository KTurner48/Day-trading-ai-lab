#!/usr/bin/env bash
#
# verify_phase15.sh — one-command verification for the AUREUS MVP.
#
# Runs, in order:
#   1. Backend safety gate (pytest tests/safety)
#   2. Backend full suite + frontend tests/build
#   3. Dev stack bring-up (migrations + seed run automatically)
#   4. Smoke checks (health endpoints, container status)
#   5. Env-level hard stop: GLOBAL_KILL_SWITCH=true with DB switch FALSE
#
# Stops on the FIRST failure and prints the failing command + output.
# Prints PHASE 15 PASS only if everything succeeds. No fabricated results.

set -u

BOLD="$(printf '\033[1m')"; DIM="$(printf '\033[2m')"; RESET="$(printf '\033[0m')"

section() {
  printf '\n%s========================================================%s\n' "$BOLD" "$RESET"
  printf '%s== %s%s\n' "$BOLD" "$1" "$RESET"
  printf '%s========================================================%s\n' "$BOLD" "$RESET"
}

run_shell() {
  local desc="$1"; shift; local cmd="$1"
  printf '%s--> %s%s\n' "$DIM" "$desc" "$RESET"
  printf '%s    $ %s%s\n' "$DIM" "$cmd" "$RESET"
  local output status
  output="$(bash -c "$cmd" 2>&1)"; status=$?
  printf '%s\n' "$output"
  if [ "$status" -ne 0 ]; then
    printf '\n%s*** FAILURE ***%s\n' "$BOLD" "$RESET"
    printf 'Step:            %s\n' "$desc"
    printf 'Failing command: %s\n' "$cmd"
    printf 'Exit code:       %s\n' "$status"
    printf '\nStopping. Phase 15 is NOT verified.\n'
    exit "$status"
  fi
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

printf '%sAUREUS MVP — Verification%s\nRepo: %s\n' "$BOLD" "$RESET" "$REPO_ROOT"

# Ensure a .env exists (dev defaults) without clobbering an existing one.
if [ ! -f .env ]; then
  run_shell "Create .env from .env.example" "cp .env.example .env"
fi

# ---------------------------------------------------------------------------
section "STEP 1/5  Bring up the stack (db, redis, backend, frontend)"
run_shell "docker compose up -d --build" "docker compose up -d --build"
run_shell "Wait for backend health" \
  'for i in $(seq 1 30); do curl -fsS http://localhost:8000/api/health >/dev/null 2>&1 && exit 0; sleep 2; done; exit 1'

# ---------------------------------------------------------------------------
section "STEP 2/5  Backend safety gate + full suite"
run_shell "Safety gate (tests/safety)" "docker compose exec -T backend pytest tests/safety -q"
run_shell "Full backend suite" "docker compose exec -T backend pytest -q"

# ---------------------------------------------------------------------------
section "STEP 3/5  Frontend tests + production build"
run_shell "Frontend unit tests (ARM LIVE + kill switch)" "cd frontend && npm install && npm run test"
run_shell "Frontend production build" "cd frontend && npm run build"

# ---------------------------------------------------------------------------
section "STEP 4/5  Smoke checks"
run_shell "Backend health (paper default)" \
  'out="$(curl -fsS http://localhost:8000/api/health)"; echo "$out"; echo "$out" | grep -q "\"trading_mode\":\"paper\""'
run_shell "Container status" "docker compose ps"

# ---------------------------------------------------------------------------
section "STEP 5/5  Env-level hard stop (GLOBAL_KILL_SWITCH, DB switch FALSE)"
# Runs the dedicated env tests INSIDE the backend container with the env var set
# true for that process only. DB kill switch stays false (the tests assert it).
# The tests SKIP if the env var is not seen. Rather than parse the summary line
# (brittle), we run verbose and require each NAMED test to print PASSED, and we
# fail if any SKIPPED/skipped appears (which would mean the env var wasn't seen).
run_shell "Env tests prove env hard stop blocks orders + suppresses emission" \
  'out="$(docker compose exec -T -e GLOBAL_KILL_SWITCH=true backend pytest tests/safety/test_env_kill_switch.py -vv --color=no -rs \
      -k "blocks_orders_without_db_kill_switch or suppresses_emission_without_db_kill_switch" 2>&1)"; \
   echo "$out"; \
   echo "$out" | grep -Eq "test_env_kill_switch_blocks_orders_without_db_kill_switch[[:space:]].*PASSED" \
     || { echo "MISSING: blocks_orders test did not report PASSED"; exit 1; }; \
   echo "$out" | grep -Eq "test_env_kill_switch_suppresses_emission_without_db_kill_switch[[:space:]].*PASSED" \
     || { echo "MISSING: suppresses_emission test did not report PASSED"; exit 1; }; \
   echo "$out" | grep -Eqi "SKIPPED" \
     && { echo "ENV TESTS SKIPPED -- GLOBAL_KILL_SWITCH not seen in the test process"; exit 1; }; \
   exit 0'

section "RESULT"
printf '%sPHASE 15 PASS%s — safety gate, full suites, build, smoke, and env hard stop all green.\n' "$BOLD" "$RESET"
