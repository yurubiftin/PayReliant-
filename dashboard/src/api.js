// Everything the dashboard needs from the PayReliant API, in one place.
// Every request carries the logged-in user's token: "Authorization: Bearer <token>".

export const API_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

let token = null;                 // set by the login session (auth.jsx)
let onUnauthorized = () => {};    // called when the token is missing or expired

export function setToken(value) { token = value; }
export function setUnauthorizedHandler(fn) { onUnauthorized = fn; }

async function request(method, path, body) {
  const headers = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";

  const response = await fetch(`${API_URL}${path}`, {
    method, headers, body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (response.status === 401) {
    onUnauthorized();             // session expired: back to the login page
    throw new Error("Your session has expired. Please log in again.");
  }
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    // FastAPI puts the reason in "detail" (a string, or a list of validation errors)
    const detail = Array.isArray(data?.detail) ? data.detail.map((d) => d.msg).join("; ") : data?.detail;
    throw new Error(detail || `${path} returned ${response.status}`);
  }
  return data;
}

export const api = {
  // Logging in sends a form (username + password), as the OAuth2 standard expects.
  async login(username, password) {
    const response = await fetch(`${API_URL}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ username, password }),
    });
    const data = await response.json().catch(() => null);
    if (!response.ok) throw new Error(data?.detail || "Login failed.");
    return data; // { access_token, token_type, user }
  },

  stats: () => request("GET", "/stats"),
  transactions: (limit) => request("GET", limit ? `/transactions?limit=${limit}` : "/transactions"),
  customers: () => request("GET", "/customers"),
  merchants: () => request("GET", "/merchants"),
  wallets: () => request("GET", "/wallets"),

  // Admin only
  createCustomer: (body) => request("POST", "/customers", body),
  createMerchant: (body) => request("POST", "/merchants", body),
  setCustomerStatus: (id, status) => request("PATCH", `/customers/${id}`, { status }),
  setMerchantStatus: (id, status) => request("PATCH", `/merchants/${id}`, { status }),
  settings: () => request("GET", "/settings"),
  saveSettings: (body) => request("PUT", "/settings", body),
  runReliabilityTest: (scenario) => request("POST", `/reliability/run/${scenario}`),
  reliabilityRuns: () => request("GET", "/reliability/runs?limit=20"),
};
