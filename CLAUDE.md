# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A SQLite to PostgreSQL synchronizer that automatically syncs daily SQLite databases to a remote PostgreSQL instance. Supports automatic schema discovery, incremental synchronization, and dynamic column addition.

## Development Setup

```bash
# Create virtual environment and install dependencies
python3 -m venv venv
source venv/bin/activate
pip install -r synchronizer/requirements.txt

# Configure application
cd synchronizer
cp config.yaml.example config.yaml
# Edit config.yaml with your database credentials and settings
```

## Docker Setup

```bash
# 1. Configure your SQLite databases directory
# Edit docker-compose.yml and replace /path/to/your/sqlite/dbs
# with the actual path to your SQLite databases folder

# 2. Start both PostgreSQL and synchronizer services
docker-compose up -d

# 3. View logs
docker-compose logs -f synchronizer

# 4. Stop services
docker-compose down
```

**Important**: The SQLite databases directory is mounted as read-only in the container. Make sure the path in `docker-compose.yml` points to the directory containing your `YYYY_MM_DD.db` files.

## Commands

### Running the synchronizer

```bash
cd synchronizer
python sync-sql.py
```

### Code quality checks (MANDATORY before completing any task)

```bash
# Run pylint on a specific file or module
pylint synchronizer/module_name.py

# Run pyright in strict mode (MANDATORY)
pyright --pythonversion 3.10

# Run all tests
pytest

# Run a specific test file
pytest tests/test_specific.py

# Run a specific test function
pytest tests/test_specific.py::test_function_name
```

All code MUST pass pylint and pyright (strict mode) before being considered complete.

## Code Quality Rules (MANDATORY)

- All Python code MUST pass:
  - pylint (no errors)
  - pyright in strict mode (no errors)
- Any pylint or pyright error MUST be fixed before considering the task complete
- Do not ignore or disable errors unless explicitly instructed
- All public functions and methods MUST have explicit type annotations
- Avoid `Any` unless absolutely necessary and justified

## Testing Requirements (MANDATORY)

- Any new feature or behavior change MUST include pytest tests
- Tests MUST:
  - Be deterministic
  - Cover success and failure cases
  - Be placed in the appropriate `tests/` directory
- Do not modify existing tests unless required

## Architecture

### Module Responsibilities

The codebase follows a layered architecture with clear separation of concerns:

- **sync-sql.py**: Entry point with main loop, connection management, and error recovery with exponential backoff
- **synchronizer.py**: Orchestrates synchronization flow - loads timestamp, fetches data, ensures schema, inserts data, saves timestamp
- **database.py**: PostgreSQL operations - connection with retry, type conversion (SQLite→PostgreSQL), table creation/alteration
- **sqlite_manager.py**: SQLite operations - reads daily files (YYYY_MM_DD.db format), auto-discovers tables/columns, fetches incremental data
- **file_manager.py**: Atomic timestamp persistence using temporary file + rename pattern
- **config.py**: Centralized configuration loaded from config.yaml file

### Data Flow

1. **Load timestamp**: Read last successful sync time from `data/lastSuccessFullTime.json`
2. **Fetch data**: Query all relevant SQLite files for data newer than timestamp
3. **Schema discovery**: Auto-detect columns and types from SQLite tables
4. **Ensure schema**: Create or alter PostgreSQL table to match SQLite structure
5. **Bulk insert**: Use PostgreSQL COPY command for high-performance insertion
6. **Save timestamp**: Atomically write new timestamp to JSON file

### Key Design Patterns

- **Atomic writes**: Timestamp file uses write-to-temp-then-rename pattern for crash safety
- **Exponential backoff**: Connection retries use exponential backoff with max delay cap
- **Transaction safety**: All PostgreSQL operations wrapped in transactions with rollback on error
- **Type mapping**: SQLite types automatically converted to appropriate PostgreSQL types
- **Schema evolution**: Missing columns automatically added to PostgreSQL table without manual intervention

### Important Implementation Details

- SQLite files MUST be named in format `YYYY_MM_DD.db` (e.g., `2026_01_25.db`)
- Timestamp column detection requires column name containing "time" or "date" (case-insensitive)
- COPY command uses tab separator with special escaping for NULL values (`\N`)
- Row factory set to `sqlite3.Row` for named column access
- PostgreSQL connection timeout configured via `CONNECT_TIMEOUT` in config

## Style

- Prefer explicit code over clever code
- Follow existing project structure and conventions
- Use type aliases for complex types (e.g., `RowData = tuple[Any, ...]`)
