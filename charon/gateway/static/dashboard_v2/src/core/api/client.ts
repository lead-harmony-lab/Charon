/**
 * @file src/core/api/client.ts
 * @description
 */
export function getApiKey(): string {
  // Use the URL object to safely parse the entire location
  const url = new URL(window.location.href);
  let apiKey = url.searchParams.get('api_key');

  if (apiKey) {
    localStorage.setItem('charon_api_key', apiKey.trim());

    // Surgically remove ONLY the api_key. This preserves the hash (#/journal)
    // and any other query params you might be testing with.
    url.searchParams.delete('api_key');
    window.history.replaceState({ path: url.toString() }, '', url.toString());
  } else {
    apiKey = localStorage.getItem('charon_api_key');
  }

  if (!apiKey) {
    apiKey = prompt("Please enter your Charon API Key:") || '';
    if (apiKey) {
      apiKey = apiKey.trim();
      localStorage.setItem('charon_api_key', apiKey);
    }
  }

  return apiKey || '';
}

export async function authFetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
  const apiKey = getApiKey();
  const headers = new Headers(init.headers || {});
  headers.set('X-API-Key', apiKey);

  const response = await fetch(input, { ...init, headers });

  if (response.status === 401) {
    localStorage.removeItem('charon_api_key');
    alert("Invalid or missing API key token. Page will reload to re-authenticate.");
    window.location.reload();
  }

  return response;
}