"""
Migration: JSONL memory.json → SQLite memory.db

One-time script. Run:
    python migrate.py [--source /path/to/memory.json] [--target /path/to/memory.db]

Default:
    source: ~/.kiro/memory.json (or MEMORY_FILE_PATH env)
    target: ~/.kiro/memory.db (or MEMORY_DB_PATH env)
"""

import json
import os
import sys
from pathlib import Path

import db


def migrate(source_path: str, target_path: str):
    """Migrate JSONL memory file to SQLite database."""

    if not os.path.exists(source_path):
        print(f"❌ Source not found: {source_path}")
        sys.exit(1)

    if os.path.exists(target_path):
        print(f"⚠️  Target already exists: {target_path}")
        response = input("   Overwrite? (y/N): ").strip().lower()
        if response != "y":
            print("   Aborted.")
            sys.exit(0)
        os.remove(target_path)

    # Initialize fresh DB
    db.init_db(target_path)
    conn = db.get_connection(target_path)

    entities = {}  # name → id
    relations = []
    entity_count = 0
    obs_count = 0
    rel_count = 0

    print(f"📖 Reading: {source_path}")

    with open(source_path) as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"   ⚠️  Skipping line {line_num}: {e}")
                continue

            if record.get("type") == "entity":
                name = record["name"]
                entity_type = record.get("entityType", "unknown")

                cur = conn.execute(
                    "INSERT OR IGNORE INTO entities (name, entity_type) VALUES (?, ?)",
                    (name, entity_type)
                )
                if cur.rowcount > 0:
                    entity_id = cur.lastrowid
                else:
                    row = conn.execute("SELECT id FROM entities WHERE name = ?", (name,)).fetchone()
                    entity_id = row["id"]

                entities[name] = entity_id
                entity_count += 1

                for obs in record.get("observations", []):
                    conn.execute(
                        "INSERT INTO observations (entity_id, content) VALUES (?, ?)",
                        (entity_id, obs)
                    )
                    obs_count += 1

            elif record.get("type") == "relation":
                relations.append(record)

    # Insert relations (after all entities exist)
    for rel in relations:
        from_name = rel.get("from")
        to_name = rel.get("to")
        rel_type = rel.get("relationType", "related_to")

        from_id = entities.get(from_name)
        to_id = entities.get(to_name)

        if from_id and to_id:
            conn.execute(
                "INSERT OR IGNORE INTO relations (from_entity_id, to_entity_id, relation_type) VALUES (?, ?, ?)",
                (from_id, to_id, rel_type)
            )
            rel_count += 1
        else:
            missing = []
            if not from_id:
                missing.append(f"from='{from_name}'")
            if not to_id:
                missing.append(f"to='{to_name}'")
            print(f"   ⚠️  Skipping relation: {', '.join(missing)} not found")

    conn.commit()

    # Verify
    actual_entities = conn.execute("SELECT COUNT(*) as c FROM entities").fetchone()["c"]
    actual_obs = conn.execute("SELECT COUNT(*) as c FROM observations").fetchone()["c"]
    actual_rels = conn.execute("SELECT COUNT(*) as c FROM relations").fetchone()["c"]

    conn.close()

    print(f"\n✅ Migration complete!")
    print(f"   Database: {target_path}")
    print(f"   Entities:     {actual_entities}")
    print(f"   Observations: {actual_obs}")
    print(f"   Relations:    {actual_rels}")
    print(f"   File size:    {os.path.getsize(target_path) / 1024:.0f} KB")
    print(f"\n💡 Next: update .kiro/settings/mcp.json to use the new server")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Migrate JSONL memory to SQLite")
    parser.add_argument("--source", default=os.environ.get(
        "MEMORY_FILE_PATH",
        str(Path.home() / "dev" / "breakingthecloud" / ".kiro" / "memory.json")
    ))
    parser.add_argument("--target", default=os.environ.get(
        "MEMORY_DB_PATH",
        str(Path.home() / "dev" / "breakingthecloud" / ".kiro" / "memory.db")
    ))

    args = parser.parse_args()
    migrate(args.source, args.target)
