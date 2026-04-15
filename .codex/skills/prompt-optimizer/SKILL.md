---
name: prompt-optimizer
description: Analyze a draft prompt, identify gaps, and output a ready-to-paste optimized prompt for Codex. Advisory only; do not execute the task itself.
origin: codex-adapted
metadata:
  author: adapted-from-community
  version: "2.0.0"
---

# Prompt Optimizer (Codex)

Improve user prompts so Codex can execute reliably with clear scope, constraints, and validation.

## When to Use

- User asks to optimize or rewrite a prompt
- User asks how to prompt Codex for a coding task
- User provides a vague prompt and asks for a better one

## Do Not Use

- User wants direct execution now (just do the task)
- User is asking for code/performance optimization directly, not prompt quality

## Operating Mode

Advisory only.

- Do not implement the task.
- Do not edit files or run commands for implementation.
- Output diagnosis plus improved prompt(s).

## Workflow

### 1) Detect intent
Classify primary intent:

- New feature
- Bug fix
- Refactor
- Tests
- Review
- Docs
- Infra/CI
- Research/design

### 2) Detect scope
Estimate scope quickly:

- `low`: single file or isolated change
- `medium`: multi-file same area
- `high`: cross-module/system change

### 3) Check missing context
Look for missing essentials:

- Tech stack / language
- Target files or module boundaries
- Acceptance criteria
- Test/validation expectations
- Security/performance constraints
- Out-of-scope boundaries

If critical context is missing, ask up to 3 concise questions.

### 4) Build optimized prompt
Produce a self-contained prompt that includes:

- Task objective
- Repository/context assumptions
- Concrete scope (paths/modules)
- Constraints and non-goals
- Validation steps and done criteria
- Output format expectations

## Output Format

### Section 1: Prompt Diagnosis

- Strengths
- Gaps
- Clarifications needed (if any)

### Section 2: Optimized Prompt (Full)

Provide one ready-to-paste prompt in a fenced code block.

### Section 3: Optimized Prompt (Compact)

Provide a short variant for experienced users.

### Section 4: Why This Is Better

List concise improvements.

## Quality Bar for Optimized Prompts

A good optimized prompt should:

- Be specific about where to change code
- Request minimal, scoped edits
- Require verification (tests/lint/type-check)
- Handle uncertainty explicitly (assumptions/questions)
- Avoid tool- or vendor-specific commands that may not exist

## Template

```markdown
You are working in `<repo/project context>`.

Goal:
- <what to build/fix>

Scope:
- In: <files/modules>
- Out: <non-goals>

Constraints:
- Follow existing patterns in <paths/files>
- Keep changes minimal and focused
- Do not introduce unrelated refactors

Implementation requirements:
- <behavioral requirements>
- <error handling/security/performance requirements>

Validation:
- Run: <test command(s)>
- Confirm: <acceptance criteria>

Output:
- Summary of changes
- Files touched
- Validation results and remaining risks
```

## Quick Patterns

- Feature: "Implement X in Y module with tests and scoped edits; preserve existing conventions."
- Bug fix: "Reproduce bug with a test, fix minimally, and verify no regressions."
- Refactor: "Refactor only Z area for readability/maintainability, behavior unchanged, tests green."
- Review: "Perform a code review focused on correctness, risk, and test gaps; findings first."
