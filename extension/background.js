// Service worker — central SSE multiplexer + daemon health proxy.
//
// Why this exists: Chrome limits HTTP/1.1 connections per origin to ~6.
// When several tabs each opened their own EventSource("/events"), the 7th
// tab onwards stalled in the browser's connection queue and never received
// the page-decoration data. This worker now owns the *single* SSE connection
// to the daemon and fans events out to all tabs via chrome.runtime ports.

const BASE = "http://127.0.0.1:8765";

chrome.runtime.onInstalled.addListener(() => {
  console.log("[streamseeker] extension installed/updated");
});

// ---------- daemon health (existing API, unchanged signature) ------------

async function daemonAlive() {
  try {
    const response = await fetch(`${BASE}/status`, { method: "GET" });
    return response.ok;
  } catch (_) {
    return false;
  }
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg && msg.type === "ss:daemon-alive") {
    daemonAlive().then((alive) => sendResponse({ alive }));
    return true; // async response
  }
  return false;
});

// ---------- self-update via daemon-managed disk copy ---------------------
//
// The CLI's daemon syncs ~/.streamseeker/extension/ with the bundled source on
// every startup. When the on-disk version is newer than what we are running,
// chrome.runtime.reload() makes Chrome re-read the unpacked folder and
// transparently brings us up to that version. No user action needed.

function parseVersion(v) {
  if (!v) return [0];
  return v.split(".").map((s) => {
    const n = parseInt(s, 10);
    return Number.isFinite(n) ? n : 0;
  });
}

function isNewer(a, b) {
  const aa = parseVersion(a), bb = parseVersion(b);
  for (let i = 0; i < Math.max(aa.length, bb.length); i++) {
    const x = aa[i] || 0, y = bb[i] || 0;
    if (x > y) return true;
    if (x < y) return false;
  }
  return false;
}

async function checkForUpdate() {
  try {
    const resp = await fetch(`${BASE}/extension/version`, { cache: "no-store" });
    if (!resp.ok) return;
    const { version: onDisk } = await resp.json();
    const running = chrome.runtime.getManifest().version;
    if (isNewer(onDisk, running)) {
      console.log(
        `[streamseeker] reloading extension: ${running} → ${onDisk} (disk is newer)`
      );
      chrome.runtime.reload();
    }
  } catch (_) {
    // daemon not reachable — try again later
  }
}

// Check on SW startup (covers both fresh install and Chrome relaunches),
// and again every 5 minutes while the worker is alive.
chrome.runtime.onStartup.addListener(() => { checkForUpdate(); });
chrome.runtime.onInstalled.addListener(() => { checkForUpdate(); });
checkForUpdate();
chrome.alarms?.create?.("ss:check-update", { periodInMinutes: 5 });
chrome.alarms?.onAlarm.addListener((alarm) => {
  if (alarm.name === "ss:check-update") checkForUpdate();
});

// ---------- SSE multiplexer ----------------------------------------------

/** Active subscriber ports (one per content-script / popup that subscribed). */
const subscribers = new Set();

/** AbortController for the in-flight SSE fetch, or null if not connected. */
let sseAbort = null;

/** Backoff (ms) for reconnect; resets to 1s on any successful read. */
let backoff = 1000;

function broadcast(event, data) {
  for (const port of subscribers) {
    try {
      port.postMessage({ type: "ss:event", event, data });
    } catch (_) {
      // Port disconnected mid-broadcast; will be cleaned up by onDisconnect.
    }
  }
}

async function pumpEvents(signal) {
  // Fetch the SSE stream and parse line-by-line. Standard SSE wire format:
  //   event: <name>\n
  //   data: <json>\n
  //   \n
  const resp = await fetch(`${BASE}/events`, {
    signal,
    headers: { Accept: "text/event-stream" },
    cache: "no-store",
  });
  if (!resp.ok || !resp.body) {
    throw new Error(`SSE upstream returned ${resp.status}`);
  }
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  let currentEvent = "message";
  let currentData = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    backoff = 1000;
    buf += decoder.decode(value, { stream: true });

    let nl;
    while ((nl = buf.indexOf("\n")) !== -1) {
      const line = buf.slice(0, nl).replace(/\r$/, "");
      buf = buf.slice(nl + 1);
      if (line === "") {
        if (currentData) {
          let parsed;
          try { parsed = JSON.parse(currentData); }
          catch (_) { parsed = currentData; }
          broadcast(currentEvent, parsed);
        }
        currentEvent = "message";
        currentData = "";
      } else if (line.startsWith("event:")) {
        currentEvent = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        currentData += (currentData ? "\n" : "") + line.slice(5).trim();
      }
      // ignore "id:" / "retry:" / comments
    }
  }
}

async function ensureSseRunning() {
  if (sseAbort) return; // already connected (or connecting)
  const controller = new AbortController();
  sseAbort = controller;
  // Loop with backoff; only exits when subscribers go to zero.
  (async () => {
    while (subscribers.size > 0) {
      try {
        await pumpEvents(controller.signal);
      } catch (err) {
        if (controller.signal.aborted) return;
        // Connection closed unexpectedly — back off and retry.
        await new Promise((r) => setTimeout(r, backoff));
        backoff = Math.min(backoff * 2, 30000);
      }
    }
    // No more subscribers — let go of the connection.
    if (sseAbort === controller) sseAbort = null;
  })();
}

function stopSseIfIdle() {
  if (subscribers.size > 0) return;
  if (sseAbort) {
    sseAbort.abort();
    sseAbort = null;
  }
}

chrome.runtime.onConnect.addListener((port) => {
  if (port.name !== "ss:events") return;
  subscribers.add(port);
  port.onDisconnect.addListener(() => {
    subscribers.delete(port);
    stopSseIfIdle();
  });
  ensureSseRunning();
});
