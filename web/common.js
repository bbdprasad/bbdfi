// Shared by the dashboard (app.js) and the terminal (terminal.js): formatting, API calls and sign-in.

export const $ = (selector) => document.querySelector(selector);
export const $$ = (selector) => document.querySelectorAll(selector);

export const currency = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", minimumFractionDigits: 2, maximumFractionDigits: 2 });
export const shortCurrency = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 });
export const number = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 });
export const shortDate = (iso) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short" });
export const longDate = (iso) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short", year: "numeric" });
export const signed = (value, digits = 2) => `${value > 0 ? "+" : ""}${Number(value).toFixed(digits)}%`;
export const tone = (value) => (value > 0 ? "positive" : value < 0 ? "negative" : "");
export const initials = (name) => (name || "?").split(/[\s_]+/).filter(Boolean).slice(0, 2).map((part) => part[0]).join("").toUpperCase();

export function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character]);
}

export class ApiError extends Error {}

const DEV_KEY = "bbdfi-dev-handle";
const auth = { config: null, supabase: null, onSignedIn: () => {} };

function readDevHandle() {
  try { return localStorage.getItem(DEV_KEY); } catch { return null; }
}

export async function accessToken() {
  if (auth.config.auth_mode === "dev") {
    const handle = readDevHandle();
    return handle ? `dev:${handle}` : null;
  }
  const { data } = await auth.supabase.auth.getSession();
  return data.session?.access_token ?? null;
}

export function showLogin() { $("#loginScreen").hidden = false; }
export function hideLogin() { $("#loginScreen").hidden = true; }

export async function api(path, { method = "GET", body, auth: needsAuth = true } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (needsAuth) {
    const token = await accessToken();
    if (!token) { showLogin(); throw new ApiError("Sign in required"); }
    headers.Authorization = `Bearer ${token}`;
  }
  const response = await fetch(path, { method, headers, body: body ? JSON.stringify(body) : undefined });
  if (response.status === 401 && needsAuth) { showLogin(); throw new ApiError("Sign in required"); }
  if (response.status === 204) return null;
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new ApiError(typeof data.detail === "string" ? data.detail : "Something went wrong");
  return data;
}

// Wires the #loginScreen overlay. onSignedIn runs after a successful sign-in.
export async function setupAuth({ onSignedIn }) {
  auth.onSignedIn = onSignedIn;
  auth.config = await api("/api/config", { auth: false });
  if (auth.config.auth_mode === "supabase") {
    const { createClient } = await import("https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/+esm");
    auth.supabase = createClient(auth.config.supabase_url, auth.config.supabase_anon_key);
    auth.supabase.auth.onAuthStateChange((event) => {
      if (event === "SIGNED_IN") { hideLogin(); auth.onSignedIn(); }
      if (event === "SIGNED_OUT") showLogin();
    });
  } else {
    $("#loginLabel").textContent = "Pick a handle";
    $("#loginInput").type = "text";
    $("#loginInput").autocomplete = "username";
    $("#loginInput").placeholder = "e.g. nifty_ninja";
    $("#loginInput").pattern = "[a-z0-9_]{3,20}";
    $("#loginInput").title = "3 to 20 lowercase letters, digits or _";
    $("#loginButton").textContent = "Start paper trading";
    $("#loginHint").textContent = "Local dev mode: no password needed. Connect Supabase to require real sign-in.";
  }

  $("#loginForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const value = $("#loginInput").value.trim();
    const errorBox = $("#loginError");
    errorBox.hidden = true;
    if (auth.config.auth_mode === "dev") {
      try { localStorage.setItem(DEV_KEY, value.toLowerCase()); } catch { /* storage blocked */ }
      hideLogin();
      auth.onSignedIn();
      return;
    }
    const redirect = window.location.origin + window.location.pathname;
    const { error } = await auth.supabase.auth.signInWithOtp({ email: value, options: { emailRedirectTo: redirect } });
    if (error) { errorBox.textContent = error.message; errorBox.hidden = false; return; }
    $("#loginSent").textContent = `Check ${value} for your sign-in link.`;
    $("#loginSent").hidden = false;
  });
}

export async function signOut() {
  if (auth.config.auth_mode === "dev") {
    try { localStorage.removeItem(DEV_KEY); } catch { /* storage blocked */ }
  } else {
    await auth.supabase.auth.signOut();
  }
  showLogin();
}
