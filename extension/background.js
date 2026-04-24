// Service worker — kept deliberately thin.
//
// Content scripts and the popup already talk to the daemon directly via
// fetch/SSE. The service worker only handles cross-context signalling
// (e.g. notifying the popup about daemon reachability once the popup opens).

const BASE = "http://127.0.0.1:8765";

chrome.runtime.onInstalled.addListener(() => {
  console.log("[streamseeker] extension installed/updated");
});

// Simple health check — used by the popup and any future dashboard.
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
    return true;  // async response
  }
  return false;
});
