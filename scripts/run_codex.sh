#!/usr/bin/env bash
# One unattended, repository-scoped task. Run with bash; no executable bit needed.
set -Eeuo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
cd "$repo"
task=${1:-docs/CODEX_M1.md}
[[ -f "$task" ]] || { printf 'Task file not found: %s\n' "$task" >&2; exit 2; }
for command in codex git gh timeout; do
    command -v "$command" >/dev/null || { printf 'Missing command: %s\n' "$command" >&2; exit 2; }
done
case "$(git remote get-url origin)" in
    https://github.com/ReloadLightly/evolved-circuit-construction|https://github.com/ReloadLightly/evolved-circuit-construction.git|git@github.com:ReloadLightly/evolved-circuit-construction.git) ;;
    *) printf 'Wrong origin; no files changed.\n' >&2; exit 2 ;;
esac
[[ "$(git branch --show-current)" == main ]] || { printf 'Run on this repository main branch.\n' >&2; exit 2; }
[[ -z "$(git status --porcelain)" ]] || { printf 'Existing changes preserved. Commit or set them aside before starting this publication-enabled task.\n' >&2; exit 2; }
export GIT_TERMINAL_PROMPT=0 GCM_INTERACTIVE=Never GIT_EDITOR=true
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
unset OPENAI_API_KEY CODEX_API_KEY OPENAI_BASE_URL
mkdir -p .local/tmp .local/uv-cache .local/pip-cache
export TMPDIR="$repo/.local/tmp" UV_CACHE_DIR="$repo/.local/uv-cache" PIP_CACHE_DIR="$repo/.local/pip-cache"
gh auth status --hostname github.com >/dev/null
codex -c 'forced_login_method="chatgpt"' login status
codex --version
# Metadata and Git publication run here, outside the agent's workspace sandbox.
# A metadata failure must not prevent the scientific task.
gh repo edit ReloadLightly/evolved-circuit-construction --description "$(cat ABOUT.txt)" || printf 'About update failed; continuing with research.\n' >&2
printf '\nRequested: gpt-6-astra / Ultra; ChatGPT authentication; no approval prompts.\n'
printf 'Task: %s; session ceiling: 100 minutes.\n\n' "$task"
set +e
timeout --signal=TERM --kill-after=30s 100m \
    codex --ask-for-approval never --sandbox workspace-write \
    --model gpt-6-astra \
    -c 'model_provider="openai"' \
    -c 'model_reasoning_effort="ultra"' \
    -c 'forced_login_method="chatgpt"' \
    -c 'sandbox_workspace_write.network_access=true' \
    -c 'web_search="live"' \
    -c 'agents.enabled=true' \
    -c 'agents.max_concurrent_threads_per_session=2' \
    -c 'agents.max_depth=1' \
    exec --ephemeral --output-last-message "$repo/.local/last-codex-message.md" \
    - < "$task"
agent_status=$?
set -e
# A zero agent exit status is NOT proof that an experiment or hypothesis succeeded.
# Preserve partial work too, with an accurate commit message; never reset or force-push.
if [[ -n "$(git status --porcelain)" ]]; then
    git add -A -- .
    git commit -m "research: $(basename "$task" .md) task output (agent exit $agent_status)"
fi
local_sha=$(git rev-parse HEAD)
if git push origin HEAD:main; then
    remote_sha=$(git ls-remote --exit-code origin refs/heads/main | awk '{print $1}')
    [[ "$local_sha" == "$remote_sha" ]] || { printf 'Remote verification mismatch; local work preserved.\n' >&2; exit 3; }
    printf '\nPublished and verified origin/main: %s\n' "$local_sha"
else
    printf '\nPush failed. Local commit %s is preserved; no automatic reset or force-push.\n' "$local_sha" >&2
    exit 3
fi
printf 'Agent exit: %s. Scientific completion and results must be read from its report, not inferred from this exit code.\n' "$agent_status"
exit "$agent_status"
