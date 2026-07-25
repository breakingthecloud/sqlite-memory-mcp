"""
SQLite Memory MCP — Database Operations

All CRUD + FTS5 search + archive functionality.
Designed to be a drop-in replacement for @modelcontextprotocol/server-memory.
"""

import sqlite3
import os
from pathlib import Path
from typing import Optional

# Default DB path
DEFAULT_DB_PATH = os.environ.get(
    "MEMORY_DB_PATH",
    str(Path.home() / ".kiro" / "memory.db")
)

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def get_connection(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Get a connection with WAL mode and foreign keys enabled."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str = DEFAULT_DB_PATH) -> None:
    """Initialize the database with schema if tables don't exist."""
    conn = get_connection(db_path)
    with open(SCHEMA_PATH) as f:
        conn.executescript(f.read())
    conn.close()


# ─── Entities ────────────────────────────────────────────────────────────


def create_entity(conn: sqlite3.Connection, name: str, entity_type: str) -> int:
    """Create an entity. Returns entity ID."""
    cur = conn.execute(
        "INSERT OR IGNORE INTO entities (name, entity_type) VALUES (?, ?)",
        (name, entity_type)
    )
    if cur.rowcount == 0:
        # Already exists, get ID
        row = conn.execute("SELECT id FROM entities WHERE name = ?", (name,)).fetchone()
        return row["id"]
    conn.commit()
    return cur.lastrowid


def get_entity_by_name(conn: sqlite3.Connection, name: str) -> Optional[dict]:
    """Get an entity with its non-archived observations."""
    row = conn.execute("SELECT * FROM entities WHERE name = ?", (name,)).fetchone()
    if not row:
        return None

    observations = conn.execute(
        "SELECT content FROM observations WHERE entity_id = ? AND archived = 0 ORDER BY created_at",
        (row["id"],)
    ).fetchall()

    return {
        "name": row["name"],
        "entityType": row["entity_type"],
        "observations": [o["content"] for o in observations],
    }


def delete_entity(conn: sqlite3.Connection, name: str) -> bool:
    """Delete an entity and cascade its observations and relations."""
    row = conn.execute("SELECT id FROM entities WHERE name = ?", (name,)).fetchone()
    if not row:
        return False
    conn.execute("DELETE FROM entities WHERE id = ?", (row["id"],))
    conn.commit()
    return True


# ─── Observations ────────────────────────────────────────────────────────


def add_observations(conn: sqlite3.Connection, entity_name: str, contents: list[str]) -> int:
    """Add observations to an entity. Returns count added."""
    row = conn.execute("SELECT id FROM entities WHERE name = ?", (entity_name,)).fetchone()
    if not row:
        return 0

    entity_id = row["id"]
    count = 0
    for content in contents:
        # Avoid exact duplicates
        existing = conn.execute(
            "SELECT id FROM observations WHERE entity_id = ? AND content = ?",
            (entity_id, content)
        ).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO observations (entity_id, content) VALUES (?, ?)",
                (entity_id, content)
            )
            count += 1

    if count > 0:
        conn.execute(
            "UPDATE entities SET updated_at = datetime('now') WHERE id = ?",
            (entity_id,)
        )
        conn.commit()
    return count


def delete_observations(conn: sqlite3.Connection, entity_name: str, contents: list[str]) -> int:
    """Delete specific observations by content match. Returns count deleted."""
    row = conn.execute("SELECT id FROM entities WHERE name = ?", (entity_name,)).fetchone()
    if not row:
        return 0

    entity_id = row["id"]
    count = 0
    for content in contents:
        cur = conn.execute(
            "DELETE FROM observations WHERE entity_id = ? AND content = ?",
            (entity_id, content)
        )
        count += cur.rowcount

    if count > 0:
        conn.commit()
    return count


# ─── Relations ───────────────────────────────────────────────────────────


def create_relation(conn: sqlite3.Connection, from_name: str, to_name: str, relation_type: str) -> bool:
    """Create a relation between two entities."""
    from_row = conn.execute("SELECT id FROM entities WHERE name = ?", (from_name,)).fetchone()
    to_row = conn.execute("SELECT id FROM entities WHERE name = ?", (to_name,)).fetchone()

    if not from_row or not to_row:
        return False

    conn.execute(
        "INSERT OR IGNORE INTO relations (from_entity_id, to_entity_id, relation_type) VALUES (?, ?, ?)",
        (from_row["id"], to_row["id"], relation_type)
    )
    conn.commit()
    return True


def delete_relation(conn: sqlite3.Connection, from_name: str, to_name: str, relation_type: str) -> bool:
    """Delete a relation."""
    from_row = conn.execute("SELECT id FROM entities WHERE name = ?", (from_name,)).fetchone()
    to_row = conn.execute("SELECT id FROM entities WHERE name = ?", (to_name,)).fetchone()

    if not from_row or not to_row:
        return False

    cur = conn.execute(
        "DELETE FROM relations WHERE from_entity_id = ? AND to_entity_id = ? AND relation_type = ?",
        (from_row["id"], to_row["id"], relation_type)
    )
    conn.commit()
    return cur.rowcount > 0


# ─── Search ──────────────────────────────────────────────────────────────


def search_nodes(conn: sqlite3.Connection, query: str, limit: int = 20) -> list[dict]:
    """FTS5 ranked search across entity names, types, and observation content.
    Returns entities with matching observations, ranked by BM25 relevance.
    """
    results = {}

    # Search in observations (FTS5 ranked)
    rows = conn.execute("""
        SELECT o.entity_id, o.content, rank
        FROM observations_fts fts
        JOIN observations o ON o.id = fts.rowid
        WHERE observations_fts MATCH ? AND o.archived = 0
        ORDER BY rank
        LIMIT ?
    """, (query, limit * 3)).fetchall()  # fetch more, dedup by entity

    for row in rows:
        entity_id = row["entity_id"]
        if entity_id not in results:
            entity = conn.execute("SELECT * FROM entities WHERE id = ?", (entity_id,)).fetchone()
            if entity:
                results[entity_id] = {
                    "name": entity["name"],
                    "entityType": entity["entity_type"],
                    "observations": [],
                }
        if entity_id in results:
            results[entity_id]["observations"].append(row["content"])

    # Also search entity names and types (simple LIKE)
    name_rows = conn.execute(
        "SELECT * FROM entities WHERE name LIKE ? OR entity_type LIKE ? LIMIT ?",
        (f"%{query}%", f"%{query}%", limit)
    ).fetchall()

    for row in name_rows:
        if row["id"] not in results:
            observations = conn.execute(
                "SELECT content FROM observations WHERE entity_id = ? AND archived = 0 ORDER BY created_at DESC LIMIT 10",
                (row["id"],)
            ).fetchall()
            results[row["id"]] = {
                "name": row["name"],
                "entityType": row["entity_type"],
                "observations": [o["content"] for o in observations],
            }

    # Return top N entities
    return list(results.values())[:limit]


# ─── Graph Read ──────────────────────────────────────────────────────────


def read_graph(conn: sqlite3.Connection) -> dict:
    """Read full active graph (non-archived observations only)."""
    entities = []
    for entity in conn.execute("SELECT * FROM entities ORDER BY name").fetchall():
        observations = conn.execute(
            "SELECT content FROM observations WHERE entity_id = ? AND archived = 0 ORDER BY created_at",
            (entity["id"],)
        ).fetchall()
        entities.append({
            "name": entity["name"],
            "entityType": entity["entity_type"],
            "observations": [o["content"] for o in observations],
        })

    relations = []
    for rel in conn.execute("""
        SELECT e1.name as from_name, e2.name as to_name, r.relation_type
        FROM relations r
        JOIN entities e1 ON e1.id = r.from_entity_id
        JOIN entities e2 ON e2.id = r.to_entity_id
        ORDER BY e1.name
    """).fetchall():
        relations.append({
            "from": rel["from_name"],
            "to": rel["to_name"],
            "relationType": rel["relation_type"],
        })

    return {"entities": entities, "relations": relations}


# ─── New Tools (Phase B) ─────────────────────────────────────────────────


def search_by_date(conn: sqlite3.Connection, start_date: str, end_date: str,
                   entity_name: Optional[str] = None) -> list[dict]:
    """Search observations by date range."""
    if entity_name:
        row = conn.execute("SELECT id FROM entities WHERE name = ?", (entity_name,)).fetchone()
        if not row:
            return []
        rows = conn.execute("""
            SELECT e.name, o.content, o.created_at
            FROM observations o JOIN entities e ON e.id = o.entity_id
            WHERE o.entity_id = ? AND o.created_at BETWEEN ? AND ?
            ORDER BY o.created_at DESC
        """, (row["id"], start_date, end_date + " 23:59:59")).fetchall()
    else:
        rows = conn.execute("""
            SELECT e.name, o.content, o.created_at
            FROM observations o JOIN entities e ON e.id = o.entity_id
            WHERE o.created_at BETWEEN ? AND ?
            ORDER BY o.created_at DESC
        """, (start_date, end_date + " 23:59:59")).fetchall()

    return [{"entity": r["name"], "content": r["content"], "date": r["created_at"]} for r in rows]


def get_recent(conn: sqlite3.Connection, n: int = 10, entity_name: Optional[str] = None) -> list[dict]:
    """Get N most recent observations."""
    if entity_name:
        row = conn.execute("SELECT id FROM entities WHERE name = ?", (entity_name,)).fetchone()
        if not row:
            return []
        rows = conn.execute("""
            SELECT e.name, o.content, o.created_at
            FROM observations o JOIN entities e ON e.id = o.entity_id
            WHERE o.entity_id = ? AND o.archived = 0
            ORDER BY o.created_at DESC LIMIT ?
        """, (row["id"], n)).fetchall()
    else:
        rows = conn.execute("""
            SELECT e.name, o.content, o.created_at
            FROM observations o JOIN entities e ON e.id = o.entity_id
            WHERE o.archived = 0
            ORDER BY o.created_at DESC LIMIT ?
        """, (n,)).fetchall()

    return [{"entity": r["name"], "content": r["content"], "date": r["created_at"]} for r in rows]


def archive_old(conn: sqlite3.Connection, days: int = 60) -> int:
    """Archive observations older than N days. Returns count archived."""
    cur = conn.execute("""
        UPDATE observations SET archived = 1
        WHERE archived = 0 AND created_at < datetime('now', ?)
    """, (f"-{days} days",))
    conn.commit()
    return cur.rowcount


def get_stats(conn: sqlite3.Connection) -> dict:
    """Return graph statistics."""
    entity_count = conn.execute("SELECT COUNT(*) as c FROM entities").fetchone()["c"]
    obs_active = conn.execute("SELECT COUNT(*) as c FROM observations WHERE archived = 0").fetchone()["c"]
    obs_archived = conn.execute("SELECT COUNT(*) as c FROM observations WHERE archived = 1").fetchone()["c"]
    rel_count = conn.execute("SELECT COUNT(*) as c FROM relations").fetchone()["c"]

    largest = conn.execute("""
        SELECT e.name, COUNT(o.id) as obs_count
        FROM entities e LEFT JOIN observations o ON o.entity_id = e.id AND o.archived = 0
        GROUP BY e.id ORDER BY obs_count DESC LIMIT 5
    """).fetchall()

    oldest = conn.execute("SELECT MIN(created_at) as d FROM observations").fetchone()["d"]
    newest = conn.execute("SELECT MAX(created_at) as d FROM observations").fetchone()["d"]

    return {
        "entities": entity_count,
        "observations_active": obs_active,
        "observations_archived": obs_archived,
        "relations": rel_count,
        "largest_entities": [{"name": r["name"], "observations": r["obs_count"]} for r in largest],
        "oldest_observation": oldest,
        "newest_observation": newest,
    }


def compact_graph(conn: sqlite3.Connection, max_obs_per_entity: int = 20) -> dict:
    """Read graph with max N observations per entity (most recent)."""
    entities = []
    for entity in conn.execute("SELECT * FROM entities ORDER BY name").fetchall():
        observations = conn.execute(
            "SELECT content FROM observations WHERE entity_id = ? AND archived = 0 ORDER BY created_at DESC LIMIT ?",
            (entity["id"], max_obs_per_entity)
        ).fetchall()
        entities.append({
            "name": entity["name"],
            "entityType": entity["entity_type"],
            "observations": [o["content"] for o in observations],
        })

    relations = []
    for rel in conn.execute("""
        SELECT e1.name as from_name, e2.name as to_name, r.relation_type
        FROM relations r
        JOIN entities e1 ON e1.id = r.from_entity_id
        JOIN entities e2 ON e2.id = r.to_entity_id
    """).fetchall():
        relations.append({
            "from": rel["from_name"],
            "to": rel["to_name"],
            "relationType": rel["relation_type"],
        })

    return {"entities": entities, "relations": relations}
