"""
charon/concierge/telemetry.py
System Version: v3.1.0 | File Revision: 3.1.0

Module: System Telemetry & Heuristic Sensors
Equips the Concierge with the ability to perceive host hardware state (CPU, GPU, RAM),
synthesize long-term idle heuristics based on historical vector memory, read the
ExecutionLedger to maintain session state awareness, and ingest multi-modal sensory context
(window focus, IDE buffer diffs, screen OCR snapshots).
"""

import psutil
import subprocess
import json
import datetime
import logging
import asyncio
from typing import Dict, Any, List, Optional

import chromadb
from charon.config.paths import CONCIERGE_MEMORY_DIR
from charon.telemetry.ledger import ExecutionLedger
from charon.db.connection import get_connection

logger = logging.getLogger("Charon.Concierge.Telemetry")


class TelemetrySensor:
    """Monitors system hardware, execution ledgers, and ingests desktop sensory perception context."""

    def __init__(self):
        # 1. Initialize Memory Context
        try:
            self.chroma_client = chromadb.PersistentClient(path=str(CONCIERGE_MEMORY_DIR))
            self.telemetry_db = self.chroma_client.get_or_create_collection(name="system_telemetry")
            self.heuristics_db = self.chroma_client.get_or_create_collection(name="core_heuristics")
            self.context_db = self.chroma_client.get_or_create_collection(name="desktop_context")
        except Exception as e:
            logger.error(f"Failed to connect to Concierge Memory: {e}")
            self.telemetry_db = None
            self.heuristics_db = None
            self.context_db = None

        # 2. Initialize Audit Ledger Connection
        self.ledger = ExecutionLedger()

    def _get_gpu_usage(self) -> float:
        """Attempts to read GPU utilization. Gracefully fails to 0.0 if unavailable."""
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, check=True
            )
            usages = [float(x.strip()) for x in result.stdout.strip().split('\n') if x.strip().isdigit()]
            return max(usages) if usages else 0.0
        except (subprocess.CalledProcessError, FileNotFoundError):
            return 0.0

    def capture_and_log_metrics(self) -> Dict[str, Any]:
        """Gathers point-in-time system load and writes to episodic memory."""
        now = datetime.datetime.now()

        metrics = {
            "timestamp": now.isoformat(),
            "hour_of_day": now.hour,
            "day_of_week": now.weekday(),
            "cpu_percent": psutil.cpu_percent(interval=1.0),
            "memory_percent": psutil.virtual_memory().percent,
            "gpu_percent": self._get_gpu_usage()
        }

        if self.telemetry_db:
            doc_id = f"telemetry_{now.timestamp()}"
            self.telemetry_db.add(
                ids=[doc_id],
                documents=[json.dumps(metrics)],
                metadatas=[{"hour": now.hour, "type": "hardware_telemetry"}]
            )
            logger.debug(f"Logged system metrics: CPU {metrics['cpu_percent']}% | GPU {metrics['gpu_percent']}%")

        return metrics

    async def get_session_deltas(self, since_iso_timestamp: str) -> Dict[str, int]:
        """
        Reads the Zero-Trust Execution Ledger to count tasks and faults
        that have occurred since the provided ISO timestamp.
        """
        def _query_db() -> Dict[str, int]:
            dt = datetime.datetime.fromisoformat(since_iso_timestamp)
            sql_timestamp = dt.strftime('%Y-%m-%d %H:%M:%S')

            with get_connection(self.ledger.db_path, read_only=True) as conn:
                cursor = conn.execute(
                    """
                    SELECT
                        SUM(CASE WHEN event_type = 'COMPLETED' THEN 1 ELSE 0 END) as tasks,
                        SUM(CASE WHEN event_type IN ('FAILED', 'ESCALATION') THEN 1 ELSE 0 END) as alerts
                    FROM audit_ledger
                    WHERE timestamp > ?;
                    """,
                    (sql_timestamp,)
                )
                row = cursor.fetchone()
                return {
                    "task_count": row["tasks"] or 0,
                    "alert_count": row["alerts"] or 0
                }

        return await asyncio.to_thread(_query_db)

    def synthesize_idle_heuristic(self) -> None:
        """
        Analyzes historical telemetry to identify consistent daily idle windows.
        Creates a semantic rule (heuristic) for task scheduling.
        """
        if not self.telemetry_db or not self.heuristics_db:
            return

        try:
            records = self.telemetry_db.get(where={"type": "hardware_telemetry"})
            if not records or not records.get("documents"):
                logger.info("Insufficient telemetry data for heuristic synthesis.")
                return

            documents = [json.loads(doc) for doc in records["documents"]]

            hourly_load = {hour: {"cpu": [], "gpu": []} for hour in range(24)}
            for doc in documents:
                h = doc["hour_of_day"]
                hourly_load[h]["cpu"].append(doc["cpu_percent"])
                hourly_load[h]["gpu"].append(doc["gpu_percent"])

            idle_hours = []
            for hour, loads in hourly_load.items():
                if not loads["cpu"]:
                    continue
                avg_cpu = sum(loads["cpu"]) / len(loads["cpu"])
                avg_gpu = sum(loads["gpu"]) / len(loads["gpu"])

                if avg_cpu < 15.0 and avg_gpu < 15.0:
                    idle_hours.append(hour)

            if not idle_hours:
                logger.info("No consistent idle window detected yet.")
                return

            idle_hours.sort()
            heuristic_statement = (
                f"SYSTEM IDLE PATTERN DETECTED: Historical telemetry indicates the host machine "
                f"experiences minimal load during hours: {idle_hours}. "
                f"ACTION RULE: All non-critical background maintenance, vector re-indexing, "
                f"and large downloads MUST be scheduled within this time frame."
            )

            self.heuristics_db.upsert(
                ids=["heuristic_maintenance_window"],
                documents=[heuristic_statement],
                metadatas=[{"type": "scheduling_directive", "confidence": "high"}]
            )

            logger.info(f"Synthesized new heuristic: {heuristic_statement}")

        except Exception as e:
            logger.error(f"Failed to synthesize idle heuristic: {e}")

    # =========================================================================
    # Phase 2: Sensory Perception Ingress Handlers
    # =========================================================================

    def log_window_context(
        self,
        app_name: str,
        window_title: str,
        active_file_path: Optional[str] = None,
        pid: Optional[int] = None,
        workspace: int = 0
    ) -> None:
        """
        Ingests active window focus state (GNOME extension / Window Manager).
        Converts the state into a semantic string for Chroma vector retrieval.
        """
        if not self.context_db:
            return

        now = datetime.datetime.now()
        doc_id = f"win_{now.timestamp()}"

        file_clause = f" active file: '{active_file_path}'" if active_file_path else ""
        semantic_document = (
            f"The user is focused on '{app_name}' with window title '{window_title}'.{file_clause}"
        )

        metadata = {
            "timestamp": now.isoformat(),
            "hour_of_day": now.hour,
            "app_name": app_name,
            "window_title": window_title,
            "active_file_path": active_file_path or "",
            "pid": pid or 0,
            "workspace": workspace,
            "type": "gnome_focus_event"
        }

        try:
            self.context_db.add(
                ids=[doc_id],
                documents=[semantic_document],
                metadatas=[metadata]
            )
            logger.debug(f"Logged window context: {app_name} | {window_title}")
        except Exception as e:
            logger.error(f"Failed to log window context to memory: {e}")

    def log_desktop_context(self, app_name: str, window_title: str, workspace: int = 0) -> None:
        """Backward-compatible alias for log_window_context."""
        self.log_window_context(app_name=app_name, window_title=window_title, workspace=workspace)

    def log_ide_context(
        self,
        editor: str,
        file_path: str,
        language: Optional[str] = "python",
        selection_or_diff: Optional[str] = None,
        diagnostics: Optional[List[Dict[str, Any]]] = None
    ) -> None:
        """
        Ingests IDE editor activity, active buffer selections, and compiler LSP diagnostics.
        """
        if not self.context_db:
            return

        now = datetime.datetime.now()
        doc_id = f"ide_{now.timestamp()}"

        diag_summary = ""
        if diagnostics:
            diag_str = "; ".join([d.get("message", "") for d in diagnostics[:3] if "message" in d])
            diag_summary = f" LSP Diagnostics: [{diag_str}]."

        selection_summary = f" Active buffer diff/selection: {selection_or_diff[:200]}..." if selection_or_diff else ""

        semantic_document = (
            f"User working in {editor} on code file '{file_path}' ({language}).{diag_summary}{selection_summary}"
        )

        metadata = {
            "timestamp": now.isoformat(),
            "hour_of_day": now.hour,
            "editor": editor,
            "file_path": file_path,
            "language": language or "python",
            "has_diagnostics": bool(diagnostics),
            "type": "ide_buffer_event"
        }

        try:
            self.context_db.add(
                ids=[doc_id],
                documents=[semantic_document],
                metadatas=[metadata]
            )
            logger.debug(f"Logged IDE context: {editor} | {file_path}")
        except Exception as e:
            logger.error(f"Failed to log IDE context to memory: {e}")

    def log_snapshot_context(
        self,
        ocr_text: Optional[str] = None,
        image_b64: Optional[str] = None,
        source_display: Optional[str] = "primary"
    ) -> None:
        """
        Ingests visual desktop snapshot OCR or thumbnails for situational awareness.
        """
        if not self.context_db:
            return

        now = datetime.datetime.now()
        doc_id = f"snap_{now.timestamp()}"

        clean_ocr = (ocr_text or "").strip()[:500]
        semantic_document = (
            f"Screen snapshot captured on display '{source_display}'. OCR text preview: {clean_ocr}"
            if clean_ocr else f"Visual screenshot snapshot recorded on display '{source_display}'."
        )

        metadata = {
            "timestamp": now.isoformat(),
            "hour_of_day": now.hour,
            "source_display": source_display or "primary",
            "has_image": bool(image_b64),
            "type": "desktop_snapshot_event"
        }

        try:
            self.context_db.add(
                ids=[doc_id],
                documents=[semantic_document],
                metadatas=[metadata]
            )
            logger.debug(f"Logged snapshot context for display: {source_display}")
        except Exception as e:
            logger.error(f"Failed to log snapshot context to memory: {e}")

    def get_recent_desktop_context(self, minutes_lookback: int = 5) -> str:
        """
        Retrieves recent context across all perception channels (window focus, IDE, snapshots)
        to inject into Charon's active prompt context.
        """
        if not self.context_db:
            return "Unknown"

        cutoff_time = datetime.datetime.now() - datetime.timedelta(minutes=minutes_lookback)

        try:
            results = self.context_db.get(limit=15)

            if not results or not results.get("metadatas"):
                return "No active desktop context detected."

            recent_events = []
            for i, meta in enumerate(results["metadatas"]):
                ts_str = meta.get("timestamp")
                if not ts_str:
                    continue
                event_time = datetime.datetime.fromisoformat(ts_str)
                if event_time >= cutoff_time:
                    recent_events.append((event_time, results["documents"][i], meta))

            if not recent_events:
                return "No active desktop context detected."

            # Sort descending (newest first)
            recent_events.sort(key=lambda x: x[0], reverse=True)
            return recent_events[0][1]

        except Exception as e:
            logger.error(f"Failed to retrieve desktop context: {e}")
            return "Context retrieval failed."