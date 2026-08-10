import json
from pathlib import Path
import sqlite3

db_path = Path.home() / ".local/share/charon/charon_state.db"

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

# Query all mapped skill actions per agent
cursor = conn.execute("SELECT agent_id, action_name FROM agent_skill_map;")
agent_tools = {}

for row in cursor.fetchall():
    aid = row["agent_id"]
    action = row["action_name"]
    if aid not in agent_tools:
        agent_tools[aid] = []

    agent_tools[aid].append({
        "name": action,
        "tool_name": action,
        "enabled": True
    })

# Backfill active_tools in agent_registry
with conn:
    for agent_id, tools in agent_tools.items():
        tools_json = json.dumps(tools)
        conn.execute(
            "UPDATE agent_registry SET active_tools = ?, priority_weight = 1.0 WHERE agent_id = ?;",
            (tools_json, agent_id)
        )

conn.close()
print(f"Successfully backfilled active_tools for {len(agent_tools)} agents.")