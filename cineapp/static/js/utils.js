/* Shared front-end helpers exposed globally on `window`. Loaded from
   base.html so every page can use them without redeclaring. */

/* Escape a string for safe HTML insertion. Tolerates null / undefined
   (returns ""), coerces other types via String(). */
window.escapeHtml = function (s) {
  if (s == null) return '';
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
};
