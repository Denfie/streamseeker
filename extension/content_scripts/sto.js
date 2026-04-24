// Content script for s.to — same backend/layout as aniworld.to but with
// the `/serie/stream/<slug>` URL prefix.

(function () {
  window.ssBadges.runSeriesScript({
    stream: "sto",

    parseLocation() {
      // s.to migrated from `/serie/stream/<slug>` to `/serie/<slug>` in
      // April 2026 — accept both forms for a few versions so older deep
      // links still work.
      const m = location.pathname.match(/^\/serie(?:\/stream)?\/([^/]+)/);
      if (!m) return null;
      const filmMatch = location.pathname.match(/\/filme\/film-(\d+)/);
      return {
        slug: m[1],
        season: parseInt((location.pathname.match(/\/staffel-(\d+)/) || [])[1], 10) || null,
        episode: parseInt((location.pathname.match(/\/episode-(\d+)/) || [])[1], 10) || null,
        isMovie: Boolean(filmMatch),
      };
    },

    findTitle() {
      const h = document.querySelector(".series-title h1")
             || document.querySelector("h1");
      return (h && h.textContent.trim()) || "(Serie)";
    },
  });
})();
