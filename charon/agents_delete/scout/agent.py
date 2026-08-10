"""
charon/agents/scout/agent.py
System Version: v0.1.0 | File Revision: 2.1.0

Module: Orchestrator class for web reconnaissance and link parsing.
Inherits from BaseAgent for unified system probing and capability discovery.
Updated for dynamic intent schemas.
"""

import logging
from typing import Any, Callable, Dict, List, Optional, Union

from charon.agents.base import BaseAgent
from charon.agents.scout.scraping import scrape_url_content
from charon.agents.scout.search import (
    DEFAULT_IGNORED_DOMAINS,
    perform_web_search,
    search_links,
)
from charon.core.skills import SkillLibrarian
from charon.intent import DynamicActionPayload

logger = logging.getLogger("charon.agents.scout")

VALID_SCOUT_ACTIONS = (
    "search_web",
    "web_search",
    "scrape_page_content",
)

ACTION_MAP = {
    "web_search": "search_web",
    "search_web": "search_web",
    "search": "search_web",
    "query_web": "search_web",
    "google_search": "search_web",
    "scrape_page_content": "scrape_page_content",
    "scrape": "scrape_page_content",
    "fetch_url": "scrape_page_content",
    "scrape_url": "scrape_page_content",
    "read_page": "scrape_page_content",
    "fetch": "scrape_page_content",
}


class TheScout(BaseAgent):
    """Pure, domain-agnostic web reconnaissance agent.

    Handles web search queries, link parsing, and direct URL content extraction.
    """

    name: str = "TheScout"
    domain: str = (
        "Pure, domain-agnostic web reconnaissance handling web search queries, "
        "link parsing, and direct URL content extraction."
    )
    description: str = (
        "Web reconnaissance agent specializing in multi-engine search execution, "
        "link parsing, domain filtering, and web page content extraction."
    )

    system_requirements: List[str] = ["requests", "beautifulsoup4"]
    consumed_artifacts: List[str] = ["query", "url", "max_results", "max_chars"]
    produced_artifacts: List[str] = [
        "search_results",
        "scraped_content",
        "web_links",
    ]

    SUPPORTED_ACTIONS: Dict[str, List[str]] = {
        "search_web": [
            "search_web",
            "web_search",
            "search",
            "query_web",
            "google_search",
        ],
        "scrape_page_content": [
            "scrape_page_content",
            "scrape",
            "fetch_url",
            "scrape_url",
            "read_page",
            "fetch",
        ],
    }

    supported_actions = SUPPORTED_ACTIONS
    IGNORED_DOMAINS = DEFAULT_IGNORED_DOMAINS

    def __init__(
        self,
        headers: Optional[Dict[str, str]] = None,
        librarian: Optional[SkillLibrarian] = None,
    ) -> None:
        """Initializes TheScout agent with customized headers for web requests."""
        super().__init__(librarian=librarian)
        self.headers = headers or {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
        }
        logger.info(
            f"[{self.name}] Initialized with custom headers and {len(self.IGNORED_DOMAINS)} ignored domains."
        )

    def health_check(self) -> Dict[str, Any]:
        """Runtime health check verifying HTTP headers and scraping capability readiness."""
        base_health = super().health_check()
        try:
            healthy = bool(self.headers and "User-Agent" in self.headers) and base_health.get("healthy", True)
            return {
                "agent": self.name,
                "domain": self.domain,
                "healthy": healthy,
                "status": (
                    "Operational"
                    if healthy
                    else "Degraded: Missing User-Agent configuration"
                ),
                "missing_dependencies": base_health.get(
                    "missing_dependencies", []
                ),
                "details": {
                    "user_agent": self.headers.get("User-Agent")
                    if self.headers
                    else None,
                    "ignored_domains_count": len(self.IGNORED_DOMAINS),
                    **base_health.get("details", {}),
                },
                "dynamic_skills_available": base_health.get(
                    "dynamic_skills_available", []
                ),
                "native_actions_supported": base_health.get(
                    "native_actions_supported", []
                ),
            }
        except Exception as e:
            return {
                "agent": self.name,
                "domain": self.domain,
                "healthy": False,
                "status": f"Degraded: Exception during health check ({e})",
                "missing_dependencies": base_health.get(
                    "missing_dependencies", []
                ),
                "details": {},
            }

    async def execute(
        self,
        action: str,
        params: Optional[Dict[str, Any]] = None,
        parameters: Optional[Dict[str, Any]] = None,
        raw_prompt: str = "",
        stream_callback: Optional[Callable[[str], None]] = None,
    ) -> Union[str, Dict[str, Any]]:
        """The primary routing switch for The Scout's capabilities using DynamicActionPayload schemas."""
        raw_params = parameters if parameters is not None else (params or {})
        payload_dict = dict(raw_params)
        action_clean = str(action or "").lower().strip()

        # Dynamic Probing Intercept
        if action_clean in ["probe", "ping", "health", "get_capabilities", "status"]:
            probe_type = payload_dict.get("probe_type", "full")
            return self.probe(probe_type=probe_type)

        normalized_action = ACTION_MAP.get(action_clean, action_clean)

        # Validate action string before payload construction
        if normalized_action not in VALID_SCOUT_ACTIONS:
            logger.error(
                f"[{self.name}] Does not recognize action: {normalized_action}"
            )
            raise ValueError(
                f"Unknown action '{normalized_action}' for {self.name}"
            )

        self.report_progress(
            message=f"Executing reconnaissance action: '{normalized_action}'",
            phase="START",
            action=normalized_action,
            progress_pct=0.0,
        )
        self.report_trace(
            event_type="EXECUTION_START",
            action=normalized_action,
            details={"parameters": payload_dict, "raw_prompt": raw_prompt},
        )
        self.report_action(action=normalized_action, details=payload_dict)

        try:
            if "call_action" in payload_dict and "params" in payload_dict:
                payload = DynamicActionPayload.model_validate(payload_dict)
            else:
                extracted_params = {
                    k: v for k, v in payload_dict.items()
                    if k not in ["call_action", "action", "thought", "memory_candidate"]
                }
                payload = DynamicActionPayload(
                    call_action=normalized_action,
                    thought=payload_dict.get("thought", ""),
                    params=extracted_params,
                )
        except Exception as e:
            logger.warning(
                f"[{self.name}] Payload validation warning ({e}). Executing fallback construction..."
            )
            fallback_action = (
                normalized_action
                if normalized_action in VALID_SCOUT_ACTIONS
                else "search_web"
            )
            payload = DynamicActionPayload(
                call_action=fallback_action,
                thought=payload_dict.get("thought", ""),
                params=payload_dict,
            )

        target_action = payload.call_action or normalized_action

        logger.info(
            f"[{self.name}] Executing action '{target_action}' with params: {payload.params}"
        )

        try:
            if target_action in ("search_web", "web_search"):
                query = (
                    payload.params.get("query")
                    or payload.params.get("prompt")
                    or payload.params.get("raw_prompt")
                    or raw_params.get("query")
                    or raw_params.get("prompt")
                    or raw_params.get("raw_prompt")
                    or raw_prompt
                )
                try:
                    max_results = int(
                        payload.params.get("max_results")
                        or raw_params.get("max_results", 5)
                    )
                except (ValueError, TypeError):
                    max_results = 5

                result = self._search_web(str(query), max_results=max_results)

            elif target_action == "scrape_page_content":
                url = (
                    payload.params.get("url")
                    or payload.params.get("link")
                    or raw_params.get("url")
                    or raw_params.get("link")
                )
                try:
                    max_chars = int(
                        payload.params.get("max_chars")
                        or raw_params.get("max_chars", 4000)
                    )
                except (ValueError, TypeError):
                    max_chars = 4000

                if not url or not str(url).strip():
                    result = "Error: A target 'url' parameter is required for scraping."
                else:
                    result = self._scrape_url(
                        str(url).strip(), max_chars=max_chars
                    )

            else:
                raise ValueError(
                    f"Unknown action '{normalized_action}' for {self.name}"
                )

            self.report_progress(
                message=f"Successfully completed action: '{normalized_action}'",
                phase="COMPLETE",
                action=normalized_action,
                progress_pct=100.0,
            )
            self.report_trace(
                event_type="EXECUTION_COMPLETE",
                action=normalized_action,
                details={"status": "success"},
            )
            return result

        except Exception as e:
            logger.exception(
                f"[{self.name}] Execution error during '{normalized_action}': {e}"
            )
            self.report_progress(
                message=f"Failed to execute action: '{normalized_action}'",
                phase="ERROR",
                action=normalized_action,
                progress_pct=100.0,
            )
            self.report_trace(
                event_type="EXECUTION_ERROR",
                action=normalized_action,
                details={"error": str(e)},
            )
            raise

    # =========================================================================
    # BACKWARD COMPATIBILITY HELPERS & DELEGATES
    # =========================================================================

    def search_links(
        self, query: str, max_results: int = 5
    ) -> List[Dict[str, str]]:
        """Returns raw search result dicts [{'title', 'link', 'snippet'}] for programmatic consumption."""
        return search_links(
            query,
            max_results=max_results,
            ignored_domains=self.IGNORED_DOMAINS,
        )

    def _search_web(self, query: str, max_results: int = 5) -> str:
        """Performs a web search using DuckDuckGo with fallback to Google."""
        return perform_web_search(
            query,
            max_results=max_results,
            ignored_domains=self.IGNORED_DOMAINS,
        )

    def _scrape_url(self, url: str, max_chars: int = 4000) -> str:
        """Fetches a web page and extracts sanitized readable text."""
        return scrape_url_content(
            url, max_chars=max_chars, headers=self.headers
        )