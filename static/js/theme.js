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
