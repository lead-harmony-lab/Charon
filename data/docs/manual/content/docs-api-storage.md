### Docs API & Storage Layer

**Overview**
The backend architecture for the Knowledge Base relies on a lightweight, file-based persistence layer served via FastAPI. The routing is handled in `../../../../charon/gateway/routes/docs.py` and mounted at the `/v1/docs` prefix.

**Storage Infrastructure**
Instead of a relational database, documentation is stored as static JSON files to ensure human-readability, easy version control, and system portability. Directories are auto-generated on startup if they do not exist:
* **ADRs**: Stored as flat files in `data/docs/adrs/*.json`.
* **Specs**: Stored as flat files in `data/docs/specs/*.json`.
* **Manual**: Stored as a single recursive JSON tree in `data/docs/manual/manual.json`.

**FastAPI Routing Layer**
The router (`APIRouter(prefix="/v1/docs")`) exposes CRUD operations synced with the frontend's `authFetch` calls:
* **GET (`/adrs`, `/specs`, `/manual`)**: Iterates through the respective directories, parses the `.json` files, sorts them (by ID, Date, or alphabetically), and serves them to the viewer components.
* **POST (`/adrs`, `/specs`)**: Creates new document entities. Explicitly checks if a file already exists to prevent accidental overwrites, returning a `409 Conflict` if the ID is taken.
* **PUT (`/adrs/{doc_id}`, `/specs/{doc_id}`, `/manual`)**: Saves updates from the editor panels. Uses `json.dumps(data, indent=2)` when writing to disk to preserve clean, readable diffs for git history.