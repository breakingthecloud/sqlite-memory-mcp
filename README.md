# sqlite-memory-mcp

SQLite-backed MCP memory server with FTS5 full-text search. Drop-in replacement for `@modelcontextprotocol/server-memory`.

## Why

- **ACID** — no more JSONL corruption
- **FTS5 ranked search** — BM25 relevance, not just substring match
- **Auto timestamps** — every observation gets `created_at` automatically
- **Archive old** — observations >60 days excluded from `read_graph` (still searchable)
- **compact_graph** — read only N most recent obs per entity (81% context reduction)
- **0ms latency** — local SQLite file, no network calls

## Install

```bash
cd sqlite-memory-mcp
uv venv --python 3.11 .venv
source .venv/bin/activate
uv pip install -e .
```

## Migrate from JSONL

```bash
python migrate.py --source /path/to/memory.json --target /path/to/memory.db
```

## Configure Kiro

`.kiro/settings/mcp.json`:
```json
{
  "mcpServers": {
    "memory": {
      "command": "/path/to/sqlite-memory-mcp/.venv/bin/python",
      "args": ["/path/to/sqlite-memory-mcp/server.py"],
      "env": {
        "MEMORY_DB_PATH": "/path/to/.kiro/memory.db"
      }
    }
  }
}
```

## Tools (14 total)

### Backward-compatible (same as JSONL server)
- `create_entities` — create entities with observations
- `add_observations` — add obs to existing entities (auto-timestamp)
- `delete_entities` — delete entities (cascades)
- `delete_observations` — delete specific obs by content
- `delete_relations` — delete relations
- `create_relations` — create relations
- `open_nodes` — get entities by name
- `search_nodes` — FTS5 ranked search (BM25)
- `read_graph` — full graph (non-archived only)

### New
- `search_by_date` — filter obs by date range (ISO YYYY-MM-DD)
- `get_recent` — last N observations (newest first)
- `archive_old` — archive obs older than N days
- `stats` — entity/obs/relation counts, largest entities, dates
- `compact_graph` — read_graph but max N obs per entity

## Backup

```bash
./backup-memory.sh
# Creates timestamped copy in memory-backups/, retains 30 days
```

## File Structure

```
sqlite-memory-mcp/
├── server.py          # MCP server entry point
├── db.py              # SQLite operations
├── schema.sql         # DDL
├── migrate.py         # JSONL → SQLite migration
├── backup-memory.sh   # Backup script
├── pyproject.toml     # uv/pip deps
└── .venv/             # Python venv (recreate with uv)
```
