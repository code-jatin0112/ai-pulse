const BASE = import.meta.env.VITE_API_URL || "http://localhost:8001";

export function getToken() {
  return localStorage.getItem("token");
}

export function setToken(t) {
  localStorage.setItem("token", t);
}

export async function api(path, options = {}) {
  let res;
  try {
    res = await fetch(BASE + path, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}),
        ...(options.headers || {}),
      },
    });
  } catch {
    throw new Error(`Unable to connect to backend API at ${BASE}. Ensure the server is running.`);
  }

  let data = null;
  const contentType = res.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    try {
      data = await res.json();
    } catch {
      data = null;
    }
  } else {
    try {
      const text = await res.text();
      if (text) {
        data = { detail: text.trim() };
      }
    } catch {
      data = null;
    }
  }

  if (!res.ok) {
    const errorMsg = (data && data.detail) || `Request failed with status ${res.status}`;
    throw new Error(errorMsg);
  }
  return data;
}
