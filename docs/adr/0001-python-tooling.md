# 0001: Python tooling

Status: accepted (Phase 0)

## Context
Python 3.13 on a 2017 MacBook; no uv or Docker installed. We want zero extra installs and exact, reviewable pins.

## Options
| Approach | Pros | Cons |
|---|---|---|
| venv + pip + pinned `requirements.txt` | No installs, universal | No transitive lockfile by default |
| uv | Fast, lockfile | Extra install |
| Poetry | Lockfile, packaging | Heavy and slow on old hardware |

## Decision
venv + pip with exact (`==`) pins.

## Consequences
Revisit uv if CI install time becomes a problem (Phase 10).
