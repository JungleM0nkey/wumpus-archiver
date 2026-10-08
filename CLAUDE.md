# wumpus-archiver

A Discord server archiver (Python 3.12, FastAPI, SQLAlchemy over aiosqlite, discord.py) with a SvelteKit portal for exploring the archive. Vocabulary lives in `GLOSSARY.md`; decisions in `docs/adr/`.

## Working here

- Python needs 3.12. Create the environment with `uv venv .venv --python 3.12 && uv pip install -e ".[dev]"`, then run tools from `.venv/bin/`.
- Tests: `.venv/bin/python -m pytest -q` (the whole suite runs in under 20 seconds and must stay green). Files run in parallel through pytest-xdist; add `-n0` to run serially, as `--pdb` needs. Lint: `.venv/bin/ruff check src tests`. Types: `.venv/bin/mypy src/wumpus_archiver`.
- Portal: `npm --prefix portal install`, then `npm --prefix portal run check` and `npm --prefix portal run build`.
- The app is built only through `create_app` in `src/wumpus_archiver/api/app.py`, a pure function of its collaborators; `serve` and the dev module compose those through `src/wumpus_archiver/compose.py`. Tests get a ready app and client from the fixtures in `tests/conftest.py`.
- The generated dev module `src/wumpus_archiver/api/_dev_app.py` is a disposable cache; `wumpus-archiver dev` rewrites it.

## Agent skills

### Issue tracker

Issues live on GitHub (`JungleM0nkey/wumpus-archiver`); tickets from a plan are sub-issues of an epic, labelled `ready-for-agent`, each with a `Blocked by` list. See `docs/agents/issue-tracker.md`.

### Domain docs

Single-context: `GLOSSARY.md` at the root and ADRs under `docs/adr/`. Read both before exploring. See `docs/agents/domain.md`.
