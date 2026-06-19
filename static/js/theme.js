/* theme.js — Cogzi BEINT v1.0 */
'use strict';
(function () {
  const THEMES = ['dark','light','corp1','corp2','corp3'];
  const KEY = 'cogzi_theme';

  function apply(theme) {
    if (!THEMES.includes(theme)) theme = 'dark';
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem(KEY, theme);
    document.querySelectorAll('.theme-select').forEach(sel => { sel.value = theme; });
  }

  window.setTheme = function(theme) { apply(theme); };

  // Apply before paint to avoid flash
  apply(localStorage.getItem(KEY) || 'dark');

  document.addEventListener('DOMContentLoaded', () => {
    apply(localStorage.getItem(KEY) || 'dark');
  });
})();
