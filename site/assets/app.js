/* QuantStrategyLab organisation landing — locale/theme controller and mobile menu. */
(function () {
  "use strict";

  var DICT = window.QSL_I18N || {};
  var LOCALES = Object.keys(DICT);
  var STORAGE_LANG = "qsl-lang";
  var STORAGE_THEME = "qsl-theme";
  var root = document.documentElement;

  function readStorage(key) {
    try { return localStorage.getItem(key); } catch (error) { return null; }
  }
  function writeStorage(key, value) {
    try { localStorage.setItem(key, value); } catch (error) { /* storage may be unavailable */ }
  }
  function queryValue(key) {
    try { return new URLSearchParams(window.location.search).get(key); } catch (error) { return null; }
  }
  function supportedLocale(value) {
    return value && LOCALES.indexOf(value) !== -1 ? value : null;
  }
  function preferredTheme() {
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }

  var browserLocale = String(navigator.language || "en").toLowerCase().indexOf("zh") === 0 ? "zh-CN" : "en";
  var lang = supportedLocale(queryValue("lang")) || supportedLocale(readStorage(STORAGE_LANG)) || browserLocale;

  var queryTheme = queryValue("theme");
  var storedTheme = readStorage(STORAGE_THEME);
  var theme = queryTheme === "dark" || queryTheme === "light"
    ? queryTheme
    : (storedTheme === "dark" || storedTheme === "light" ? storedTheme : preferredTheme());

  var langButton = document.querySelector(".js-lang");
  var themeButton = document.querySelector(".js-theme");
  var menuButton = document.querySelector(".js-menu");
  var nav = document.getElementById("primary-nav");
  var description = document.querySelector('meta[name="description"]');

  function text(key) {
    var table = DICT[lang] || {};
    return typeof table[key] === "string" ? table[key] : "";
  }

  function setMenuOpen(open) {
    if (!menuButton || !nav) return;
    nav.setAttribute("data-open", open ? "true" : "false");
    menuButton.setAttribute("aria-expanded", open ? "true" : "false");
    menuButton.setAttribute("aria-label", open ? text("menu_close") : text("menu"));
  }

  function apply() {
    root.lang = lang;
    root.setAttribute("data-theme", theme);
    document.title = text("doc_title") || "QuantStrategyLab";

    document.querySelectorAll("[data-i18n]").forEach(function (element) {
      var value = text(element.getAttribute("data-i18n"));
      if (value) element.textContent = value;
    });
    document.querySelectorAll("[data-i18n-html]").forEach(function (element) {
      var value = text(element.getAttribute("data-i18n-html"));
      if (value) element.innerHTML = value;
    });
    document.querySelectorAll("[data-i18n-aria]").forEach(function (element) {
      var value = text(element.getAttribute("data-i18n-aria"));
      if (value) element.setAttribute("aria-label", value);
    });

    if (description) description.setAttribute("content", text("meta_description"));

    if (langButton) {
      langButton.textContent = lang === "zh-CN" ? "EN" : "中文";
      langButton.lang = lang === "zh-CN" ? "en" : "zh-CN";
      langButton.setAttribute("aria-label", text("lang_switch"));
    }
    if (themeButton) {
      themeButton.setAttribute("aria-pressed", theme === "dark" ? "true" : "false");
      themeButton.setAttribute("aria-label", theme === "dark" ? text("theme_to_light") : text("theme_to_dark"));
    }
    if (menuButton) {
      setMenuOpen(menuButton.getAttribute("aria-expanded") === "true");
    }
  }

  if (langButton) {
    langButton.addEventListener("click", function () {
      lang = lang === "zh-CN" ? "en" : "zh-CN";
      writeStorage(STORAGE_LANG, lang);
      apply();
    });
  }

  if (themeButton) {
    themeButton.addEventListener("click", function () {
      theme = theme === "dark" ? "light" : "dark";
      writeStorage(STORAGE_THEME, theme);
      apply();
    });
  }

  if (menuButton && nav) {
    menuButton.addEventListener("click", function () {
      setMenuOpen(menuButton.getAttribute("aria-expanded") !== "true");
    });
    nav.querySelectorAll("a").forEach(function (link) {
      link.addEventListener("click", function () { setMenuOpen(false); });
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && menuButton.getAttribute("aria-expanded") === "true") {
        setMenuOpen(false);
        menuButton.focus();
      }
    });
  }

  apply();
})();
