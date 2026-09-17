(function () {
  var key = "censo-theme";
  var saved = localStorage.getItem(key);
  var theme = saved || "dark";
  document.documentElement.setAttribute("data-theme", theme);

  function label(t) { return t === "dark" ? "Modo claro" : "Modo oscuro"; }

  document.addEventListener("DOMContentLoaded", function () {
    var btn = document.getElementById("theme-toggle");
    if (!btn) return;
    btn.textContent = label(theme);
    btn.addEventListener("click", function () {
      theme = theme === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", theme);
      localStorage.setItem(key, theme);
      btn.textContent = label(theme);
    });
  });
})();

document.addEventListener("DOMContentLoaded", function () {
  var btn = document.getElementById("nav-toggle");
  var nav = document.querySelector("header nav");
  if (!btn || !nav) return;
  btn.addEventListener("click", function () {
    var open = nav.classList.toggle("is-open");
    btn.setAttribute("aria-expanded", open ? "true" : "false");
    btn.textContent = open ? "Cerrar" : "Menú";
  });
});
