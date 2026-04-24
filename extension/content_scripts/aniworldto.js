// Content script for aniworld.to.
//
// URL shapes this script handles:
//   /anime/stream/<slug>
//   /anime/stream/<slug>/staffel-N
//   /anime/stream/<slug>/staffel-N/episode-M
//   /anime/stream/<slug>/filme/film-N

(function () {
  window.ssBadges.runSeriesScript({
    stream: "aniworldto",

    parseLocation() {
      const m = location.pathname.match(/^\/anime\/stream\/([^/]+)/);
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
