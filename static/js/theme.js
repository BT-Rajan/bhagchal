/* theme.js — Cogzi BEINT v1.0 theme management */
'use strict';
(function () {
  const THEMES = ['dark', 'light', 'corp1', 'corp2', 'corp3'];
  const KEY = 'cogzi_theme';

  function apply(theme) {
    if (!THEMES.includes(theme)) theme = 'dark';
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem(KEY, theme);
    document.querySelectorAll('.theme-btn').forEach(b =>
      b.classList.toggle('active', b.dataset.t === theme)
    );
  }

  window.setTheme = apply;

  // Apply immediately on load (before paint)
  apply(localStorage.getItem(KEY) || 'dark');

  document.addEventListener('DOMContentLoaded', () => {
    apply(localStorage.getItem(KEY) || 'dark');
  });
})();
