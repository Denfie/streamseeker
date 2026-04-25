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
    sto: (slug) => `https://s.to/serie/${slug}`,
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
      // Show both ext + CLI in the header so it's obvious whether the
      // browser-side or daemon-side build is what the user expects.
      const manifest = chrome.runtime.getManifest();
      document.querySelector("#ss-version").textContent =
        `ext ${manifest.version} · CLI ${version.cli}`;
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
        if (tab.dataset.tab === "settings") renderSettings();
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

  // FSK-Farbschema: 0 = weiß, 6 = gelb, 12 = grün, 16 = blau, 18 = rot.
  // Akzeptiert "FSK 12", "12", 12. Andere Zertifikate (z.B. "TV-MA")
  // werden ignoriert, weil sie keine FSK-Zahl sind.
  function parseFskNumber(raw) {
    if (raw == null) return null;
    const m = String(raw).match(/\b(\d{1,2})\b/);
    if (!m) return null;
    const n = parseInt(m[1], 10);
    return [0, 6, 12, 16, 18].includes(n) ? n : null;
  }

  function renderFskBadge(raw) {
    const n = parseFskNumber(raw);
    if (n == null) return null;
    const badge = document.createElement("span");
    badge.className = `fsk-badge fsk-badge--${n}`;
    badge.textContent = String(n);
    badge.title = `FSK ${n}`;
    return badge;
  }

  function renderCard(row, { showPromote }) {
    const card = document.createElement("div");
    card.className = "card";
    card.dataset.title = row.title || row.slug || "";

    card.title = "Details anzeigen";
    card.addEventListener("click", (ev) => {
      if (ev.target.closest("button")) return;  // let action buttons handle themselves
      showDetailModal(row);
    });

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

    const fskBadge = renderFskBadge(row.fsk);
    if (fskBadge) right.appendChild(fskBadge);

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

  // ----- Detail modal ---------------------------------------------

  let savedScrollY = 0;

  async function showDetailModal(row) {
    const modal = document.querySelector("#ss-detail");
    const alreadyOpen = !modal.hidden;
    if (!alreadyOpen) {
      // Remember where the user was so we can jump back on close.
      savedScrollY = window.scrollY || document.documentElement.scrollTop || 0;
      document.documentElement.classList.add("ss-detail-open");
      document.body.classList.add("ss-detail-open");
      modal.scrollTop = 0;
    }
    const backdrop = document.querySelector("#ss-detail-backdrop");
    const poster = document.querySelector("#ss-detail-poster");
    const titleEl = document.querySelector("#ss-detail-title");
    const metaEl = document.querySelector("#ss-detail-meta");
    const genresEl = document.querySelector("#ss-detail-genres");
    const overviewEl = document.querySelector("#ss-detail-overview");
    const statsEl = document.querySelector("#ss-detail-stats");
    const actionsEl = document.querySelector("#ss-detail-actions");

    // Initial fast render from index row; enrich with full entry below.
    poster.style.backgroundImage = `url("${api.posterUrl(row.key)}")`;
    backdrop.style.backgroundImage = `url("${api.backdropUrl(row.key)}")`;
    titleEl.textContent = row.title || row.slug || row.key;
    metaEl.innerHTML = "";
    genresEl.innerHTML = "";
    overviewEl.textContent = "Details werden geladen…";
    statsEl.innerHTML = "";
    actionsEl.innerHTML = "";

    modal.hidden = false;
    modal.setAttribute("aria-hidden", "false");

    let entry;
    try {
      entry = await api.libraryGet(row.key);
    } catch (err) {
      overviewEl.textContent = `Konnte Details nicht laden: ${err.message}`;
      return;
    }

    // Merge all provider blocks so the modal shows every available field.
    // Preference order: earlier entries win per-field when multiple providers
    // carry the same data. Artwork always wins from the stored block.
    const external = entry.external || {};
    const preference = ["tmdb", "tvdb", "anilist", "omdb", "tvmaze", "jikan"];
    const providersOrdered = [
      ...preference.filter((p) => external[p]),
      ...Object.keys(external).filter((p) => !preference.includes(p)),
    ];
    const ext = {};
    for (const name of providersOrdered) {
      const block = external[name] || {};
      for (const [k, v] of Object.entries(block)) {
        if (ext[k] == null && v != null) ext[k] = v;
      }
    }

    // Title + pills row
    titleEl.textContent = entry.title || ext.title || entry.slug || entry.key;
    const pills = [];
    const year = entry.year || ext.year;
    if (year) pills.push(["", `${year}`]);
    if (ext.fsk) pills.push(["detail__pill--fsk", ext.fsk]);
    if (ext.rating) pills.push(["detail__pill--rating", `★ ${ext.rating.toFixed(1)}`]);
    if (entry.favorite) pills.push(["detail__pill--fav", "⭐ Favorit"]);
    const streamLabel = STREAM_LABELS[entry.stream] || entry.stream;
    if (streamLabel) pills.push(["", streamLabel]);
    for (const [cls, text] of pills) {
      const span = document.createElement("span");
      span.className = `detail__pill ${cls}`.trim();
      span.textContent = text;
      metaEl.appendChild(span);
    }

    // Genres
    for (const g of (ext.genres || [])) {
      const span = document.createElement("span");
      span.textContent = `#${g}`;
      genresEl.appendChild(span);
    }

    // Overview
    overviewEl.textContent = ext.overview || (ext.extra && ext.extra.description) || "Keine Beschreibung verfügbar.";

    // Stats
    const seasons = entry.seasons || {};
    const seasonCount = Object.keys(seasons).length;
    const totalEpisodes = Object.values(seasons).reduce((a, s) => a + (s.episode_count || 0), 0);
    const downloaded = Object.values(seasons).reduce((a, s) => a + ((s.downloaded || []).length), 0);
    const stats = [
      ["Staffeln", String(seasonCount)],
      ["Episoden", totalEpisodes ? `${downloaded} / ${totalEpisodes}` : String(downloaded)],
    ];
    for (const [label, value] of stats) {
      const cell = document.createElement("div");
      const strong = document.createElement("strong");
      strong.textContent = value;
      cell.appendChild(strong);
      const sub = document.createElement("span");
      sub.textContent = label;
      cell.appendChild(sub);
      statsEl.appendChild(cell);
    }

    // Actions — three rows:
    //   1. Primary button (full-width): "Auf <Seite> öffnen"
    //   2. Icon-only tool row: refresh / search / delete
    //   3. Provider-link chips below (TMDb, AniList, …)
    const url = seriesUrlFor(row);
    if (url) {
      const openBtn = document.createElement("button");
      openBtn.type = "button";
      openBtn.className = "detail__primary";
      openBtn.textContent = `Auf ${streamLabel || "Seite"} öffnen`;
      openBtn.addEventListener("click", () => {
        chrome.tabs.create({ url });
        hideDetailModal();
      });
      actionsEl.appendChild(openBtn);
    }

    const iconRow = document.createElement("div");
    iconRow.className = "detail__icon-row";

    const refreshBtn = iconButton("↻", "Metadaten neu laden", async (btn) => {
      btn.disabled = true;
      const prev = btn.textContent;
      btn.textContent = "…";
      try {
        await api.libraryRefresh(row.key);
        await showDetailModal(row);
      } catch (err) {
        btn.textContent = "✕";
        btn.title = err.message || "Fehlgeschlagen";
        setTimeout(() => { btn.textContent = prev; btn.disabled = false; }, 2000);
      }
    });
    iconRow.appendChild(refreshBtn);

    const tuneBtn = iconButton("🔎", "Mit anderem Titel/Jahr neu suchen", () => {
      openSearchOverride(row, actionsEl, entry);
    });
    iconRow.appendChild(tuneBtn);

    const folderBtn = iconButton("📁", "Sammlung im Finder/Explorer öffnen", async (btn) => {
      btn.disabled = true;
      const prev = btn.textContent;
      btn.textContent = "…";
      try {
        await api.libraryOpenFolder(row.key);
        btn.textContent = prev;
        btn.disabled = false;
      } catch (err) {
        btn.textContent = "✕";
        btn.title = err.message || "Fehler";
        setTimeout(() => { btn.textContent = prev; btn.disabled = false; }, 2000);
      }
    });
    iconRow.appendChild(folderBtn);

    const deleteBtn = iconButton("🗑", "Aus Sammlung entfernen", async (btn) => {
      const label = entry.title || entry.slug || entry.key;
      if (!confirm(`"${label}" aus der Sammlung entfernen?\n\nDie heruntergeladenen Videos bleiben erhalten — nur der Sammlungs-Eintrag (inkl. Metadaten & Cover) wird gelöscht.`)) return;
      btn.disabled = true;
      btn.textContent = "…";
      try {
        await api.libraryDelete(row.key);
        hideDetailModal();
        await renderLibrary();
      } catch (err) {
        btn.textContent = "✕";
        btn.title = err.message || "Fehler";
        setTimeout(() => { btn.disabled = false; btn.textContent = "🗑"; }, 2000);
      }
    });
    deleteBtn.classList.add("detail__icon-btn--danger");
    iconRow.appendChild(deleteBtn);
    actionsEl.appendChild(iconRow);

    const providerRow = document.createElement("div");
    providerRow.className = "detail__provider-row";
    for (const [providerName, block] of Object.entries(external)) {
      if (!block || !block.source_url) continue;
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "detail__provider-chip";
      chip.textContent = `${providerName.toUpperCase()} ↗`;
      chip.title = block.source_url;
      chip.addEventListener("click", () => {
        chrome.tabs.create({ url: block.source_url });
      });
      providerRow.appendChild(chip);
    }
    if (providerRow.children.length) actionsEl.appendChild(providerRow);
  }

  function iconButton(glyph, titleText, onClick) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "detail__icon-btn";
    btn.textContent = glyph;
    btn.title = titleText;
    btn.setAttribute("aria-label", titleText);
    btn.addEventListener("click", () => onClick(btn));
    return btn;
  }

  function openSearchOverride(row, actionsEl, entry) {
    // Replace the actions row with a small form: title + year + "Suchen".
    const existing = document.querySelector("#ss-search-override");
    if (existing) { existing.remove(); return; }

    const form = document.createElement("form");
    form.id = "ss-search-override";
    form.className = "detail__search-override";

    const titleInput = document.createElement("input");
    titleInput.type = "text";
    titleInput.placeholder = "Alternativer Titel (z.B. Stargate SG-1)";
    titleInput.value = entry.title || "";

    const yearInput = document.createElement("input");
    yearInput.type = "number";
    yearInput.placeholder = "Jahr";
    yearInput.min = "1900";
    yearInput.max = "2099";
    yearInput.value = entry.year || "";

    const submit = document.createElement("button");
    submit.type = "submit";
    submit.textContent = "Suchen & Ersetzen";

    form.appendChild(titleInput);
    form.appendChild(yearInput);
    form.appendChild(submit);

    form.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      submit.disabled = true;
      submit.textContent = "…";
      try {
        await api.libraryRefresh(row.key, {
          title: titleInput.value.trim() || undefined,
          year: yearInput.value ? parseInt(yearInput.value, 10) : undefined,
          reset: true,
        });
        await showDetailModal(row);
      } catch (err) {
        submit.textContent = "✕ " + (err.message || "Fehler");
      }
    });

    actionsEl.parentElement.insertBefore(form, actionsEl);
    titleInput.focus();
    titleInput.select();
  }

  function hideDetailModal() {
    const modal = document.querySelector("#ss-detail");
    modal.hidden = true;
    modal.setAttribute("aria-hidden", "true");
    document.documentElement.classList.remove("ss-detail-open");
    document.body.classList.remove("ss-detail-open");
    // Restore the scroll position the user had before opening the modal.
    window.scrollTo(0, savedScrollY);
  }

  // ----- Settings tab ----------------------------------------------

  const PROVIDER_CHOICES = ["voe", "vidoza", "streamtape", "doodstream", "speedfiles", "filemoon", "vidmoly"];

  async function renderSettings() {
    const host = document.querySelector("#ss-settings");
    host.innerHTML = '<div class="settings__loading">Lade Einstellungen…</div>';
    let data;
    try {
      data = await api.settingsGet();
    } catch (err) {
      host.innerHTML = `<div class="empty">Konnte Einstellungen nicht laden: ${err.message}</div>`;
      return;
    }
    host.innerHTML = "";
    host.appendChild(buildSettingsForm(data));
  }

  function buildSettingsForm(data) {
    const wrap = document.createElement("div");
    wrap.className = "settings";

    // --- Section: Daemon-Info (read-only) ---
    const info = document.createElement("section");
    info.className = "settings__section";
    info.innerHTML = `<h3>Daemon</h3>`;
    const dl = document.createElement("dl");
    dl.className = "settings__info";
    [
      ["Home", data.paths.home],
      ["Sammlung", data.paths.downloads],
      ["Library", data.paths.library],
      ["Config-Datei", data.paths.config_file],
    ].forEach(([k, v]) => {
      const dt = document.createElement("dt"); dt.textContent = k;
      const dd = document.createElement("dd"); dd.textContent = v;
      dl.appendChild(dt); dl.appendChild(dd);
    });
    info.appendChild(dl);
    wrap.appendChild(info);

    // --- Section: Sammlung (queue + pipeline tuning) ---
    const dlSection = document.createElement("section");
    dlSection.className = "settings__section";
    dlSection.innerHTML = `<h3>Sammlung</h3>`;

    const providerLabel = labeledField("Bevorzugter Provider", "preferred_provider");
    const providerSelect = document.createElement("select");
    providerSelect.id = "settings-preferred-provider";
    PROVIDER_CHOICES.forEach((p) => {
      const o = document.createElement("option");
      o.value = p; o.textContent = p;
      if (data.config.preferred_provider === p) o.selected = true;
      providerSelect.appendChild(o);
    });
    providerLabel.appendChild(providerSelect);
    dlSection.appendChild(providerLabel);

    const concLabel = labeledField("Max. parallele Aktivitäten", "max_concurrent");
    const concInput = document.createElement("input");
    concInput.type = "number"; concInput.id = "settings-max-concurrent";
    concInput.min = "1"; concInput.max = "10";
    concInput.value = data.config.max_concurrent ?? 5;
    concLabel.appendChild(concInput);
    dlSection.appendChild(concLabel);

    const retryLabel = labeledField("Max. Retry-Versuche", "max_retries");
    const retryInput = document.createElement("input");
    retryInput.type = "number"; retryInput.id = "settings-max-retries";
    retryInput.min = "0"; retryInput.max = "10";
    retryInput.value = data.config.max_retries ?? 3;
    retryLabel.appendChild(retryInput);
    dlSection.appendChild(retryLabel);

    wrap.appendChild(dlSection);

    // --- Section: Metadata ---
    const meta = document.createElement("section");
    meta.className = "settings__section";
    meta.innerHTML = `<h3>Metadaten</h3>`;

    const tmdbLabel = labeledField(
      `TMDb API-Key${data.credentials.tmdb ? " (gesetzt — leer lassen, um beizubehalten)" : ""}`,
      "tmdb_api_key"
    );
    const tmdbInput = document.createElement("input");
    tmdbInput.type = "password";
    tmdbInput.id = "settings-tmdb-key";
    tmdbInput.placeholder = data.credentials.tmdb
      ? "•••••••••• (gesetzt)"
      : "Schlüssel aus themoviedb.org";
    tmdbLabel.appendChild(tmdbInput);
    meta.appendChild(tmdbLabel);

    const hint = document.createElement("p");
    hint.className = "settings__hint";
    hint.innerHTML = `TMDb-Key holen → <a href="https://www.themoviedb.org/settings/api" target="_blank" rel="noopener">themoviedb.org/settings/api</a>. Ohne Key fallen Stream-Ketten auf AniList/Jikan/TVmaze zurück (kein FSK).`;
    meta.appendChild(hint);

    wrap.appendChild(meta);

    // --- Save row ---
    const actions = document.createElement("div");
    actions.className = "settings__actions";
    const saveBtn = document.createElement("button");
    saveBtn.type = "button";
    saveBtn.className = "detail__primary";
    saveBtn.textContent = "Speichern";
    const status = document.createElement("span");
    status.className = "settings__status";

    saveBtn.addEventListener("click", async () => {
      saveBtn.disabled = true;
      saveBtn.textContent = "Speichere…";
      status.textContent = "";
      const payload = {
        config: {
          preferred_provider: providerSelect.value,
          max_concurrent: parseInt(concInput.value, 10) || 5,
          max_retries: parseInt(retryInput.value, 10) || 3,
        },
      };
      const tmdb = tmdbInput.value.trim();
      if (tmdb) payload.tmdb_api_key = tmdb;
      try {
        await api.settingsPatch(payload);
        status.textContent = "Gespeichert ✓";
        status.style.color = "var(--success)";
        tmdbInput.value = "";
        // Re-render so the "(gesetzt)" hint reflects reality
        setTimeout(renderSettings, 800);
      } catch (err) {
        status.textContent = `✕ ${err.message || "Fehler"}`;
        status.style.color = "var(--danger)";
      } finally {
        saveBtn.disabled = false;
        saveBtn.textContent = "Speichern";
      }
    });

    actions.appendChild(saveBtn);
    actions.appendChild(status);
    wrap.appendChild(actions);

    return wrap;
  }

  function labeledField(text, htmlForId) {
    const lbl = document.createElement("label");
    lbl.className = "settings__field";
    const span = document.createElement("span");
    span.textContent = text;
    lbl.appendChild(span);
    if (htmlForId) lbl.htmlFor = `settings-${htmlForId.replace(/_/g, "-")}`;
    return lbl;
  }

  function wireDetailModal() {
    document.querySelector("#ss-detail-close").addEventListener("click", hideDetailModal);
    document.addEventListener("keydown", (ev) => {
      if (ev.key === "Escape") hideDetailModal();
    });
  }

  document.addEventListener("DOMContentLoaded", () => { init(); wireDetailModal(); });
})();
