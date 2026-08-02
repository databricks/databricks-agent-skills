#!/bin/bash
# Ralph loop driver - databricks-agent-skills audit remediation
#
# Usage: ./loop.sh [mode] [args]
#
#   ./loop.sh                          Build mode, unlimited iterations
#   ./loop.sh 20                       Build mode, max 20 iterations
#   ./loop.sh plan                     Full planning pass (regenerate whole plan)
#   ./loop.sh plan 3                   Planning, max 3 iterations
#   ./loop.sh plan-work "SPEC-10 cross-skill traversal sweep"
#                                      Scoped planning for the current work branch
#
# Scoping happens at plan creation, never at task selection. Create the work
# branch first, then run plan-work with a natural-language description of the
# concern. Build mode then just picks "most important" from an already-scoped
# plan, with no semantic filtering at build time.

set -uo pipefail

MODE="build"
PROMPT_FILE="PROMPT_build.md"
MAX_ITERATIONS=0
WORK_DESC=""

if [ "${1:-}" = "plan" ]; then
    MODE="plan"
    PROMPT_FILE="PROMPT_plan.md"
    MAX_ITERATIONS=${2:-0}
elif [ "${1:-}" = "plan-work" ]; then
    MODE="plan-work"
    PROMPT_FILE="PROMPT_plan.md"
    WORK_DESC="${2:-}"
    MAX_ITERATIONS=${3:-2}
    if [ -z "$WORK_DESC" ]; then
        echo "Error: plan-work requires a work description."
        echo "  ./loop.sh plan-work \"SPEC-10 cross-skill traversal sweep\""
        exit 1
    fi
elif [[ "${1:-}" =~ ^[0-9]+$ ]]; then
    MAX_ITERATIONS=$1
fi

# --- Safety gate -------------------------------------------------------------
# The loop runs with --dangerously-skip-permissions, which bypasses the
# permission system entirely. The sandbox is the only remaining boundary.
# Refuse to run outside one unless explicitly overridden.
if [ "${RALPH_SANDBOXED:-0}" != "1" ]; then
    echo "Refusing to run: RALPH_SANDBOXED is not set to 1."
    echo
    echo "This loop runs with --dangerously-skip-permissions. On a machine"
    echo "carrying workspace credentials, SSH keys, or cloud tokens the blast"
    echo "radius is every one of them. Run inside a container with only this"
    echo "fork mounted and no credentials present, then set RALPH_SANDBOXED=1."
    echo
    echo "See references/sandbox-environments.md in the Ralph playbook."
    exit 1
fi

# --- Repo guard --------------------------------------------------------------
if [ ! -f "scripts/skills.py" ]; then
    echo "Error: run from the root of your databricks-agent-skills fork clone."
    echo "No path is hardcoded; this checks for scripts/skills.py in \$PWD."
    exit 1
fi

if [ ! -f "$PROMPT_FILE" ]; then
    echo "Error: $PROMPT_FILE not found"
    exit 1
fi

CURRENT_BRANCH=$(git branch --show-current)

if [ "$CURRENT_BRANCH" = "main" ] && [ "$MODE" = "build" ]; then
    echo "Refusing to build on main. Create a work branch first:"
    echo "  git checkout -b ralph/spec-10-traversal"
    exit 1
fi

# DCO: every commit must be signed off with a real name.
GIT_NAME=$(git config user.name || true)
GIT_EMAIL=$(git config user.email || true)
if [ -z "$GIT_NAME" ] || [ -z "$GIT_EMAIL" ]; then
    echo "Error: git user.name and user.email must be set. Upstream requires"
    echo "DCO sign-off with a real name; pseudonymous commits are rejected."
    exit 1
fi

ITERATION=0

echo "----------------------------------------"
echo "Mode:   $MODE"
echo "Prompt: $PROMPT_FILE"
echo "Branch: $CURRENT_BRANCH"
echo "Signer: $GIT_NAME <$GIT_EMAIL>"
[ -n "$WORK_DESC" ] && echo "Scope:  $WORK_DESC"
[ $MAX_ITERATIONS -gt 0 ] && echo "Max:    $MAX_ITERATIONS iterations"
echo "----------------------------------------"

# Baseline backpressure before the first iteration. If the tree is already
# failing, that is upstream breakage and the loop must not paper over it.
echo "Running baseline backpressure..."
python3 scripts/skills.py validate || { echo "Baseline validate failed. Stop."; exit 1; }
python3 -m unittest discover -s tests -p '*_test.py' -q || { echo "Baseline tests failed. Stop."; exit 1; }
echo "Baseline green."

while true; do
    if [ $MAX_ITERATIONS -gt 0 ] && [ $ITERATION -ge $MAX_ITERATIONS ]; then
        echo "Reached max iterations: $MAX_ITERATIONS"
        break
    fi

    if [ "$MODE" = "plan-work" ]; then
        {
            cat "$PROMPT_FILE"
            echo
            echo "WORK SCOPE FOR THIS BRANCH: $WORK_DESC"
            echo "Scope IMPLEMENTATION_PLAN.md to this concern only. Findings"
            echo "outside it belong to other branches; note them under a"
            echo "'Deferred to other branches' heading and do not plan them."
        } | claude -p \
            --dangerously-skip-permissions \
            --output-format=stream-json \
            --model opus \
            --verbose
    else
        cat "$PROMPT_FILE" | claude -p \
            --dangerously-skip-permissions \
            --output-format=stream-json \
            --model opus \
            --verbose
    fi

    git push origin "$CURRENT_BRANCH" 2>/dev/null || \
        git push -u origin "$CURRENT_BRANCH" || \
        echo "Push failed; continuing. Commits are local."

    ITERATION=$((ITERATION + 1))
    echo
    echo "======================== LOOP $ITERATION ========================"
    echo
done
