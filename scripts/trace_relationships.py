import shutil
from charon.core.skills.librarian import SkillLibrarian

librarian = SkillLibrarian.get_instance()

# 1. Inspect what Librarian loaded into memory
details = librarian.get_action_details("answer_query")
print("=== Librarian Memory State ===")
print("Action Details:", details)

# 2. Check binary host verification
print("\n=== Host Binary Check ===")
for binary in ["python3", "ollama"]:
    path = shutil.which(binary)
    print(f"Binary '{binary}': {'FOUND at ' + path if path else 'NOT FOUND IN PATH'}")

# 3. Test agent resolution
if hasattr(librarian, "resolve_agent_id_for_role"):
    print("\n=== Role Resolution ===")
    print("system_generalist ->", librarian.resolve_agent_id_for_role("system_generalist"))