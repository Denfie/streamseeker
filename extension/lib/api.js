// Thin HTTP client talking to the StreamSeeker daemon on 127.0.0.1:8765.
// Exposed as `window.ssApi` for content scripts (no ES modules in MV3
// content-script context) and `globalThis.ssApi` for the popup/background.

(function () {
  const BASE = "http://127.0.0.1:8765";

  async function request(method, path, body) {
    const init = {
      method,
      headers: { "Accept": "application/json" },
    };
    if (body !== undefined) {
      init.headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(body);
    }
    const response = await fetch(BASE + path, init);
    if (!response.ok) {
      let detail = response.statusText;
      try {
        const data = await response.json();
        detail = data.detail || detail;
      } catch (_) { /* ignore non-JSON bodies */ }
      const err = new Error(`HTTP ${response.status}: ${detail}`);
      err.status = response.status;
      throw err;
    }
    if (response.status === 204) return null;
    const text = await response.text();
    return text ? JSON.parse(text) : null;
  }

  async function isDaemonAlive() {
    try {
      const r = await fetch(BASE + "/status", { method: "GET" });
      return r.ok;
    } catch (_) {
      return false;
    }
  }

  const api = {
    BASE,
    isDaemonAlive,

    version: () => request("GET", "/version"),
    status: () => request("GET", "/status"),

    queueList: () => request("GET", "/queue"),
    queueAdd: (payload) => request("POST", "/queue", payload),
    seriesStructure: (stream, slug) =>
      request("GET", `/series/${encodeURIComponent(stream)}/${encodeURIComponent(slug)}/structure`),
    seriesEpisodes: (stream, slug, season, type = "staffel") =>
      request("GET", `/series/${encodeURIComponent(stream)}/${encodeURIComponent(slug)}/episodes?season=${season}&type=${encodeURIComponent(type)}`),
    queuePause: (fileName) => request("POST", `/queue/${encodeURI(fileName)}/pause`),
    queueResume: (fileName) => request("POST", `/queue/${encodeURI(fileName)}/resume`),
    queueRetry: (fileName) => request("POST", `/queue/${encodeURI(fileName)}/retry`),
    queueDelete: (fileName) => request("DELETE", `/queue/${encodeURI(fileName)}`),

    libraryList: () => request("GET", "/library"),
    libraryGet: (key) => request("GET", `/library/${encodeURIComponent(key)}`),
    libraryRefresh: (key) => request("POST", `/library/${encodeURIComponent(key)}/refresh`),
    libraryState: (stream, slug) =>
      request("GET", `/library/state?stream=${encodeURIComponent(stream)}&slug=${encodeURIComponent(slug)}`),

    updatesList: () => request("GET", "/updates"),
    updatesDismiss: (key) => request("POST", `/updates/${encodeURIComponent(key)}/dismiss`),

    favoritesList: () => request("GET", "/favorites"),
    favoritesAdd: (stream, slug) => request("POST", "/favorites", { stream, slug }),
    favoritesRemove: (key) => request("DELETE", `/favorites/${encodeURIComponent(key)}`),
    favoritesPromote: (key) => request("POST", `/favorites/${encodeURIComponent(key)}/promote`),

    posterUrl: (key) => `${BASE}/library/${encodeURIComponent(key)}/poster`,
    backdropUrl: (key) => `${BASE}/library/${encodeURIComponent(key)}/backdrop`,

    // Server-Sent Events — returns an AbortController caller can .abort().
    subscribeStatus(onStatus, onError) {
      const source = new EventSource(BASE + "/events");
      source.addEventListener("status", (ev) => {
        try {
          onStatus(JSON.parse(ev.data));
        } catch (err) {
          if (onError) onError(err);
        }
      });
      source.addEventListener("error", (err) => {
        if (onError) onError(err);
      });
      return source;
    },

    // SemVer comparison helper — "0.2.1" >= "0.2.0" → true
    versionGte(actual, required) {
      const toTuple = (v) => v.split(".").map((s) => parseInt(s, 10) || 0);
      const a = toTuple(actual);
      const r = toTuple(required);
      for (let i = 0; i < Math.max(a.length, r.length); i++) {
        const x = a[i] || 0, y = r[i] || 0;
        if (x > y) return true;
        if (x < y) return false;
      }
      return true;
    },
  };

  if (typeof window !== "undefined") window.ssApi = api;
  if (typeof globalThis !== "undefined") globalThis.ssApi = api;
})();
