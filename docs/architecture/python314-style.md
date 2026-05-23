# Python 3.14 style notes (repo tooling)

This project targets **Python 3.14** with **Ruff** `target-version = "py314"` (see [`pyproject.toml`](../../pyproject.toml) and [AGENTS.md](../../AGENTS.md)).

## Multi-exception `except`

**Intentionally valid in this codebase:** omitting parentheses when catching multiple exceptions:

```python
except TimeoutError, asyncio.CancelledError:
    ...
```

This matches [AGENTS.md](../../AGENTS.md) *Coding Environment* (Ruff/py314 formatter support). Automated reviewers or parsers that assume older Python 3 grammar may report false positives; prefer checking `uv run ruff format` / `uv run pytest` locally.

Do **not** mass-rewrite comma-style clauses to **`except (A, B):`** for “compat” unless the toolchain or supported Python band changes.
