# Agent Card: `The_Scout` (Web Reconnaissance & Content Extraction)

**File Path:** `docs/architecture/agents/scout.md`

**Target Module:** `charon/agents/scout/agent.py`

**Agent Class:** `TheScout`

**Agent Enum:** `AgentEnum.The_Scout`

**Safety Intercept Level:** 🟢 **Low Intercept** (Read-only HTTP web searches & URL page content scraping; no local storage mutations, shell calls, or file writes)

**System Specification:** Charon Agent Spec v2.2 / System Architecture v4.5

---

## 1. Operational Overview

**`The_Scout`** serves as Charon’s domain-agnostic web reconnaissance agent. It provides web search capabilities, query result parsing, and direct URL page extraction. `The_Scout` converts raw web data into clean, sanitized Markdown and plain-text snippets for context injection and upstream LLM ingestion.

To ensure high availability, `The_Scout` employs a dual-tiered search fallback strategy (DuckDuckGo primary with Google Search fallback) and aggressive domain filtering to ignore layout noise and aggregator bloat. For page scraping, it utilizes `httpx` and `BeautifulSoup` to strip non-content HTML markup (navigation bars, footers, scripts, and forms) before applying character windowing.

---

## 2. Action Capabilities & Method Mapping

| Action Alias (`ScoutPayload`) | Executing Method | Target Parameters | Description |
| --- | --- | --- | --- |
| `search_web`, `search`, `web_search`, `query_web`, `google_search` | `_search_web` | `query`, `prompt`, `raw_prompt`, `max_results` | Executes a web search query across primary/secondary search engines, filters domain noise, and returns formatted Markdown search results. |
| `scrape_page_content`, `scrape`, `fetch_url`, `scrape_url`, `read_page`, `fetch` | `_scrape_url` | `url`, `link`, `max_chars` | Fetches an HTTP/HTTPS endpoint, decomposes non-content DOM elements, normalizes whitespace, and truncates text to `max_chars`. |

---

## 3. Subsystem Logic & Architectural Features

### Query Cleaning & Regex Normalization (`_clean_query`)

Before issuing network requests, query strings are cleaned to remove wrapping LLM artifacts, quotes, or Markdown syntax:

