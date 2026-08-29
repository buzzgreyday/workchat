# Backend

FastAPI backend using SQLAlchemy, Alembic, and PostgreSQL.

## Types

`app/` is type-checked with mypy, configured in `pyproject.toml`. There is no CI
yet, so nothing runs this but you:

```bash
uv run mypy
```

The settings are strict enough to be worth having — every function in a request
path declares what it takes and returns, and a value that quietly becomes `Any`
is an error. `build_index` and the logging package are exempt from the
annotation requirement: both are script-shaped rather than request-shaped.

## Tests

Tests use an in-memory SQLite database and a mocked OpenAI client, so they
run without any external service.

```bash
uv sync                # installs the `dev` dependency group (pytest, aiosqlite)
uv run pytest
```

**pyenv gotcha:** the tests need the `_sqlite3` stdlib module. If your
Python was built by pyenv without `sqlite-devel` installed, `pytest` will
fail with `ModuleNotFoundError: No module named '_sqlite3'`. Fix once with:

```bash
sudo dnf install sqlite-devel      # or apt-get install libsqlite3-dev
pyenv install --force 3.13.1
```

Or run the suite against your system Python:

```bash
uv run --python /usr/bin/python3 pytest
```