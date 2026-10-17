// Small fetch wrapper for the SiteScope API (same origin; the session is an httpOnly cookie).

export async function api(path, { method = "GET", json, form } = {}) {
  const url = `/api${path}`;
  const init = { method, credentials: "same-origin", headers: {} };
  if (json !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(json);
  } else if (form) {
    init.body = form;
  }
  let res;
  try {
    res = await fetch(url, init);
  } catch {
    throw new Error("Cannot reach the server. Is the backend running?");
  }
  if (res.status === 204) return null;
  const isJson = (res.headers.get("content-type") || "").includes("application/json");
  const data = isJson ? await res.json() : await res.text();
  if (!res.ok) {
    if (res.status === 401 && path !== "/auth/login") window.dispatchEvent(new CustomEvent("auth:required"));
    throw new Error((isJson && data?.error?.message) || `Request failed (${res.status})`);
  }
  return data;
}

export const get = (path) => api(path);
export const post = (path, json) => api(path, { method: "POST", json });
export const put = (path, json) => api(path, { method: "PUT", json });
