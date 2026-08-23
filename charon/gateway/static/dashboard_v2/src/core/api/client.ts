export function getApiKey(): string {
  const urlParams = new URLSearchParams(window.location.search);
  let apiKey = urlParams.get('api_key');

  if (apiKey) {
    localStorage.setItem('charon_api_key', apiKey.trim());
    // Clean URL parameter to prevent key exposure in address bar & history
    const cleanUrl = window.location.protocol + "//" + window.location.host + window.location.pathname;
    window.history.replaceState({ path: cleanUrl }, '', cleanUrl);
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
