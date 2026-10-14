// NEXT_PUBLIC_API_URL is normally a relative path (e.g. "/braingram_mg_api"),
// which only resolves correctly when the page is loaded through the Apache
// reverse proxy that rewrites it to the backend. NEXT_PUBLIC_* values are
// baked into the client bundle at build time, so a single build can't serve
// a different value per access method -- this has to be decided at runtime
// in the browser instead. When this Next.js server is opened directly on its
// own port (bypassing Apache, e.g. for local dev), that relative path loops
// back into Next.js itself instead of reaching the backend, so fall back to
// an absolute local backend URL in that case.
const LOCAL_DEV_PORT = "3001";
const LOCAL_API_URL = process.env.NEXT_PUBLIC_LOCAL_API_URL || "http://localhost:8001";

export function getApiBase(): string {
  const configured = process.env.NEXT_PUBLIC_API_URL;
  const isRelative = !configured || configured.startsWith("/");
  if (typeof window !== "undefined" && window.location.port === LOCAL_DEV_PORT && isRelative) {
    return LOCAL_API_URL;
  }
  return configured || LOCAL_API_URL;
}

export function getWsBase(): string {
  const base = getApiBase();
  if (base.startsWith("https://")) return "wss://" + base.slice("https://".length);
  if (base.startsWith("http://")) return "ws://" + base.slice("http://".length);
  // Relative path case (proxied via Apache): derive ws(s) scheme and host from the
  // current page, same as the browser would for the http(s) fetches using this base.
  const wsProto = typeof window !== "undefined" && window.location.protocol === "https:" ? "wss:" : "ws:";
  const host = typeof window !== "undefined" ? window.location.host : "";
  return `${wsProto}//${host}${base}`;
}
