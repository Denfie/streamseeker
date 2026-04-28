// Popup controller — status, library, favorites.
//
// Uses window.ssApi (from ../lib/api.js, loaded before this script).

(function () {
  const api = window.ssApi;
  let minCliVersion = "0.0.0";

  const STREAM_LABELS = {
    aniworldto: "AniWorld",
    sto: "S.to",
  };

  const STREAM_URL_BUILDERS = {
    aniworldto: (slug) => `https://aniworld.to/anime/stream/${slug}`,
    sto: (slug) => `https://s.to/serie/${slug}`,
  };

  const libraryFilter = {
    stream: null,
    favoritesOnly: false,
    fsk: null,
    searchTerm: "",
    rows: [],
  };
  const UPDATE_LABELS = {
    new_season: (u) => `neue Staffel ${u.season}`,
    new_episode: (u) => `S${u.season}: +${(u.to || 0) - (u.from || 0)} Episode${((u.to || 0) - (u.from || 0)) === 1 ? "" : "n"}`,
    new_movie: (u) => `neuer Film`,
  };
  let pendingKeys = new Set();

  async function init() {
    await loadManifestMeta();
    await loadActiveLanguage();
    wireTabs();
    wireSearch();
    bindUpdatesToolbar();
    bindLibraryFilterButton();

    try {
      const daemonAlive = await api.isDaemonAlive();
      if (!daemonAlive) {
        showBanner(window.ssI18n.t("header.banner.daemon_unreachable"));
        return;
      }

      const version = await api.version();
      // Show both ext + CLI in the header so it's obvious whether the
      // browser-side or daemon-side build is what the user expects.
      const manifest = chrome.runtime.getManifest();
      document.querySelector("#ss-version").textContent =
        `ext ${manifest.version} · CLI ${version.cli}`;
      if (!api.versionGte(version.cli, minCliVersion)) {
        showBanner(window.ssI18n.t("header.banner.cli_too_old", { cli: version.cli, min: minCliVersion }));
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

  async function loadActiveLanguage() {
    // Pull the language the daemon thinks is active so the popup uses
    // the same locale as the CLI/daemon. Fail open: stay on English.
    try {
      const settings = await api.settingsGet();
      const code = settings && settings.config && settings.config.language;
      if (code && window.ssI18n) window.ssI18n.setLanguage(code);
    } catch (_) { /* ignore — daemon might be down */ }
    applyStaticI18n();
  }

  // Apply translations to all data-i18n* attributes in the static DOM.
  // Called on init() and again after the language toggle saves.
  function applyStaticI18n() {
    if (!window.ssI18n) return;
    const t = window.ssI18n.t;
    document.querySelectorAll("[data-i18n]").forEach((el) => {
      el.textContent = t(el.getAttribute("data-i18n"));
    });
    document.querySelectorAll("[data-i18n-title]").forEach((el) => {
      el.title = t(el.getAttribute("data-i18n-title"));
    });
    document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
      el.placeholder = t(el.getAttribute("data-i18n-placeholder"));
    });
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
    document.querySelector("#ss-library-search").addEventListener("input", (e) => {
      libraryFilter.searchTerm = e.target.value || "";
      const container = document.querySelector("#ss-library");
      paintLibrary(container, libraryFilter);
      updateFilterButtonState();
    });
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
        queueEl.innerHTML = `<div class="empty">${window.ssI18n.t("empty.queue")}</div>`;
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
    const toolbar = document.querySelector("#ss-updates-toolbar");
    container.innerHTML = "";

    pendingKeys = new Set((rows || []).map((r) => r.key));

    if (!rows || !rows.length) {
      tab.hidden = true;
      badge.classList.remove("is-visible");
      if (toolbar) toolbar.hidden = true;
      return;
    }

    tab.hidden = false;
    badge.textContent = String(rows.length);
    badge.classList.add("is-visible");
    if (toolbar) toolbar.hidden = false;

    for (const row of rows) {
      container.appendChild(renderUpdateCard(row));
    }
  }

  function bindUpdatesToolbar() {
    const btn = document.querySelector("#ss-updates-dismiss-all");
    if (!btn || btn.dataset.bound === "1") return;
    btn.dataset.bound = "1";
    btn.addEventListener("click", async () => {
      btn.disabled = true;
      try {
        await api.updatesDismissAll();
        const rows = await api.updatesList();
        await renderUpdates(rows);
        renderLibrary();
        renderFavorites();
      } catch (err) {
        console.warn("[streamseeker] dismiss-all failed", err);
      } finally {
        btn.disabled = false;
      }
    });
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
    dismissBtn.className = "updates__dismiss";
    dismissBtn.textContent = window.ssI18n
      ? window.ssI18n.t("updates.dismiss")
      : "Als gelesen";
    dismissBtn.title = dismissBtn.textContent;
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
      const repaint = () => {
        paintLibrary(container, libraryFilter);
        updateFilterButtonState();
      };
      renderFilterPopover("#ss-library-filter-popover", rows, libraryFilter, repaint);
      repaint();
    } catch (err) {
      container.innerHTML = `<div class="empty">${window.ssI18n.t("empty.collection_load_failed")}</div>`;
    }
  }

  async function renderFavorites() { /* legacy no-op */ }

  function paintLibrary(container, filterState) {
    container.innerHTML = "";
    let rows = filterState.rows;
    if (filterState.stream) rows = rows.filter((r) => r.stream === filterState.stream);
    if (filterState.favoritesOnly) rows = rows.filter((r) => r.favorite);
    if (filterState.fsk != null) {
      rows = rows.filter((r) => parseFskNumber(r.fsk) === filterState.fsk);
    }
    const needle = (filterState.searchTerm || "").trim().toLowerCase();
    if (needle) {
      rows = rows.filter((r) => {
        const title = (r.title || r.slug || "").toLowerCase();
        return title.includes(needle);
      });
    }
    if (!rows.length) {
      container.innerHTML = `<div class="empty">${window.ssI18n.t("empty.collection")}</div>`;
      return;
    }
    for (const row of rows) {
      container.appendChild(renderCard(row, { showPromote: false }));
    }
  }

  // Strip "FSK " prefix and trailing punctuation; "FSK 12" → 12, "12" → 12,
  // "TV-MA" → null. Keeps the filter robust against TMDb's free-form fields.
  function parseFskNumber(raw) {
    if (raw == null) return null;
    const m = String(raw).match(/\d{1,2}/);
    if (!m) return null;
    const n = parseInt(m[0], 10);
    return [0, 6, 12, 16, 18].includes(n) ? n : null;
  }

  function activeFilterCount(filterState) {
    let c = 0;
    if (filterState.stream) c++;
    if (filterState.favoritesOnly) c++;
    if (filterState.fsk != null) c++;
    return c;
  }

  function updateFilterButtonState() {
    const btn = document.querySelector("#ss-library-filter-btn");
    if (!btn) return;
    const dot = btn.querySelector(".library__filter-dot");
    const c = activeFilterCount(libraryFilter);
    if (dot) {
      dot.hidden = c === 0;
      dot.textContent = c > 0 ? String(c) : "";
    }
    btn.classList.toggle("library__filter-btn--active", c > 0);
  }

  function renderFilterPopover(selector, rows, filterState, onChange) {
    const host = document.querySelector(selector);
    host.innerHTML = "";

    const t = window.ssI18n.t;
    const streams = Array.from(new Set(rows.map((r) => r.stream).filter(Boolean))).sort();
    const fskValues = Array.from(
      new Set(rows.map((r) => parseFskNumber(r.fsk)).filter((n) => n != null))
    ).sort((a, b) => a - b);

    const addSection = (titleKey, controls) => {
      if (!controls.length) return;
      const section = document.createElement("div");
      section.className = "library__filter-section";
      const heading = document.createElement("div");
      heading.className = "library__filter-heading";
      heading.textContent = t(titleKey);
      section.appendChild(heading);
      const group = document.createElement("div");
      group.className = "library__filter-group";
      controls.forEach((c) => group.appendChild(c));
      section.appendChild(group);
      host.appendChild(section);
    };

    const makeChip = (label, isActive, onClick, extraClass = "") => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = `chip${isActive ? " chip--active" : ""}${extraClass ? " " + extraClass : ""}`;
      btn.textContent = label;
      btn.addEventListener("click", onClick);
      return btn;
    };

    // Favorites toggle (only useful when at least one entry is starred)
    if (rows.some((r) => r.favorite)) {
      addSection("filter.section.favorites", [
        makeChip(
          t("filter.favorites"),
          filterState.favoritesOnly,
          () => {
            filterState.favoritesOnly = !filterState.favoritesOnly;
            renderFilterPopover(selector, rows, filterState, onChange);
            onChange();
          },
          "chip--fav"
        ),
      ]);
    }

    // Stream
    if (streams.length >= 2) {
      const chips = [
        makeChip(t("filter.all"), filterState.stream == null, () => {
          filterState.stream = null;
          renderFilterPopover(selector, rows, filterState, onChange);
          onChange();
        }),
        ...streams.map((s) =>
          makeChip(STREAM_LABELS[s] || s, filterState.stream === s, () => {
            filterState.stream = s;
            renderFilterPopover(selector, rows, filterState, onChange);
            onChange();
          })
        ),
      ];
      addSection("filter.section.stream", chips);
    }

    // FSK
    if (fskValues.length) {
      const chips = [
        makeChip(t("filter.all"), filterState.fsk == null, () => {
          filterState.fsk = null;
          renderFilterPopover(selector, rows, filterState, onChange);
          onChange();
        }),
        ...fskValues.map((n) =>
          makeChip(`FSK ${n}`, filterState.fsk === n, () => {
            filterState.fsk = n;
            renderFilterPopover(selector, rows, filterState, onChange);
            onChange();
          }, `chip--fsk fsk-badge--${n}`)
        ),
      ];
      addSection("filter.section.fsk", chips);
    }

    // Clear all (only if any filter is active)
    if (activeFilterCount(filterState) > 0) {
      const reset = document.createElement("button");
      reset.type = "button";
      reset.className = "library__filter-reset";
      reset.textContent = t("filter.reset");
      reset.addEventListener("click", () => {
        filterState.stream = null;
        filterState.favoritesOnly = false;
        filterState.fsk = null;
        renderFilterPopover(selector, rows, filterState, onChange);
        onChange();
      });
      host.appendChild(reset);
    }

    if (!host.children.length) {
      const empty = document.createElement("div");
      empty.className = "library__filter-empty";
      empty.textContent = t("filter.none_available");
      host.appendChild(empty);
    }
  }

  function bindLibraryFilterButton() {
    const btn = document.querySelector("#ss-library-filter-btn");
    const popover = document.querySelector("#ss-library-filter-popover");
    if (!btn || !popover || btn.dataset.bound === "1") return;
    btn.dataset.bound = "1";

    const close = () => {
      popover.hidden = true;
      btn.setAttribute("aria-expanded", "false");
    };
    const open = () => {
      popover.hidden = false;
      btn.setAttribute("aria-expanded", "true");
    };

    btn.addEventListener("click", (ev) => {
      ev.stopPropagation();
      popover.hidden ? open() : close();
    });
    document.addEventListener("click", (ev) => {
      if (popover.hidden) return;
      if (popover.contains(ev.target) || btn.contains(ev.target)) return;
      close();
    });
    document.addEventListener("keydown", (ev) => {
      if (ev.key === "Escape" && !popover.hidden) close();
    });
  }

  function seriesUrlFor(row) {
    const builder = STREAM_URL_BUILDERS[row.stream];
    return builder ? builder(row.slug) : null;
  }

  // Mirror of streamseeker.api.core.metadata.base.localize_block — when an
  // external block carries translations[lang], overlay {title, overview,
  // genres, tagline} from there; otherwise return the block unchanged so
  // English (the primary fetch language) acts as the universal fallback.
  function localizeExt(block, language) {
    if (!block || typeof block !== "object") return block || {};
    const tr = (block.translations || {})[language];
    if (!tr) return block;
    const merged = Object.assign({}, block);
    for (const key of ["title", "overview", "genres", "tagline"]) {
      const value = tr[key];
      if (value != null && value !== "" &&
          !(Array.isArray(value) && value.length === 0)) {
        merged[key] = value;
      }
    }
    return merged;
  }

  function statusLabel(status) {
    const t = window.ssI18n && window.ssI18n.t;
    if (!t) return status;
    const map = {
      pending: "queue.status.pending",
      downloading: "queue.status.running",
      paused: "queue.status.paused",
      failed: "queue.status.failed",
      skipped: "queue.status.skipped",
    };
    return t(map[status] || `queue.status.${status}`);
  }

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

    if (key) {
      card.title = window.ssI18n.t("card.show_details");
      card.addEventListener("click", (ev) => {
        if (ev.target.closest("button")) return;
        const cached = (libraryFilter.rows || []).find((r) => r.key === key);
        const row = cached || { key, stream, slug, title: slug };
        showDetailModal(row);
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
    meta.textContent = `${statusLabel(status)}${epLabel ? " · " + epLabel : ""}${pctText}`;
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

    card.title = window.ssI18n.t("card.show_details");
    card.addEventListener("click", (ev) => {
      if (ev.target.closest("button")) return;  // let action buttons handle themselves
      showDetailModal(row);
    });

    const poster = document.createElement("div");
    poster.className = "card__poster";
    poster.style.backgroundImage = `url("${api.posterUrl(row.key)}")`;
    // Overlay the FSK age rating in the bottom-left corner of the poster
    // so the listing stays compact and the meta column has more room.
    const fskOverlay = renderFskBadge(row.fsk);
    if (fskOverlay) {
      fskOverlay.classList.add("fsk-badge--overlay");
      poster.appendChild(fskOverlay);
    }
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
      star.title = window.ssI18n.t("card.update_indicator");
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
    favBtn.title = window.ssI18n.t(row.favorite ? "card.fav_remove" : "card.fav_add");
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
        favBtn.title = window.ssI18n.t(row.favorite ? "card.fav_remove" : "card.fav_add");
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
    overviewEl.textContent = window.ssI18n.t("detail.loading");
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
    // Each block is first overlaid with the active language's translation
    // (translations.{de}) when present, falling back to the provider's
    // top-level (English) fields.
    const activeLang = (window.ssI18n && window.ssI18n.getLanguage && window.ssI18n.getLanguage()) || "en";
    const external = entry.external || {};
    const preference = ["tmdb", "tvdb", "anilist", "omdb", "tvmaze", "jikan"];
    const providersOrdered = [
      ...preference.filter((p) => external[p]),
      ...Object.keys(external).filter((p) => !preference.includes(p)),
    ];
    const ext = {};
    for (const name of providersOrdered) {
      const block = localizeExt(external[name] || {}, activeLang);
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
    host.innerHTML = `<div class="settings__loading">${window.ssI18n.t("settings.loading")}</div>`;
    let data;
    try {
      data = await api.settingsGet();
    } catch (err) {
      host.innerHTML = `<div class="empty">${window.ssI18n.t("settings.load_failed", { message: err.message })}</div>`;
      return;
    }
    host.innerHTML = "";
    host.appendChild(buildSettingsForm(data));
  }

  function buildSettingsForm(data) {
    const wrap = document.createElement("div");
    wrap.className = "settings";

    const t = window.ssI18n.t;

    // --- Section: Daemon-Info (read-only) ---
    const info = document.createElement("section");
    info.className = "settings__section";
    info.innerHTML = `<h3>${t("settings.section.daemon")}</h3>`;
    const dl = document.createElement("dl");
    dl.className = "settings__info";
    [
      [t("settings.label.home"), data.paths.home],
      [t("settings.label.downloads"), data.paths.downloads],
      [t("settings.label.library"), data.paths.library],
      [t("settings.label.config_file"), data.paths.config_file],
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
    dlSection.innerHTML = `<h3>${t("settings.section.collection")}</h3>`;

    const providerLabel = labeledField(t("settings.label.preferred_provider"), "preferred_provider");
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

    const concLabel = labeledField(t("settings.label.max_concurrent"), "max_concurrent");
    const concInput = document.createElement("input");
    concInput.type = "number"; concInput.id = "settings-max-concurrent";
    concInput.min = "1"; concInput.max = "10";
    concInput.value = data.config.max_concurrent ?? 5;
    concLabel.appendChild(concInput);
    dlSection.appendChild(concLabel);

    const retryLabel = labeledField(t("settings.label.max_retries"), "max_retries");
    const retryInput = document.createElement("input");
    retryInput.type = "number"; retryInput.id = "settings-max-retries";
    retryInput.min = "0"; retryInput.max = "10";
    retryInput.value = data.config.max_retries ?? 3;
    retryLabel.appendChild(retryInput);
    dlSection.appendChild(retryLabel);

    wrap.appendChild(dlSection);

    // --- Section: Stream-Page Overlay ---
    const overlay = document.createElement("section");
    overlay.className = "settings__section";
    overlay.innerHTML = `<h3>${t("settings.section.overlay")}</h3>`;

    const overlayLabel = document.createElement("label");
    overlayLabel.className = "settings__field settings__field--checkbox";
    const overlayCheckbox = document.createElement("input");
    overlayCheckbox.type = "checkbox";
    overlayCheckbox.id = "settings-overlay-collapsed-default";
    // ?? handles the case where the daemon hasn't shipped the key yet
    overlayCheckbox.checked = data.config && data.config.overlay_collapsed_default !== false;
    const overlayText = document.createElement("span");
    overlayText.textContent = t("settings.overlay.collapsed_default");
    overlayLabel.appendChild(overlayCheckbox);
    overlayLabel.appendChild(overlayText);
    overlay.appendChild(overlayLabel);

    const overlayHint = document.createElement("p");
    overlayHint.className = "settings__hint";
    overlayHint.textContent = t("settings.overlay.hint");
    overlay.appendChild(overlayHint);

    wrap.appendChild(overlay);

    // --- Section: Metadata ---
    const meta = document.createElement("section");
    meta.className = "settings__section";
    meta.innerHTML = `<h3>${t("settings.section.metadata")}</h3>`;

    const tmdbLabel = labeledField(
      t(data.credentials.tmdb ? "settings.label.tmdb_key_set" : "settings.label.tmdb_key"),
      "tmdb_api_key"
    );
    const tmdbInput = document.createElement("input");
    tmdbInput.type = "password";
    tmdbInput.id = "settings-tmdb-key";
    tmdbInput.placeholder = t(data.credentials.tmdb
      ? "settings.tmdb.placeholder_set"
      : "settings.tmdb.placeholder_unset");
    tmdbLabel.appendChild(tmdbInput);
    meta.appendChild(tmdbLabel);

    const hint = document.createElement("p");
    hint.className = "settings__hint";
    hint.innerHTML = t("settings.tmdb.hint");
    meta.appendChild(hint);

    wrap.appendChild(meta);

    // --- Section: Sprache ---
    const lang = document.createElement("section");
    lang.className = "settings__section";
    lang.innerHTML = `<h3>${t("settings.section.language")}</h3>`;

    const langGroup = document.createElement("div");
    langGroup.className = "settings__lang-group";
    const currentLang = (data.config && data.config.language) || "en";
    const supported = data.supported_languages || ["de", "en"];

    supported.forEach((code) => {
      const id = `settings-lang-${code}`;
      const wrapper = document.createElement("label");
      wrapper.className = "settings__lang-option";
      const radio = document.createElement("input");
      radio.type = "radio";
      radio.name = "settings-language";
      radio.value = code;
      radio.id = id;
      if (code === currentLang) radio.checked = true;
      const text = document.createElement("span");
      text.textContent = t(`settings.language.${code}`);
      wrapper.appendChild(radio);
      wrapper.appendChild(text);
      langGroup.appendChild(wrapper);
    });
    lang.appendChild(langGroup);

    const langHint = document.createElement("p");
    langHint.className = "settings__hint";
    langHint.textContent = t("settings.language.hint");
    lang.appendChild(langHint);

    // "Refresh metadata" — re-fetches every library entry's external
    // metadata so the active language's translations get populated. Paced
    // server-side; we just trigger and report.
    const refreshRow = document.createElement("div");
    refreshRow.className = "settings__refresh-row";
    const refreshBtn = document.createElement("button");
    refreshBtn.type = "button";
    refreshBtn.className = "settings__refresh-btn";
    refreshBtn.textContent = t("settings.metadata.refresh");
    const refreshStatus = document.createElement("span");
    refreshStatus.className = "settings__status";
    refreshBtn.addEventListener("click", async () => {
      refreshBtn.disabled = true;
      refreshStatus.textContent = t("settings.metadata.refreshing");
      refreshStatus.style.color = "";
      try {
        const result = await api.libraryRefreshAll();
        const count = (result && result.queued) || 0;
        refreshStatus.textContent = t("settings.metadata.refresh_queued", { count });
        refreshStatus.style.color = "var(--success)";
      } catch (err) {
        refreshStatus.textContent = t("settings.action.error", {
          message: err.message || "Error",
        });
        refreshStatus.style.color = "var(--danger)";
      } finally {
        refreshBtn.disabled = false;
      }
    });
    refreshRow.appendChild(refreshBtn);
    refreshRow.appendChild(refreshStatus);
    lang.appendChild(refreshRow);

    const refreshHint = document.createElement("p");
    refreshHint.className = "settings__hint";
    refreshHint.textContent = t("settings.metadata.hint");
    lang.appendChild(refreshHint);

    wrap.appendChild(lang);

    // --- Save row ---
    const actions = document.createElement("div");
    actions.className = "settings__actions";
    const saveBtn = document.createElement("button");
    saveBtn.type = "button";
    saveBtn.className = "detail__primary";
    saveBtn.textContent = window.ssI18n.t("settings.action.save");
    const status = document.createElement("span");
    status.className = "settings__status";

    saveBtn.addEventListener("click", async () => {
      saveBtn.disabled = true;
      saveBtn.textContent = window.ssI18n.t("settings.action.saving");
      status.textContent = "";
      const langChoice = (langGroup.querySelector('input[name="settings-language"]:checked') || {}).value;
      const payload = {
        config: {
          preferred_provider: providerSelect.value,
          max_concurrent: parseInt(concInput.value, 10) || 5,
          max_retries: parseInt(retryInput.value, 10) || 3,
          overlay_collapsed_default: overlayCheckbox.checked,
        },
      };
      if (langChoice) payload.config.language = langChoice;
      const tmdb = tmdbInput.value.trim();
      if (tmdb) payload.tmdb_api_key = tmdb;
      try {
        await api.settingsPatch(payload);
        // Apply language change immediately to the popup; full re-render
        // happens on the timer below.
        if (langChoice) window.ssI18n.setLanguage(langChoice);
        status.textContent = window.ssI18n.t("settings.action.saved");
        status.style.color = "var(--success)";
        tmdbInput.value = "";
        // Re-render so the "(gesetzt)" hint reflects reality and any
        // localized labels switch.
        setTimeout(renderSettings, 800);
      } catch (err) {
        status.textContent = window.ssI18n.t("settings.action.error", { message: err.message || "Error" });
        status.style.color = "var(--danger)";
      } finally {
        saveBtn.disabled = false;
        saveBtn.textContent = window.ssI18n.t("settings.action.save");
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
