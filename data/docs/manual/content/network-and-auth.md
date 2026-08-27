### Authentication & Network Layer

Managed via `src/core/api/client.ts`:

* **API Key Management**: Extracts `?api_key=` from URL params, cleans history, and persists key in `localStorage` as `charon_api_key`.
* **`authFetch` Wrapper**: Injects `X-API-Key` headers on HTTP requests and forces session re-authentication on 401 errors.