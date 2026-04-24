// Popup controller — status, library, favorites.
//
// Uses window.ssApi (from ../lib/api.js, loaded before this script).

(function () {
  const api = window.ssApi;
  let minCliVersion = "0.0.0";

  const STREAM_LABELS = {
    aniworldto: "AniWorld",
    sto: "S.to",
    megakinotax: "MegaKino",
  };

  const STREAM_URL_BUILDERS = {
    aniworldto: (slug) => `https://aniworld.to/anime/stream/${slug}`,
    sto: (slug) => `https://s.to/serie/stream/${slug}`,
    megakinotax: (slug) => `https://megakino.tax/${slug}.html`,
  };

  const libraryFilter = { stream: null, favoritesOnly: false, rows: [] };
  const UPDATE_LABELS = {
    new_season: (u) => `neue Staffel ${u.season}`,
    new_episode: (u) => `S${u.season}: +${(u.to || 0) - (u.from || 0)} Episode${((u.to || 0) - (u.from || 0)) === 1 ? "" : "n"}`,
    new_movie: (u) => `neuer Film`,
  };
  let pendingKeys = new Set();

  async function init() {
    await loadManifestMeta();
    wireTabs();
    wireSearch();

    try {
      const daemonAlive = await api.isDaemonAlive();
      if (!daemonAlive) {
        showBanner("Daemon nicht erreichbar — bitte 'streamseeker daemon start' ausführen.");
        return;
      }

      const version = await api.version();
      document.querySelector("#ss-version").textContent = `CLI ${version.cli}`;
      if (!api.versionGte(version.cli, minCliVersion)) {
        showBanner(`CLI ${version.cli} zu alt — mind. ${minCliVersion} benötigt.`);
      }
    } catch (err) {
      console.warn("[streamseeker] init failed", err);
    }

    const updates = await safeFetch(() => api.updatesList(), []);
    const queueItems = await safeFetch(() => api.queueList(), []);

    await renderUpdates(updates);
    renderStatus();
    renderLibrary();

    selectInitialTab(updates.length, queueItems.length);

    api.subscribeStatus(renderStatus, () => {});
  }

  async function safeFetch(fn, fallback) {
    try { return await fn(); } catch (_) { return fallback; }
  }

  function selectInitialTab(updateCount, queueCount) {
    let target = "library";
    if (updateCount > 0) target = "updates";
    else if (queueCount > 0) target = "status";
    activateTab(target);
  }

  function activateTab(name) {
    const tabs = document.querySelectorAll(".tab");
    const panels = document.querySelectorAll(".tab-panel");
    tabs.forEach((t) => t.setAttribute("aria-selected", t.dataset.tab === name ? "true" : "false"));
    panels.forEach((p) => (p.hidden = `tab-${name}` !== p.id));
  }

  async function loadManifestMeta() {
    try {
      const manifest = chrome.runtime.getManifest();
      minCliVersion = manifest.minCliVersion || "0.0.0";
      document.querySelector("#ss-version").textContent = `ext ${manifest.version}`;
    } catch (_) { /* ignore */ }
  }

  function showBanner(text) {
    const el = document.querySelector("#ss-banner");
    el.textContent = text;
    el.hidden = false;
  }

  // ----- Tabs -------------------------------------------------------

  function wireTabs() {
    const tabs = document.querySelectorAll(".tab");
    const panels = document.querySelectorAll(".tab-panel");
    tabs.forEach((tab) => {
      tab.addEventListener("click", () => {
        tabs.forEach((t) => t.setAttribute("aria-selected", "false"));
        tab.setAttribute("aria-selected", "true");
        panels.forEach((p) => (p.hidden = `tab-${tab.dataset.tab}` !== p.id));
      });
    });
  }

  function wireSearch() {
    document.querySelector("#ss-library-search")
      .addEventListener("input", (e) => filterCards("#ss-library", e.target.value));
  }

  function filterCards(container, term) {
    const needle = term.trim().toLowerCase();
    const cards = document.querySelectorAll(`${container} .card`);
    for (const card of cards) {
      const title = card.dataset.title || "";
      card.hidden = needle && !title.toLowerCase().includes(needle);
    }
  }

  // ----- Status tab -------------------------------------------------

  // Generation counter guards against interleaved renders (e.g. initial
  // render + SSE snapshot arriving while the first await is still pending).
  let statusRenderGen = 0;

  async function renderStatus(snapshot) {
    const gen = ++statusRenderGen;
    try {
      const data = snapshot || (await api.status());
      if (gen !== statusRenderGen) return;
      const summary = data.summary || {};
      const progress = data.progress || [];

      const items = await api.queueList();
      if (gen !== statusRenderGen) return;

      const summaryEl = document.querySelector("#ss-summary");
      summaryEl.innerHTML = "";
      for (const [label, value] of Object.entries(summary)) {
        const span = document.createElement("span");
        span.textContent = `${label}: ${value}`;
        summaryEl.appendChild(span);
      }

      const queueEl = document.querySelector("#ss-queue");
      queueEl.innerHTML = "";
      if (!items.length) {
        queueEl.innerHTML = '<div class="empty">Keine offenen Einträge.</div>';
      } else {
        const progressByName = new Map(progress.map((p) => [p.name, p]));
        for (const item of items) {
          queueEl.appendChild(renderQueueCard(item, progressByName));
        }
      }
    } catch (err) {
      console.warn("[streamseeker] renderStatus failed", err);
    }
  }

  function renderProgressRow(bar) {
    const row = document.createElement("div");
    row.className = "active__row";

    const title = document.createElement("div");
    title.textContent = `${bar.name}  ${bar.pct ? bar.pct.toFixed(1) + "%" : ""}`;
    row.appendChild(title);

    const track = document.createElement("div");
    track.className = "active__bar";
    const fill = document.createElement("div");
    fill.className = "active__bar-fill";
    fill.style.width = `${Math.max(0, Math.min(100, bar.pct || 0))}%`;
    track.appendChild(fill);
    row.appendChild(track);
    return row;
  }

  // ----- Library & Favorites ---------------------------------------

  async function renderUpdates(rows) {
    const container = document.querySelector("#ss-updates");
    const tab = document.querySelector('[data-tab="updates"]');
    const badge = document.querySelector("#ss-updates-badge");
    container.innerHTML = "";

    pendingKeys = new Set((rows || []).map((r) => r.key));

    if (!rows || !rows.length) {
      tab.hidden = true;
      badge.classList.remove("is-visible");
      return;
    }

    tab.hidden = false;
    badge.textContent = String(rows.length);
    badge.classList.add("is-visible");

    for (const row of rows) {
      container.appendChild(renderUpdateCard(row));
    }
  }

  function renderUpdateCard(row) {
    const card = document.createElement("div");
    card.className = "card";
    card.dataset.title = row.title || row.slug || "";

    const url = seriesUrlFor({ stream: row.stream, slug: row.slug });
    if (url) {
      card.title = `Auf ${STREAM_LABELS[row.stream] || row.stream} öffnen`;
      card.addEventListener("click", (ev) => {
        if (ev.target.closest("button")) return;
        chrome.tabs.create({ url });
      });
    }

    const poster = document.createElement("div");
    poster.className = "card__poster";
    poster.style.backgroundImage = `url("${api.posterUrl(row.key)}")`;
    card.appendChild(poster);

    const body = document.createElement("div");
    body.className = "card__body";
    const title = document.createElement("div");
    title.className = "card__title";
    title.textContent = (row.title || row.slug || row.key);
    body.appendChild(title);

    const badges = document.createElement("div");
    badges.className = "updates__badge-list";
    for (const u of row.pending_updates || []) {
      const label = UPDATE_LABELS[u.type] ? UPDATE_LABELS[u.type](u) : u.type;
      const pill = document.createElement("span");
      pill.className = "updates__pill";
      pill.textContent = label;
      badges.appendChild(pill);
    }
    body.appendChild(badges);
    card.appendChild(body);

    const actions = document.createElement("div");
    actions.className = "card__actions";
    const dismissBtn = document.createElement("button");
    dismissBtn.type = "button";
    dismissBtn.textContent = "✓";
    dismissBtn.title = "Als gesehen markieren";
    dismissBtn.addEventListener("click", async (ev) => {
      ev.stopPropagation();
      try {
        await api.updatesDismiss(row.key);
        const rows = await api.updatesList();
        await renderUpdates(rows);
        renderLibrary();
        renderFavorites();
      } catch (err) {
        console.warn("[streamseeker] dismiss failed", err);
      }
    });
    actions.appendChild(dismissBtn);
    card.appendChild(actions);

    return card;
  }

  async function renderLibrary() {
    const container = document.querySelector("#ss-library");
    container.innerHTML = "";
    try {
      const rows = await api.libraryList();
      libraryFilter.rows = rows;
      const repaint = () => paintLibrary(container, libraryFilter);
      renderFilterChips("#ss-library-filter", rows, libraryFilter, repaint);
      repaint();
    } catch (err) {
      container.innerHTML = '<div class="empty">Konnte Sammlung nicht laden.</div>';
    }
  }

  async function renderFavorites() { /* legacy no-op */ }

  function paintLibrary(container, filterState) {
    container.innerHTML = "";
    let rows = filterState.rows;
    if (filterState.stream) rows = rows.filter((r) => r.stream === filterState.stream);
    if (filterState.favoritesOnly) rows = rows.filter((r) => r.favorite);
    if (!rows.length) {
      container.innerHTML = '<div class="empty">Sammlung ist leer.</div>';
      return;
    }
    for (const row of rows) {
      container.appendChild(renderCard(row, { showPromote: false }));
    }
  }

  function renderFilterChips(selector, rows, filterState, onChange) {
    const host = document.querySelector(selector);
    host.innerHTML = "";
    const streams = Array.from(new Set(rows.map((r) => r.stream).filter(Boolean))).sort();
    const hasFavorites = rows.some((r) => r.favorite);
    if (streams.length < 2 && !hasFavorites) return;

    // ⭐ "Nur Favoriten" chip
    if (hasFavorites) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "chip chip--fav";
      btn.textContent = "⭐ Favoriten";
      if (filterState.favoritesOnly) btn.classList.add("chip--active");
      btn.addEventListener("click", () => {
        filterState.favoritesOnly = !filterState.favoritesOnly;
        btn.classList.toggle("chip--active", filterState.favoritesOnly);
        onChange();
      });
      host.appendChild(btn);
    }

    if (streams.length < 2) return;

    const addChip = (value, label) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "chip";
      btn.textContent = label;
      if (filterState.stream === value) btn.classList.add("chip--active");
      btn.addEventListener("click", () => {
        filterState.stream = value;
        host.querySelectorAll(".chip:not(.chip--fav)").forEach((c) => c.classList.remove("chip--active"));
        btn.classList.add("chip--active");
        onChange();
      });
      host.appendChild(btn);
    };

    addChip(null, "Alle");
    for (const s of streams) addChip(s, STREAM_LABELS[s] || s);
  }

  function seriesUrlFor(row) {
    const builder = STREAM_URL_BUILDERS[row.stream];
    return builder ? builder(row.slug) : null;
  }

  function episodeUrlFor(stream, slug, season, episode) {
    const base = STREAM_URL_BUILDERS[stream] ? STREAM_URL_BUILDERS[stream](slug) : null;
    if (!base) return null;
    if (stream === "megakinotax") return base;  // movies have no S/E segment
    if (season && episode) return `${base}/staffel-${season}/episode-${episode}`;
    if (season) return `${base}/staffel-${season}`;
    return base;
  }

  const STATUS_LABELS = {
    pending: "wartend",
    downloading: "läuft",
    paused: "pausiert",
    failed: "fehlgeschlagen",
    skipped: "übersprungen",
  };

  function renderQueueCard(item, progressByName) {
    const stream = item.stream_name;
    const slug = item.name;
    const key = stream && slug ? `${stream}::${slug}` : null;
    const season = Number(item.season) || 0;
    const episode = Number(item.episode) || 0;
    const status = item.status || "pending";

    const card = document.createElement("div");
    card.className = "card";
    card.dataset.title = slug || "";

    const url = episodeUrlFor(stream, slug, season, episode);
    if (url) {
      card.title = `Auf ${STREAM_LABELS[stream] || stream} öffnen`;
      card.addEventListener("click", (ev) => {
        if (ev.target.closest("button")) return;
        chrome.tabs.create({ url });
      });
    } else {
      card.style.cursor = "default";
    }

    const poster = document.createElement("div");
    poster.className = "card__poster";
    if (key) poster.style.backgroundImage = `url("${api.posterUrl(key)}")`;
    card.appendChild(poster);

    const body = document.createElement("div");
    body.className = "card__body";
    const title = document.createElement("div");
    title.className = "card__title";
    title.textContent = slug || item.file_name || "?";
    body.appendChild(title);
    const meta = document.createElement("div");
    meta.className = "card__meta";
    const epLabel = item.type === "filme"
      ? "Film"
      : (season && episode ? `S${season}E${episode}` : season ? `Staffel ${season}` : "");
    // Downloader registers bars under full path (standard) or basename (ffmpeg),
    // so look up by both to cover HLS + direct-HTTP cases.
    const basename = item.file_name ? item.file_name.split(/[\\/]/).pop() : null;
    const progressMatch = progressByName && (
      progressByName.get(item.file_name)
      || (basename ? progressByName.get(basename) : null)
      || progressByName.get(slug)
    );
    const pctText = progressMatch && progressMatch.pct
      ? ` · ${progressMatch.pct.toFixed(1)}%` : "";
    meta.textContent = `${STATUS_LABELS[status] || status}${epLabel ? " · " + epLabel : ""}${pctText}`;
    body.appendChild(meta);

    if (progressMatch) {
      const track = document.createElement("div");
      track.className = "active__bar";
      const fill = document.createElement("div");
      fill.className = "active__bar-fill";
      fill.style.width = `${Math.max(0, Math.min(100, progressMatch.pct || 0))}%`;
      track.appendChild(fill);
      body.appendChild(track);
    }
    card.appendChild(body);

    const actions = document.createElement("div");
    actions.className = "card__actions";

    const runAction = async (fn) => {
      try {
        await fn();
        renderStatus();
      } catch (err) {
        console.warn("[streamseeker] queue action failed", err);
      }
    };

    if (status === "paused") {
      actions.appendChild(makeActionBtn("▶", "Fortsetzen",
        () => runAction(() => api.queueResume(item.file_name))));
    } else if (status === "failed" || status === "skipped") {
      actions.appendChild(makeActionBtn("↻", "Neu einreihen",
        () => runAction(() => api.queueRetry(item.file_name))));
    } else if (status === "downloading" || status === "pending") {
      actions.appendChild(makeActionBtn("⏸", "Pausieren",
        () => runAction(() => api.queuePause(item.file_name))));
    }
    actions.appendChild(makeActionBtn("✕", "Entfernen",
      () => runAction(() => api.queueDelete(item.file_name))));

    card.appendChild(actions);
    return card;
  }

  function makeActionBtn(label, titleText, handler) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = label;
    btn.title = titleText;
    btn.addEventListener("click", (ev) => {
      ev.stopPropagation();
      handler();
    });
    return btn;
  }

  function renderCard(row, { showPromote }) {
    const card = document.createElement("div");
    card.className = "card";
    card.dataset.title = row.title || row.slug || "";

    const url = seriesUrlFor(row);
    if (url) {
      card.title = `Auf ${STREAM_LABELS[row.stream] || row.stream} öffnen`;
      card.addEventListener("click", (ev) => {
        if (ev.target.closest("button")) return;  // let action buttons handle themselves
        chrome.tabs.create({ url });
      });
    } else {
      card.style.cursor = "default";
    }

    const poster = document.createElement("div");
    poster.className = "card__poster";
    poster.style.backgroundImage = `url("${api.posterUrl(row.key)}")`;
    card.appendChild(poster);

    const body = document.createElement("div");
    body.className = "card__body";
    const title = document.createElement("div");
    title.className = "card__title";
    title.textContent = row.title || row.slug;
    if (pendingKeys.has(row.key)) {
      const star = document.createElement("span");
      star.className = "card__star";
      star.textContent = "★";
      star.title = "Neues Material verfügbar";
      title.appendChild(star);
    }
    body.appendChild(title);
    const meta = document.createElement("div");
    meta.className = "card__meta";
    meta.textContent = `${row.stream}${row.year ? " · " + row.year : ""}`;
    body.appendChild(meta);
    card.appendChild(body);

    const right = document.createElement("div");
    right.className = "card__actions";
    const progress = document.createElement("div");
    progress.className = "card__progress";
    const total = row.total_count || 0;
    const dl = row.downloaded_count || 0;
    progress.textContent = total ? `${dl}/${total}` : `${dl}`;
    right.appendChild(progress);

    const favBtn = document.createElement("button");
    favBtn.type = "button";
    favBtn.className = `card__fav-btn ${row.favorite ? "is-on" : ""}`;
    favBtn.textContent = row.favorite ? "★" : "☆";
    favBtn.title = row.favorite ? "Aus Favoriten entfernen" : "Als Favorit markieren";
    favBtn.addEventListener("click", async (ev) => {
      ev.stopPropagation();
      try {
        if (row.favorite) {
          await api.favoritesRemove(row.key);
          row.favorite = false;
        } else {
          await api.favoritesAdd(row.stream, row.slug);
          row.favorite = true;
        }
        favBtn.textContent = row.favorite ? "★" : "☆";
        favBtn.classList.toggle("is-on", row.favorite);
        favBtn.title = row.favorite ? "Aus Favoriten entfernen" : "Als Favorit markieren";
      } catch (err) {
        console.warn("[streamseeker] favorite toggle failed", err);
      }
    });
    right.appendChild(favBtn);

    card.appendChild(right);
    return card;
  }

  document.addEventListener("DOMContentLoaded", init);
})();
