"""
charon/agents/archivist/agent.py
System Version: v0.1.0 | File Revision: 1.5.0

Module: Main TheArchivist agent orchestrator and action routing switch,
inheriting from BaseAgent for standardized probing and capability discovery
and real-time telemetry stream instrumentation. Updated for dynamic intent schemas.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import chromadb

from charon.config.paths import CHROMA_DB_DIR, ensure_ecosystem_directories
from charon.intent import DynamicActionPayload
from charon.agents.base import BaseAgent
from charon.agents.archivist.ledger import LedgerManager
from charon.agents.archivist.datasheets import DatasheetManager

logger = logging.getLogger("CHAROND.Archivist")


class TheArchivist(BaseAgent):
    """Specialist Agent: The Continental Ledger & Semantic Knowledge Vector Store.

    Domain: Persistent memory management, rule retrieval, PDF datasheet
    indexing, and RAG search.
    """

    name: str = "The_Archivist"
    domain: str = "Memory, Vector Ledger & Technical Datasheet RAG"

    SUPPORTED_ACTIONS: Dict[str, List[str]] = {
        "store_record": ["store_record", "record_rule", "add_rule", "save_fact"],
        "search_ledger": ["search_ledger", "query_ledger", "get_rule"],
        "expunge_record": ["expunge_record", "delete_rule", "delete_ledger_rule", "remove_rule"],
        "summarize_ledger": ["summarize_ledger", "get_summary", "list_rules"],
        "index_datasheet": ["index_datasheet", "index_pdf", "ingest_datasheet"],
        "search_datasheets": ["search_datasheets", "query_datasheet", "search_knowledge", "get_datasheet_info"],
    }

    # BaseAgent capability registration
    supported_actions = SUPPORTED_ACTIONS

    def __init__(self, db_path: Optional[Union[str, Path]] = None):
        super().__init__()
        ensure_ecosystem_directories()

        if db_path:
            p = Path(db_path).resolve()
            # If passed a file or path with an extension (e.g., .db), use a parent chroma_db directory
            if p.is_file() or p.suffix:
                target_path = p.parent / "chroma_db"
            else:
                target_path = p
        else:
            target_path = CHROMA_DB_DIR

        target_path.mkdir(parents=True, exist_ok=True)

        self.db_path = target_path
        self.client = chromadb.PersistentClient(path=str(self.db_path))

        # Collection 1: Operational rules & system memory
        self.collection = self.client.get_or_create_collection("ledger")

        # Collection 2: Technical datasheet text chunks & spec memory
        self.datasheet_collection = self.client.get_or_create_collection(
            "datasheet_knowledge"
        )

        # Domain managers
        self._ledger = LedgerManager(self.collection, self.datasheet_collection)
        self._datasheets = DatasheetManager(self.datasheet_collection)

    def health_check(self) -> Dict[str, Any]:
        """Runtime health check verifying ChromaDB connection and collection statistics."""
        try:
            ledger_count = self.collection.count()
            datasheet_count = self.datasheet_collection.count()
            return {
                "healthy": True,
                "status": "Operational",
                "details": {
                    "db_path": str(self.db_path),
                    "ledger_records": ledger_count,
                    "datasheet_chunks": datasheet_count,
                },
            }
        except Exception as e:
            return {
                "healthy": False,
                "status": f"Degraded: ChromaDB error ({e})",
                "details": {"db_path": str(self.db_path)},
            }

    def probe(self, probe_type: str = "full") -> Dict[str, Any]:
        """Coordinator Probing Interface: Exposes agent capabilities, status, and health."""
        probe_type = str(probe_type).lower().strip()
        health_info = self.health_check()

        capabilities_info = {
            "agent_name": self.name,
            "domain": self.domain,
            "payload_schema": "DynamicActionPayload",
            "actions": self.supported_actions,
        }

        if probe_type == "health":
            return health_info
        elif probe_type == "capabilities":
            return capabilities_info

        return {
            "agent": self.name,
            "health": health_info,
            "capabilities": capabilities_info,
        }

    def execute(
        self, action: str, parameters: Dict[str, Any], raw_prompt: str = ""
    ) -> Union[str, Dict[str, Any]]:
        """The primary routing switch for The Archivist, validated against DynamicActionPayload."""
        payload_dict = dict(parameters) if parameters else {}

        clean_action = str(
            action or payload_dict.get("action") or payload_dict.get("call_action", "")
        ).lower().strip()

        # Dynamic Probing Route
        if clean_action in ["probe", "ping", "health", "get_capabilities", "status"]:
            probe_type = payload_dict.get("probe_type", "full")
            return self.probe(probe_type=probe_type)

        # Telemetry: Initial Action Emission
        self.report_trace(
            action=clean_action,
            reasoning_chunk=f"The Archivist initialized for action '{clean_action}'. Parsing parameters...",
        )
        self.report_action(
            action=clean_action,
            details={"parameters": payload_dict, "raw_prompt": raw_prompt},
        )

        if "call_action" not in payload_dict and "action" not in payload_dict:
            payload_dict["call_action"] = clean_action
        if raw_prompt and "query" not in payload_dict and "raw_prompt" not in payload_dict:
            payload_dict["raw_prompt"] = raw_prompt

        try:
            # Parse into DynamicActionPayload
            if "call_action" in payload_dict and "params" in payload_dict:
                payload = DynamicActionPayload.model_validate(payload_dict)
            else:
                call_act = payload_dict.get("call_action") or payload_dict.get("action") or clean_action
                extracted_params = {
                    k: v for k, v in payload_dict.items()
                    if k not in ["call_action", "action", "thought", "memory_candidate"]
                }
                payload = DynamicActionPayload(
                    call_action=call_act,
                    thought=payload_dict.get("thought", ""),
                    params=extracted_params,
                )

            self.report_trace(
                action=clean_action,
                reasoning_chunk="Successfully validated parameters against DynamicActionPayload schema.",
            )
        except Exception as e:
            logger.warning(
                f"[ARCHIVIST] Payload validation fallback ({e}). Building default DynamicActionPayload..."
            )
            payload = DynamicActionPayload(
                call_action=clean_action,
                thought=payload_dict.get("thought", ""),
                params=payload_dict,
            )
            self.report_trace(
                action=clean_action,
                reasoning_chunk=f"Payload validation fallback applied: {e}",
            )

        clean_action = str(payload.call_action or action).lower().strip()

        # Telemetry: Mid-Execution Progress (Routing Phase)
        self.report_progress(
            action=clean_action,
            progress_pct=25.0,
            message=f"Routing request to vector store domain handler for '{clean_action}'...",
        )

        # Prepare parameter mapping for downstream domain managers (ledger / datasheets)
        exec_params = dict(payload.params) if payload.params else {}
        if "query" not in exec_params and "query" in payload_dict:
            exec_params["query"] = payload_dict["query"]
        if "raw_prompt" not in exec_params and raw_prompt:
            exec_params["raw_prompt"] = raw_prompt

        try:
            if clean_action in self.SUPPORTED_ACTIONS["store_record"]:
                self.report_trace(
                    action=clean_action,
                    reasoning_chunk="Writing knowledge record / operational rule into ChromaDB ledger collection.",
                )
                result = self._store_record(exec_params)

            elif clean_action in self.SUPPORTED_ACTIONS["search_ledger"]:
                query_str = exec_params.get("query", "") or raw_prompt
                self.report_trace(
                    action=clean_action,
                    reasoning_chunk=f"Executing semantic vector query against ledger collection with query: '{query_str}'",
                )
                result = self._search_ledger(exec_params, raw_prompt=raw_prompt)

            elif clean_action in self.SUPPORTED_ACTIONS["expunge_record"]:
                target_str = exec_params.get("target_concept") or exec_params.get("query", "")
                self.report_trace(
                    action=clean_action,
                    reasoning_chunk=f"Expunging records matching target pattern: '{target_str}'",
                )
                result = self._expunge_record(exec_params, raw_prompt=raw_prompt)

            elif clean_action in self.SUPPORTED_ACTIONS["summarize_ledger"]:
                self.report_trace(
                    action=clean_action,
                    reasoning_chunk="Summarizing active records and collection metadata in vector ledger.",
                )
                result = self._summarize_ledger(exec_params)

            elif clean_action in self.SUPPORTED_ACTIONS["index_datasheet"]:
                mpn_val = exec_params.get("mpn", "N/A")
                self.report_trace(
                    action=clean_action,
                    reasoning_chunk=f"Parsing, chunking, and embedding datasheet PDF into knowledge store for MPN: {mpn_val}",
                )
                result = self._index_datasheet_action(exec_params)

            elif clean_action in self.SUPPORTED_ACTIONS["search_datasheets"]:
                query_str = exec_params.get("query", "") or raw_prompt
                self.report_trace(
                    action=clean_action,
                    reasoning_chunk=f"Performing technical datasheet RAG search for specs/query: '{query_str}'",
                )
                result = self._search_datasheets(exec_params, raw_prompt=raw_prompt)

            else:
                logger.error(
                    f"The Archivist does not recognize the action: {action}"
                )
                raise ValueError(f"Unknown action '{action}' for The_Archivist")

            # Telemetry: Completion Signal
            self.report_progress(
                action=clean_action,
                progress_pct=100.0,
                message=f"Action '{clean_action}' completed successfully.",
            )
            return result

        except Exception as err:
            logger.error(f"[ARCHIVIST] Error executing action '{clean_action}': {err}", exc_info=True)
            self.report_progress(
                action=clean_action,
                progress_pct=100.0,
                message=f"Action '{clean_action}' failed with error: {err}",
            )
            raise

    def delete_ledger_rule(self, pattern: str) -> str:
        """Public helper to scrub rules/records matching a keyword or phrase."""
        return self._expunge_record(params={"target_concept": pattern})

    # =========================================================================
    # DELEGATED METHODS (Updated type annotations to DynamicActionPayload)
    # =========================================================================

    def _search_ledger(
        self,
        params: Union[DynamicActionPayload, Dict[str, Any]],
        raw_prompt: str = "",
    ) -> str:
        return self._ledger.search_ledger(
            params,
            datasheet_search_fallback=self._search_datasheets,
            raw_prompt=raw_prompt,
        )

    def _store_record(
        self, params: Union[DynamicActionPayload, Dict[str, Any]]
    ) -> str:
        return self._ledger.store_record(params)

    def _expunge_record(
        self,
        params: Union[DynamicActionPayload, Dict[str, Any]],
        raw_prompt: str = "",
    ) -> str:
        return self._ledger.expunge_record(params, raw_prompt=raw_prompt)

    def _summarize_ledger(
        self, params: Union[DynamicActionPayload, Dict[str, Any]]
    ) -> str:
        return self._ledger.summarize_ledger(params)

    def index_pdf_datasheet(
        self,
        pdf_path: Union[str, Path],
        mpn: str,
        metadata: Optional[Dict[str, Any]] = None,
        sha256_hash: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self._datasheets.index_pdf_datasheet(
            pdf_path=pdf_path, mpn=mpn, metadata=metadata, sha256_hash=sha256_hash
        )

    def _index_datasheet_action(
        self, params: Union[DynamicActionPayload, Dict[str, Any]]
    ) -> str:
        return self._datasheets.index_datasheet_action(params)

    def _search_datasheets(
        self,
        params: Union[DynamicActionPayload, Dict[str, Any]],
        raw_prompt: str = "",
    ) -> str:
        return self._datasheets.search_datasheets(params, raw_prompt=raw_prompt)