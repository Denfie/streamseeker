// Shared helpers for the stream content scripts.
//
// Renders a single fixed bottom-right overlay per page with:
//   - Series title + current Season/Episode context
//   - Favorite / Library / Downloaded state
//   - "★ Favorit" toggle button
//   - "⬇ Download" button that opens a modal with the usual scope choices
//     (just this episode / the whole season / everything / whole series).
//
// Per-stream scripts only provide URL parsing + title extraction and call
// window.ssBadges.runSeriesScript({...}).

(function () {
  const iconUrl = (name) => chrome.runtime.getURL(`icons/svg/${name}.svg`);

  const svgCache = new Map();
  async function fetchSvg(name) {
    if (svgCache.has(name)) return svgCache.get(name);
    const promise = fetch(iconUrl(name)).then((r) => r.text());
    svgCache.set(name, promise);
    return promise;
  }
  async function injectSvg(el, name) {
    try { el.innerHTML = await fetchSvg(name); }
    catch { el.textContent = "●"; }
  }

  // ----- Small DOM helpers --------------------------------------------

  function el(tag, props = {}, children = []) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(props)) {
      if (k === "class") node.className = v;
      else if (k === "text") node.textContent = v;
      else if (k === "html") node.innerHTML = v;
      else if (k === "on") for (const [ev, fn] of Object.entries(v)) node.addEventListener(ev, fn);
      else if (k === "style") Object.assign(node.style, v);
      else if (/^on[A-Z]/.test(k) && typeof v === "function") {
        node.addEventListener(k.slice(2).toLowerCase(), v);
      }
      else node.setAttribute(k, v);
    }
    for (const c of children) if (c) node.appendChild(c);
    return node;
  }

  async function makeIconButton({ icon, label, title, cls = "", onClick }) {
    const btn = el("button", {
      class: `ss-btn ${cls}`.trim(),
      title: title || "",
      type: "button",
      on: { click: onClick ? (ev) => { ev.preventDefault(); ev.stopPropagation(); onClick(ev, btn); } : undefined },
    });
    const iconHolder = el("span");
    btn.appendChild(iconHolder);
    if (icon) injectSvg(iconHolder, icon);
    if (label) btn.appendChild(el("span", { text: label }));
    return btn;
  }

  // ----- Toast --------------------------------------------------------

  function toast(message, { error = false } = {}) {
    const node = el("div", {
      class: `ss-toast ${error ? "ss-toast--error" : ""}`.trim(),
      text: message,
    });
    document.body.appendChild(node);
    setTimeout(() => node.remove(), 2600);
  }

  // ----- State helpers ------------------------------------------------

  function aggregateSeasons(state) {
    const seasons = state && state.seasons ? Object.values(state.seasons) : [];
    const agg = { total: 0, downloaded: 0, queued: 0, failed: 0 };
    for (const s of seasons) {
      agg.total += s.total || 0;
      agg.downloaded += s.downloaded || 0;
      agg.queued += s.queued || 0;
      agg.failed += s.failed || 0;
    }
    return agg;
  }

  function downloadStatusClass(agg) {
    if (agg.failed > 0) return "ss-btn--danger";
    if (agg.queued > 0) return "ss-btn--warn";
    if (agg.total > 0 && agg.downloaded >= agg.total) return "ss-btn--success";
    return "";
  }

  // ----- Overlay ------------------------------------------------------

  function removeOverlay() {
    for (const node of document.querySelectorAll(".ss-overlay, .ss-modal-backdrop")) {
      node.remove();
    }
  }

  // Collapse state persists across page loads via localStorage so users who
  // minimise on one page aren't re-ambushed on every navigation.
  const COLLAPSE_STORAGE_KEY = "streamseeker:overlay-collapsed";
  function isCollapsed() {
    try { return localStorage.getItem(COLLAPSE_STORAGE_KEY) === "1"; }
    catch { return false; }
  }
  function setCollapsed(value) {
    try { localStorage.setItem(COLLAPSE_STORAGE_KEY, value ? "1" : "0"); }
    catch { /* private mode etc. — ignore */ }
  }

  async function renderOverlay(options, info, state, title) {
    removeOverlay();
    const agg = aggregateSeasons(state);
    const key = `${options.stream}::${info.slug}`;
    const collapsed = isCollapsed();

    const overlay = el("div", {
      class: `ss-overlay ${collapsed ? "ss-overlay--minimized" : ""}`.trim(),
    });
    if (collapsed) {
      overlay.title = "Klicken zum Öffnen";
      overlay.addEventListener("click", (ev) => {
        if (ev.target.closest(".ss-overlay__toggle")) return;
        setCollapsed(false);
        renderOverlay(options, info, state, title);
      });
    }

    // Title row with collapse/expand toggle + colored status dot
    const dotCls = downloadStatusClass(agg).replace("ss-btn--", "ss-overlay__pill-dot--");
    const dot = el("span", { class: `ss-overlay__pill-dot ${dotCls}`.trim() });
    const titleNode = el("div", { class: "ss-overlay__title", text: title });
    const toggle = el("button", {
      class: "ss-overlay__toggle",
      title: collapsed ? "Öffnen" : "Einklappen",
      type: "button",
      html: collapsed ? "+" : "−",
    });
    toggle.addEventListener("click", (ev) => {
      ev.stopPropagation();
      setCollapsed(!collapsed);
      renderOverlay(options, info, state, title);
    });
    const titleRow = el("div", { class: "ss-overlay__row" }, [dot, titleNode, toggle]);

    // Meta row — subtle tracking-style info: stream, season/episode context,
    // collection progress. Download-specific wording stays out of here.
    const metaRow = el("div", { class: "ss-overlay__meta" });
    metaRow.appendChild(el("span", { html: `<strong>${options.stream}</strong>` }));
    if (info.season) {
      const epPart = info.episode ? ` · E${info.episode}` : "";
      metaRow.appendChild(el("span", { text: `S${info.season}${epPart}` }));
    }
    metaRow.appendChild(el("span", { text: collectionLabel(agg) }));
    if (state.library) metaRow.appendChild(el("span", { text: "📚 in Sammlung" }));
    if (state.favorite) metaRow.appendChild(el("span", { text: "⭐ Favorit" }));

    // Primary action — favorite toggle. The only obvious button.
    const favBtn = await makeIconButton({
      icon: state.favorite ? "star-filled" : "star-outline",
      label: state.favorite ? "Entfernen" : "Merken",
      title: state.favorite
        ? "Von meinen Favoriten entfernen"
        : "Zu meinen Favoriten hinzufügen",
      cls: state.favorite ? "ss-btn--primary ss-btn--active" : "ss-btn--primary",
      onClick: async () => {
        try {
          if (state.favorite) await window.ssApi.favoritesRemove(key);
          else await window.ssApi.favoritesAdd(options.stream, info.slug);
          state.favorite = !state.favorite;
          toast(state.favorite ? "Zu Favoriten hinzugefügt" : "Aus Favoriten entfernt");
          await refresh(options, info);
        } catch (err) {
          toast(String(err), { error: true });
        }
      },
    });

    // Discreet kebab menu — advanced actions (incl. download) live here.
    const kebab = makeKebab([
      {
        label: options.isMovie
          ? "Film zur Sammlung hinzufügen…"
          : "Zur Sammlung hinzufügen…",
        onClick: () => openDownloadModal(options, info, state, title),
      },
    ]);

    const actionsRow = el("div", { class: "ss-overlay__actions" }, [favBtn, kebab]);
    overlay.appendChild(titleRow);
    overlay.appendChild(metaRow);
    overlay.appendChild(actionsRow);

    document.body.appendChild(overlay);

    // Colour host-page season/episode links based on collection state.
    applyLinkColouring(options, state);
  }

  function collectionLabel(agg) {
    if (agg.total > 0 && agg.downloaded >= agg.total) return "Sammlung komplett";
    if (agg.total > 0 && agg.downloaded > 0) return `${agg.downloaded}/${agg.total} in Sammlung`;
    if (agg.downloaded > 0) return `${agg.downloaded} gesammelt`;
    if (agg.queued > 0) return `${agg.queued} geplant`;
    if (agg.failed > 0) return `${agg.failed} Problem${agg.failed === 1 ? "" : "e"}`;
    return "Noch nichts gesammelt";
  }

  function makeKebab(items) {
    const wrap = el("div", { class: "ss-kebab" });
    const btn = el("button", {
      class: "ss-kebab__btn",
      type: "button",
      title: "Weitere Optionen",
      html: "⋮",
    });

    const menu = el("div", { class: "ss-kebab__menu" });
    for (const item of items) {
      const opt = el("button", { type: "button", text: item.label });
      opt.addEventListener("click", (ev) => {
        ev.stopPropagation();
        menu.remove();
        item.onClick();
      });
      menu.appendChild(opt);
    }

    btn.addEventListener("click", (ev) => {
      ev.stopPropagation();
      if (wrap.contains(menu)) {
        menu.remove();
      } else {
        wrap.appendChild(menu);
        // Close on outside click
        setTimeout(() => {
          const closer = (e) => {
            if (!wrap.contains(e.target)) {
              menu.remove();
              document.removeEventListener("click", closer);
            }
          };
          document.addEventListener("click", closer);
        }, 0);
      }
    });

    wrap.appendChild(btn);
    return wrap;
  }

  // ----- In-page link colouring --------------------------------------

  function applyLinkColouring(options, state) {
    // Clean any previous state first
    for (const a of document.querySelectorAll("a[data-ss-state]")) {
      a.removeAttribute("data-ss-state");
    }

    const seasons = (state && state.seasons) || {};

    // Season links — skip the link the user is currently on so the site's
    // own "active" styling wins. Skip anchors that also carry an episode
    // segment (those are episode links inside a season, handled below).
    for (const link of document.querySelectorAll('a[href*="/staffel-"]')) {
      const href = link.getAttribute("href") || "";
      if (href.includes("/episode-")) continue;
      if (isActiveLink(link)) continue;
      const m = href.match(/\/staffel-(\d+)\/?(?:[?#]|$)/);
      if (!m) continue;
      const s = seasons[m[1]];
      const kind = classifySeasonLink(s);
      if (kind) link.setAttribute("data-ss-state", kind);
    }

    // Episode anchors: instead of tinting the anchor (which on aniworld
    // can wrap an entire table row including the title + hoster columns),
    // wrap just the "Folge N" / "Episode N" / "N" text node inside the
    // anchor in our own span and tint that. This way unrelated text
    // (episode title etc.) stays untouched.
    //
    // Clean previous wraps first so refresh doesn't stack spans.
    for (const badge of document.querySelectorAll(".ss-ep-badge")) {
      const parent = badge.parentNode;
      while (badge.firstChild) parent.insertBefore(badge.firstChild, badge);
      parent.removeChild(badge);
      if (parent.normalize) parent.normalize();
    }

    // Prefer the season the user is currently on (URL). If the page shows
    // episodes from multiple seasons (series landing page, search results)
    // we fall back to extracting the season from each anchor's href — so
    // all episodes get coloured consistently, no matter which page layout
    // the stream serves.
    const currentSeason = location.pathname.match(/\/staffel-(\d+)/);
    {
      const currentSeasonKey = currentSeason ? currentSeason[1] : null;
      const LABEL_RE = /^(?:Folge|Episode|Ep\.?|Film|Movie)?\s*\d+$/i;

      for (const link of document.querySelectorAll('a[href*="/episode-"]')) {
        if (isActiveLink(link)) continue;
        const href = link.getAttribute("href") || "";
        const m = href.match(/\/episode-(\d+)/);
        if (!m) continue;
        const seasonMatch = href.match(/\/staffel-(\d+)\//);
        const seasonKey = (seasonMatch && seasonMatch[1]) || currentSeasonKey;
        if (!seasonKey) continue;
        const s = seasons[seasonKey] || { episodes: {} };
        const epStatus = (s.episodes || {})[m[1]];
        if (!epStatus) continue;

        // Pill-style anchor whose whole text is just the episode label
        // (top "Episoden:"-pill bar). Tint the anchor directly so it stays
        // visually consistent with the site's pill styling instead of
        // nesting a second box inside.
        const fullText = (link.textContent || "").trim();
        if (LABEL_RE.test(fullText)) {
          link.setAttribute("data-ss-state", epStatus);
          continue;
        }

        // Otherwise (table row anchor that wraps title/hoster too): find
        // the "Folge N" text node and wrap only that.
        const walker = document.createTreeWalker(link, NodeFilter.SHOW_TEXT);
        let node;
        while ((node = walker.nextNode())) {
          const text = node.textContent.trim();
          if (!text) continue;
          if (LABEL_RE.test(text)) {
            const badge = document.createElement("span");
            badge.className = "ss-ep-badge";
            badge.setAttribute("data-ss-state", epStatus);
            node.parentNode.insertBefore(badge, node);
            badge.appendChild(node);
            break;
          }
        }
      }
    }
  }

  function isActiveLink(link) {
    if (!link) return false;
    // Anchor points at the page the user is already on — let the site's
    // own active styling show through.
    if (link.pathname && link.pathname === location.pathname) return true;
    if (link.matches(".active, .current, [aria-current]")) return true;
    return !!link.closest(".active, .current, [aria-current]");
  }

  function classifySeasonLink(s) {
    if (!s) return null;
    const total = s.total || 0;
    const dl = s.downloaded || 0;
    if (s.failed > 0) return "failed";
    if (total > 0 && dl >= total) return "downloaded";
    if (dl > 0) return "partial";
    if (s.queued > 0) return "queued";
    if (s.skipped > 0) return "skipped";
    return null;
  }

  async function refresh(options, info) {
    try {
      const fresh = await window.ssApi.libraryState(options.stream, info.slug);
      if (options.decorateState) options.decorateState(fresh, info);
      const title = options.findTitle ? options.findTitle() : info.slug;
      await renderOverlay(options, info, fresh, title);
    } catch (err) {
      console.warn("[streamseeker] refresh failed", err);
    }
  }

  // ----- Download modal ----------------------------------------------

  const MODE_SERIES = [
    { key: "all", label: "Komplette Serie", detail: "Alle Staffeln, alle Episoden", needs: [] },
    { key: "season", label: "Komplette Staffel", detail: "Alle Episoden der gewählten Staffel", needs: ["season"] },
    { key: "season_from", label: "Staffel ab Episode", detail: "Gewählte Staffel ab dieser Episode", needs: ["season", "episode"] },
    { key: "from", label: "Ab Staffel/Episode", detail: "Ab hier bis Serien-Ende", needs: ["season", "episode"] },
    { key: "single", label: "Nur diese Episode", detail: "Eine einzelne Episode", needs: ["season", "episode"] },
  ];

  async function openDownloadModal(options, info, _state, title) {
    const api = window.ssApi;
    const backdrop = el("div", { class: "ss-modal-backdrop" });
    const modal = el("div", { class: "ss-modal" });
    backdrop.appendChild(modal);
    backdrop.addEventListener("click", (ev) => {
      if (ev.target === backdrop) backdrop.remove();
    });

    modal.appendChild(el("h2", { text: title }));

    if (options.isMovie) {
      modal.appendChild(el("p", { class: "subtle", text: "Was soll passieren?" }));
      const movieState = { intent: "download" };
      modal.appendChild(buildIntentToggle(movieState, () => {}));
      const submit = el("button", { class: "ss-btn ss-btn--primary", text: "Hinzufügen", type: "button" });
      submit.addEventListener("click", async () => {
        backdrop.remove();
        const payload = {
          stream: options.stream, slug: info.slug,
          type: "filme", scope: "single", season: 0, episode: 1,
        };
        try {
          if (movieState.intent === "mark") {
            await api.libraryMark(payload);
            toast("Als vorhanden markiert");
          } else {
            await api.queueAdd(payload);
            toast("Film – wird gesammelt");
          }
          refresh(options, info);
        } catch (err) { toast(String(err), { error: true }); }
      });
      modal.appendChild(el("div", { class: "ss-modal__footer" }, [
        el("button", { class: "ss-btn", text: "Abbrechen", type: "button",
          onClick: () => backdrop.remove() }),
        submit,
      ]));
      document.body.appendChild(backdrop);
      return;
    }

    // Series modal — load structure first
    modal.appendChild(el("p", { class: "subtle", text: "Struktur wird geladen…" }));
    document.body.appendChild(backdrop);

    let structure;
    try {
      structure = await api.seriesStructure(options.stream, info.slug);
    } catch (err) {
      modal.innerHTML = "";
      modal.appendChild(el("h2", { text: title }));
      modal.appendChild(el("p", { class: "subtle", text: `Konnte Struktur nicht laden: ${err.message}` }));
      modal.appendChild(el("div", { class: "ss-modal__footer" }, [
        el("button", { class: "ss-btn", text: "Schließen", type: "button",
          onClick: () => backdrop.remove() }),
      ]));
      return;
    }

    modal.innerHTML = "";
    modal.appendChild(el("h2", { text: title }));
    modal.appendChild(el("p", { class: "subtle", text: `Umfang wählen — ${options.stream}` }));

    const seasons = structure.seasons || [];
    const languages = structure.languages || {};
    const providers = structure.providers || {};

    // State
    const state = {
      intent: "download",  // or "mark"
      mode: info.season && info.episode ? "single"
        : info.season ? "season" : "all",
      season: info.season || (seasons[0] || 0),
      episode: info.episode || 0,
      language: firstKey(languages, "de") || firstKey(languages),
      provider: firstKey(providers, "voe") || firstKey(providers),
      episodes: [],
    };

    modal.appendChild(buildIntentToggle(state, () => updateFields()));

    const modeList = el("div", { class: "ss-modal__modes" });
    for (const mode of MODE_SERIES) {
      const row = el("label", { class: "ss-modal__mode" }, [
        el("input", { type: "radio", name: "ss-mode", value: mode.key,
          onChange: () => { state.mode = mode.key; updateFields(); } }),
        el("div", {}, [
          el("strong", { text: mode.label }),
          el("span", { class: "subtle", text: mode.detail }),
        ]),
      ]);
      if (state.mode === mode.key) row.querySelector("input").checked = true;
      modeList.appendChild(row);
    }
    modal.appendChild(modeList);

    // Season + episode fields
    const seasonField = buildSelect("Staffel", seasons.map((s) => [s, `Staffel ${s}`]), state.season);
    const episodeField = buildSelect("Episode", [], state.episode);
    const languageField = buildSelect("Sprache",
      Object.entries(languages).map(([k, v]) => [k, v.title || k]), state.language);
    const providerField = buildSelect("Provider",
      Object.entries(providers).map(([k, v]) => [k, v.title || k]), state.provider);

    const fields = el("div", { class: "ss-modal__fields" }, [
      seasonField.wrapper, episodeField.wrapper,
      languageField.wrapper, providerField.wrapper,
    ]);
    modal.appendChild(fields);

    seasonField.select.addEventListener("change", async () => {
      state.season = Number(seasonField.select.value) || 0;
      await loadEpisodes();
    });
    episodeField.select.addEventListener("change", () => {
      state.episode = Number(episodeField.select.value) || 0;
    });
    languageField.select.addEventListener("change", () => {
      state.language = languageField.select.value;
    });
    providerField.select.addEventListener("change", () => {
      state.provider = providerField.select.value;
    });

    async function loadEpisodes() {
      if (!state.season) { episodeField.setOptions([]); return; }
      episodeField.setOptions([["", "lädt…"]]);
      try {
        const res = await api.seriesEpisodes(options.stream, info.slug, state.season);
        state.episodes = res.episodes || [];
        episodeField.setOptions(state.episodes.map((e) => [e, `Episode ${e}`]), state.episode);
        if (!state.episodes.includes(state.episode) && state.episodes.length) {
          state.episode = state.episodes[0];
          episodeField.select.value = String(state.episode);
        }
      } catch (err) {
        episodeField.setOptions([["", "Fehler"]]);
      }
    }

    const submit = el("button", { class: "ss-btn ss-btn--primary", text: "Zur Sammlung hinzufügen", type: "button" });

    function updateFields() {
      const mode = MODE_SERIES.find((m) => m.key === state.mode);
      const needs = new Set(mode.needs);
      seasonField.wrapper.style.display = needs.has("season") ? "" : "none";
      episodeField.wrapper.style.display = needs.has("episode") ? "" : "none";
      const markMode = state.intent === "mark";
      languageField.wrapper.style.display = markMode ? "none" : "";
      providerField.wrapper.style.display = markMode ? "none" : "";
      submit.textContent = markMode ? "Als vorhanden markieren" : "Zur Sammlung hinzufügen";
    }
    updateFields();
    await loadEpisodes();

    submit.addEventListener("click", async () => {
      backdrop.remove();
      const basePayload = {
        stream: options.stream,
        slug: info.slug,
        type: "staffel",
        scope: state.mode,
        season: state.season,
        episode: state.episode,
      };
      try {
        if (state.intent === "mark") {
          await api.libraryMark(basePayload);
          toast("Als vorhanden markiert");
        } else {
          await api.queueAdd({
            ...basePayload,
            language: state.language,
            preferred_provider: state.provider,
          });
          toast("Zur Sammlung hinzugefügt");
        }
        refresh(options, info);
      } catch (err) {
        toast(String(err), { error: true });
      }
    });

    modal.appendChild(el("div", { class: "ss-modal__footer" }, [
      el("button", { class: "ss-btn", text: "Abbrechen", type: "button",
        onClick: () => backdrop.remove() }),
      submit,
    ]));
  }

  function buildIntentToggle(stateLike, onChange) {
    const toggle = el("div", { class: "ss-modal__intent" });
    const options = [
      { key: "download", label: "⬇ Herunterladen", detail: "Download starten" },
      { key: "mark", label: "✓ Bestand markieren", detail: "Schon vorhanden, nicht laden" },
    ];
    for (const opt of options) {
      const btn = el("button", {
        type: "button",
        class: `ss-modal__intent-btn ${stateLike.intent === opt.key ? "is-active" : ""}`.trim(),
      }, [
        el("strong", { text: opt.label }),
        el("span", { class: "subtle", text: opt.detail }),
      ]);
      btn.addEventListener("click", () => {
        stateLike.intent = opt.key;
        toggle.querySelectorAll(".ss-modal__intent-btn").forEach((b) => b.classList.remove("is-active"));
        btn.classList.add("is-active");
        onChange();
      });
      toggle.appendChild(btn);
    }
    return toggle;
  }

  function firstKey(obj, preferred) {
    if (!obj) return undefined;
    const keys = Object.keys(obj);
    if (preferred && keys.includes(preferred)) return preferred;
    // Also match on common language aliases
    if (preferred === "de" && keys.includes("german")) return "german";
    if (preferred === "voe" && keys.includes("voe")) return "voe";
    return keys[0];
  }

  function buildSelect(label, options, initial) {
    const select = el("select", { class: "ss-modal__select" });
    const wrapper = el("label", { class: "ss-modal__field" }, [
      el("span", { class: "subtle", text: label }),
      select,
    ]);
    function setOptions(opts, value) {
      select.innerHTML = "";
      for (const [val, text] of opts) {
        const opt = document.createElement("option");
        opt.value = String(val);
        opt.textContent = text;
        select.appendChild(opt);
      }
      if (value !== undefined && value !== null) select.value = String(value);
    }
    setOptions(options, initial);
    return { wrapper, select, setOptions };
  }

  // ----- Main runner --------------------------------------------------

  async function runSeriesScript(options) {
    const info = options.parseLocation();
    if (!info || !info.slug) return;

    const alive = await window.ssApi.isDaemonAlive();
    if (!alive) {
      toast("StreamSeeker-Daemon nicht erreichbar", { error: true });
      return;
    }

    let state;
    try {
      state = await window.ssApi.libraryState(options.stream, info.slug);
    } catch (err) {
      console.warn("[streamseeker] libraryState failed", err);
      toast("State konnte nicht geladen werden", { error: true });
      return;
    }

    if (options.decorateState) options.decorateState(state, info);

    const title = options.findTitle ? options.findTitle() : info.slug;
    await renderOverlay(options, info, state, title);

    // Live updates — only re-render if something about this series actually changed
    const signatureOf = (s) =>
      JSON.stringify({ fav: s.favorite, lib: s.library, seasons: s.seasons || {} });
    let lastSignature = signatureOf(state);

    window.ssApi.subscribeStatus(async () => {
      try {
        const fresh = await window.ssApi.libraryState(options.stream, info.slug);
        const nextSig = signatureOf(fresh);
        if (nextSig === lastSignature) return;
        lastSignature = nextSig;
        if (options.decorateState) options.decorateState(fresh, info);
        const t = options.findTitle ? options.findTitle() : info.slug;
        await renderOverlay(options, info, fresh, t);
      } catch (_) { /* ignore */ }
    }, () => { /* ignore SSE errors */ });
  }

  window.ssBadges = {
    iconUrl,
    fetchSvg,
    injectSvg,
    aggregateSeasons,
    runSeriesScript,
    toast,
  };
})();
