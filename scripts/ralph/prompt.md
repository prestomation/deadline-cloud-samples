# Ralph Agent Instructions

You are an autonomous coding agent working on the deadline-cloud-samples repository.

## Working Directory

You are running from the **project root** directory (`~/deadline-cloud-samples`). Ralph files are in `scripts/ralph/`:
- PRD: `scripts/ralph/prd.json`
- Progress: `scripts/ralph/progress.txt`

This allows you to access source code, conda_recipes/, and job_bundles/ from the project root.

## Your Task

1. Read the PRD at `scripts/ralph/prd.json`
2. **READ THE CONTEXT SECTION FIRST** - Technology constraints, reference implementation, infrastructure values
3. **READ notInScope** - Features you MUST NOT implement
4. **READ bestPractices** - Code standards to follow
5. Read the progress log at `scripts/ralph/progress.txt` (check Codebase Patterns section first)
6. Check you're on the correct branch from PRD `branchName`. If not, check it out or create from main/mainline.
7. Pick the **highest priority** user story where `passes: false`
8. Read the story's `context.relevantFiles` if present
9. Implement that single user story
10. Run quality checks (openjd check for templates)
11. If checks pass, commit ALL changes with message: `feat: [Story ID] - [Story Title]`
12. Update the PRD to set `passes: true` for the completed story
13. Append your progress to `scripts/ralph/progress.txt`

## Critical Context from PRD

**READ THE `context` SECTION OF prd.json BEFORE IMPLEMENTING ANY STORY**

The context section contains:
- **technologyConstraints**: Limitations you MUST respect (Maya 2026, maya-usd 0.35.0, Linux only, rattler-build)
- **referenceImplementation**: Existing code to match for patterns
- **infrastructureValues**: Download URLs, checksums

The **notInScope** section lists features you MUST NOT implement - Windows, macOS, older Maya versions.

The **bestPractices** section lists code standards that apply to ALL stories.

## Progress Report Format

APPEND to `scripts/ralph/progress.txt` (never replace, always append):

```
## [Date/Time] - [Story ID]
- What was implemented
- Files changed
- **Learnings for future iterations:**
  - Patterns discovered
  - Gotchas encountered
---
```

## Consolidate Patterns

If you discover a **reusable pattern**, add it to the `## Codebase Patterns` section at the TOP of `scripts/ralph/progress.txt`:

```
## Codebase Patterns
- Example: Use rattler-build recipe.yaml format (not conda-build meta.yaml)
- Example: Always validate templates with 'openjd check'
```

## Quality Requirements

- Validate job templates with `openjd check template.yaml`
- Keep changes focused and minimal
- Follow existing code patterns from reference implementations
- Include README.md files with clear instructions

## Stop Condition

After completing a user story:

1. **Re-read `scripts/ralph/prd.json`** to verify current state
2. **Count stories** where `passes: false`
3. If count is zero (ALL stories have `passes: true`), output only:

```
<promise>COMPLETE</promise>
```

4. If count is greater than zero, end your response normally

## CRITICAL: Completion Signal Warning

**NEVER write the completion signal XML tags in ANY other context!**

The bash script uses `grep` to detect completion. When referring to the completion mechanism:
- Say "the completion signal" or "COMPLETE marker"
- Do NOT quote or include the actual XML tags

## Important

- Work on ONE story per iteration
- Commit after each completed story
- Only output the completion signal when ALL stories pass
- NEVER include the completion signal in explanatory text
