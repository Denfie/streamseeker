// Tiny i18n runtime for the StreamSeeker popup + content scripts.
//
// `window.ssI18n.de` and `window.ssI18n.en` are populated by
// `extension/locales/{de,en}.js` (loaded as plain <script>s before
// this file). `setLanguage(code)` switches the active bundle;
// `t("key", {placeholder: value})` looks up + format-substitutes.

(function () {
  const SUPPORTED = ["de", "en"];
  const DEFAULT = "en";
  let active = DEFAULT;

  function bundle(code) {
    return (window.ssI18n && window.ssI18n[code]) || {};
  }

  function setLanguage(code) {
    active = SUPPORTED.includes(code) ? code : DEFAULT;
    return active;
  }

  function getLanguage() { return active; }

  function t(key, vars) {
    const raw = bundle(active)[key] || bundle(DEFAULT)[key] || key;
    if (!vars) return raw;
    return raw.replace(/\{(\w+)\}/g, (m, name) =>
      vars[name] !== undefined ? String(vars[name]) : m
    );
  }

  window.ssI18n = window.ssI18n || {};
  window.ssI18n.setLanguage = setLanguage;
  window.ssI18n.getLanguage = getLanguage;
  window.ssI18n.t = t;
  window.ssI18n.SUPPORTED = SUPPORTED;
})();
