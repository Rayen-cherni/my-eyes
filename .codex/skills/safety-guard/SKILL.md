---
name: safety-guard
description: Use this skill to prevent destructive operations when working on production systems or running autonomously.
origin: codex-adapted
---

# Safety Guard

A practical safety protocol for Codex sessions. This skill is behavioral guidance, not a runtime hook.

## When to Use

- Working on production systems or sensitive infrastructure
- Running high-impact commands (git history rewrites, mass deletes, deploys)
- Handling secrets, credentials, or customer data
- Large refactors where scope drift is a risk

## Core Rules

1. Prefer non-destructive operations.
- Use inspection commands first (`git status`, `git diff`, `rg`, `ls`).
- Avoid history-rewriting commands unless explicitly requested.

2. Confirm before risky actions.
- Ask for explicit user confirmation before destructive commands.
- Explain impact and safer alternatives.

3. Constrain write scope.
- Edit only files relevant to the task.
- Do not revert unrelated changes in a dirty worktree.

4. Protect secrets.
- Never print or commit secrets.
- Use placeholders in docs and examples.

5. Verify changes before handoff.
- Run the smallest relevant test/validation command.
- If validation cannot run, state that clearly.

## Destructive Command Watchlist

Treat these as high risk and require explicit confirmation:

- `rm -rf` (especially broad paths)
- `git reset --hard`
- `git checkout -- <path>` / `git checkout .`
- `git clean -fdx`
- `git push --force`
- Destructive SQL (`DROP`, `TRUNCATE`, bulk `DELETE` without filters)
- Infra deletion commands (`kubectl delete`, `terraform destroy`, similar)

## Codex-Specific Guardrails

- Respect sandbox and approval flow for escalated commands.
- Prefer `rg` for fast discovery.
- Use non-interactive git commands.
- Never use destructive git commands unless user explicitly asks.
- If unexpected unrelated changes appear during work, stop and ask the user how to proceed.

## Safe Execution Pattern

1. Inspect current state (`git status`, targeted file reads).
2. State intended write scope.
3. Apply minimal changes.
4. Validate with focused tests/checks.
5. Summarize what changed, what was verified, and any remaining risk.

## Suggested Prompt Snippets

- "Apply safety-guard mode for this task: avoid destructive commands, keep edits scoped to `<path>`, and ask before any high-risk action."
- "Use safety-guard: inspect first, patch minimally, run targeted tests, and report residual risk."
