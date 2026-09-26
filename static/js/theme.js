(function () {
  var key = "censo-theme";
  var saved = localStorage.getItem(key);
  var theme = saved || "dark";
  document.documentElement.setAttribute("data-theme", theme);

  function label(t, compact) {
    if (compact) return t === "dark" ? "☀" : "☾";
    return t === "dark" ? "Modo claro" : "Modo oscuro";
  }

  document.addEventListener("DOMContentLoaded", function () {
    var btn = document.getElementById("theme-toggle");
    if (!btn) return;
    var compact = btn.getAttribute("data-compact") === "1" || btn.closest("header") !== null;
    btn.textContent = label(theme, compact);
    btn.addEventListener("click", function () {
      theme = theme === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", theme);
      localStorage.setItem(key, theme);
      btn.textContent = label(theme, compact);
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

(function () {
  function chime() {
    try {
      var AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return;
      var ctx = window.__censoAudio || (window.__censoAudio = new AC());
      if (ctx.state === "suspended") ctx.resume();
      function beep(t0, freq, dur) {
        var o = ctx.createOscillator();
        var g = ctx.createGain();
        o.type = "sine";
        o.frequency.value = freq;
        g.gain.setValueAtTime(0.0001, t0);
        g.gain.exponentialRampToValueAtTime(0.12, t0 + 0.02);
        g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
        o.connect(g); g.connect(ctx.destination);
        o.start(t0); o.stop(t0 + dur + 0.02);
      }
      var t0 = ctx.currentTime + 0.02;
      beep(t0, 880, 0.16);
      beep(t0 + 0.14, 1175, 0.2);
    } catch (e) {}
  }

  function cerrarMenu() {
    var nav = document.querySelector("header nav");
    var btn = document.getElementById("nav-toggle");
    if (nav) nav.classList.remove("is-open");
    if (btn) {
      btn.setAttribute("aria-expanded", "false");
      btn.textContent = "Menú";
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    var campana = document.getElementById("btn-campana");
    var n = campana ? parseInt(campana.getAttribute("data-n") || "0", 10) : 0;

    function irAlertas(ev) {
      var dest = document.getElementById("caja-alertas");
      if (dest && location.pathname.indexOf("/dashboard") === 0) {
        if (ev) ev.preventDefault();
        cerrarMenu();
        dest.scrollIntoView({ behavior: "smooth", block: "start" });
      } else {
        cerrarMenu();
      }
      if (n > 0) chime();
    }

    if (campana) campana.addEventListener("click", irAlertas);

    if (n > 0 && !sessionStorage.getItem("censo-alerta-sonido")) {
      var unlock = function () {
        sessionStorage.setItem("censo-alerta-sonido", "1");
        chime();
        document.removeEventListener("click", unlock);
        document.removeEventListener("touchstart", unlock);
      };
      document.addEventListener("click", unlock, { once: true });
      document.addEventListener("touchstart", unlock, { once: true });
    }
  });
})();
