# Coding instructions

- Keep responses concise and implementation-focused.
- Prefer minimal changes over large refactors.
- Change only files necessary for the requested task.
- Avoid unnecessary abstractions.
- Avoid verbose comments and docstrings unless they add real value.
- Prefer simple, readable Python over clever code.
- Do not rewrite working code without a clear reason.
- Preserve the existing project structure and naming conventions.
- When fixing a bug, make the smallest safe fix.
- When adding a feature, keep the diff small.
- Do not add dependencies unless necessary.
- Do not modify unrelated files.
- Before editing, briefly inspect the relevant files.
- After editing, summarize:
  1. what changed,
  2. which files changed,
  3. how to test it.

## Python

- Follow PEP 8.
- Prefer type hints for non-trivial functions.
- Avoid deeply nested logic.
- Prefer small functions with clear responsibility.
- Use existing dependencies before adding new ones.

## Git

- Never commit or push unless explicitly asked.
- Never modify `main` directly unless explicitly asked.
- Assume development happens on the current branch.

## Hackathon mode

- Prioritize working functionality over perfect architecture.
- Prefer solutions that can be implemented and tested quickly.
- Avoid premature optimization.
- Avoid building infrastructure that is not needed for the demo.
- If there are multiple valid approaches, choose the simplest one that works.