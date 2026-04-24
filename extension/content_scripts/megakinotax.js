// Content script for megakino.tax — a pure movie site, no seasons/episodes.
// The overlay's download button opens a modal with a single "Ganzen Film
// herunterladen" choice (handled by common.js thanks to `isMovie: true`).

(function () {
  window.ssBadges.runSeriesScript({
    stream: "megakinotax",
    isMovie: true,

    parseLocation() {
      // megakino.tax detail pages: /film/<slug>.html or /film/<slug>/
      const m = location.pathname.match(/\/(?:film|movie)\/([^/.]+)/);
      if (!m) return null;
      return { slug: m[1], season: null, episode: null, isMovie: true };
    },

    findTitle() {
      const h = document.querySelector("h1")
             || document.querySelector(".poster__title");
      return (h && h.textContent.trim()) || "(Film)";
    },
  });
})();
