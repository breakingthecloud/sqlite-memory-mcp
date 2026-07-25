"""
SQLite Memory MCP Server — Drop-in replacement for @modelcontextprotocol/server-memory

Usage:
    python server.py

Environment:
    MEMORY_DB_PATH — Path to SQLite database (default: ~/.kiro/memory.db)

Tools (backward-compatible):
    create_entities, add_observations, delete_entities, delete_observations,
    delete_relations, create_relations, open_nodes, search_nodes, read_graph

New tools:
    search_by_date, get_recent, archive_old, stats, compact_graph
"""

import json
import os
import sys
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

import db

# Initialize
server = Server("sqlite-memory-mcp")
DB_PATH = os.environ.get("MEMORY_DB_PATH", db.DEFAULT_DB_PATH)

# Ensure DB exists with schema
db.init_db(DB_PATH)


def get_conn():
    return db.get_connection(DB_PATH)


# ─── Tool Definitions ────────────────────────────────────────────────────


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="create_entities",
            description="Create multiple new entities in the knowledge graph",
            inputSchema={
                "type": "object",
                "properties": {
                    "entities": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string", "description": "The name of the entity"},
                                "entityType": {"type": "string", "description": "The type of the entity"},
                                "observations": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "An array of observation contents",
                                },
                            },
                            "required": ["name", "entityType", "observations"],
                        },
                    }
                },
                "required": ["entities"],
            },
        ),
        Tool(
            name="add_observations",
            description="Add new observations to existing entities in the knowledge graph",
            inputSchema={
                "type": "object",
                "properties": {
                    "observations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "entityName": {"type": "string", "description": "The name of the entity"},
                                "contents": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "An array of observation contents to add",
                                },
                            },
                            "required": ["entityName", "contents"],
                        },
                    }
                },
                "required": ["observations"],
            },
        ),
        Tool(
            name="delete_entities",
            description="Delete multiple entities and their associated relations from the knowledge graph",
            inputSchema={
                "type": "object",
                "properties": {
                    "entityNames": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "An array of entity names to delete",
                    }
                },
                "required": ["entityNames"],
            },
        ),
        Tool(
            name="delete_observations",
            description="Delete specific observations from entities in the knowledge graph",
            inputSchema={
                "type": "object",
                "properties": {
                    "deletions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "entityName": {"type": "string"},
                                "observations": {"type": "array", "items": {"type": "string"}},
                            },
                            "required": ["entityName", "observations"],
                        },
                    }
                },
                "required": ["deletions"],
            },
        ),
        Tool(
            name="delete_relations",
            description="Delete multiple relations from the knowledge graph",
            inputSchema={
                "type": "object",
                "properties": {
                    "relations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "from": {"type": "string"},
                                "to": {"type": "string"},
                                "relationType": {"type": "string"},
                            },
                            "required": ["from", "to", "relationType"],
                        },
                    }
                },
                "required": ["relations"],
            },
        ),
        Tool(
            name="create_relations",
            description="Create multiple new relations between entities in the knowledge graph",
            inputSchema={
                "type": "object",
                "properties": {
                    "relations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "from": {"type": "string"},
                                "to": {"type": "string"},
                                "relationType": {"type": "string"},
                            },
                            "required": ["from", "to", "relationType"],
                        },
                    }
                },
                "required": ["relations"],
            },
        ),
        Tool(
            name="open_nodes",
            description="Open specific nodes in the knowledge graph by their names",
            inputSchema={
                "type": "object",
                "properties": {
                    "names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "An array of entity names to retrieve",
                    }
                },
                "required": ["names"],
            },
        ),
        Tool(
            name="search_nodes",
            description="Search for nodes in the knowledge graph based on a query (FTS5 ranked)",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query"},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="read_graph",
            description="Read the entire knowledge graph (non-archived observations only)",
            inputSchema={"type": "object", "properties": {}},
        ),
        # ─── New tools ───
        Tool(
            name="search_by_date",
            description="Search observations by date range (ISO format: YYYY-MM-DD)",
            inputSchema={
                "type": "object",
                "properties": {
                    "start_date": {"type": "string", "description": "Start date (YYYY-MM-DD)"},
                    "end_date": {"type": "string", "description": "End date (YYYY-MM-DD)"},
                    "entity_name": {"type": "string", "description": "Optional: filter by entity name"},
                },
                "required": ["start_date", "end_date"],
            },
        ),
        Tool(
            name="get_recent",
            description="Get N most recent observations (newest first)",
            inputSchema={
                "type": "object",
                "properties": {
                    "n": {"type": "integer", "description": "Number of observations to return (default 10)"},
                    "entity_name": {"type": "string", "description": "Optional: filter by entity name"},
                },
            },
        ),
        Tool(
            name="archive_old",
            description="Archive observations older than N days (excluded from read_graph)",
            inputSchema={
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "Archive obs older than N days (default 60)"},
                },
            },
        ),
        Tool(
            name="stats",
            description="Return knowledge graph statistics (counts, sizes, dates)",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="compact_graph",
            description="Read graph with max N observations per entity (most recent only)",
            inputSchema={
                "type": "object",
                "properties": {
                    "max_obs_per_entity": {
                        "type": "integer",
                        "description": "Max observations per entity (default 20)",
                    },
                },
            },
        ),
    ]


# ─── Tool Handlers ───────────────────────────────────────────────────────


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    conn = get_conn()
    try:
        result = _handle_tool(conn, name, arguments)
        return [TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]
    finally:
        conn.close()


def _handle_tool(conn, name: str, arguments: dict):
    if name == "create_entities":
        results = []
        for entity_data in arguments["entities"]:
            entity_id = db.create_entity(conn, entity_data["name"], entity_data["entityType"])
            if entity_data.get("observations"):
                db.add_observations(conn, entity_data["name"], entity_data["observations"])
            results.append({"name": entity_data["name"], "id": entity_id})
        return results

    elif name == "add_observations":
        results = []
        for obs_data in arguments["observations"]:
            count = db.add_observations(conn, obs_data["entityName"], obs_data["contents"])
            results.append({"entityName": obs_data["entityName"], "addedObservations": obs_data["contents"][:count]})
        return results

    elif name == "delete_entities":
        deleted = []
        for entity_name in arguments["entityNames"]:
            if db.delete_entity(conn, entity_name):
                deleted.append(entity_name)
        return {"deleted": deleted}

    elif name == "delete_observations":
        results = []
        for deletion in arguments["deletions"]:
            count = db.delete_observations(conn, deletion["entityName"], deletion["observations"])
            results.append({"entityName": deletion["entityName"], "deletedCount": count})
        return results

    elif name == "delete_relations":
        deleted = 0
        for rel in arguments["relations"]:
            if db.delete_relation(conn, rel["from"], rel["to"], rel["relationType"]):
                deleted += 1
        return {"deletedCount": deleted}

    elif name == "create_relations":
        created = 0
        for rel in arguments["relations"]:
            if db.create_relation(conn, rel["from"], rel["to"], rel["relationType"]):
                created += 1
        return {"createdCount": created}

    elif name == "open_nodes":
        entities = []
        for name_str in arguments["names"]:
            entity = db.get_entity_by_name(conn, name_str)
            if entity:
                entities.append(entity)
        return {"entities": entities}

    elif name == "search_nodes":
        query = arguments["query"]
        entities = db.search_nodes(conn, query)
        return {"entities": entities}

    elif name == "read_graph":
        return db.read_graph(conn)

    # ─── New tools ───
    elif name == "search_by_date":
        results = db.search_by_date(
            conn,
            arguments["start_date"],
            arguments["end_date"],
            arguments.get("entity_name"),
        )
        return {"results": results, "count": len(results)}

    elif name == "get_recent":
        results = db.get_recent(
            conn,
            arguments.get("n", 10),
            arguments.get("entity_name"),
        )
        return {"results": results, "count": len(results)}

    elif name == "archive_old":
        count = db.archive_old(conn, arguments.get("days", 60))
        return {"archived_count": count}

    elif name == "stats":
        return db.get_stats(conn)

    elif name == "compact_graph":
        return db.compact_graph(conn, arguments.get("max_obs_per_entity", 20))

    else:
        return {"error": f"Unknown tool: {name}"}


# ─── Main ────────────────────────────────────────────────────────────────


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
