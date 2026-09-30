(function () {
  var key = "censo-theme";
  var saved = localStorage.getItem(key);
  var theme = saved || "dark";
  document.documentElement.setAttribute("data-theme", theme);

  function label(t) {
    return t === "dark" ? "☀️" : "🌙";
  }

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
  var btn = document.getElementById("btn-mas");
  var sheet = document.getElementById("mas-sheet");
  if (!btn || !sheet) return;
  function openSheet(open) {
    if (open) {
      sheet.hidden = false;
      sheet.classList.add("is-open");
      btn.setAttribute("aria-expanded", "true");
    } else {
      sheet.hidden = true;
      sheet.classList.remove("is-open");
      btn.setAttribute("aria-expanded", "false");
    }
  }
  btn.addEventListener("click", function () {
    openSheet(sheet.hidden);
  });
  var c1 = document.getElementById("mas-cerrar");
  var c2 = document.getElementById("mas-cerrar-bg");
  if (c1) c1.addEventListener("click", function () { openSheet(false); });
  if (c2) c2.addEventListener("click", function () { openSheet(false); });
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

  document.addEventListener("DOMContentLoaded", function () {
    var campana = document.getElementById("btn-campana");
    var n = campana ? parseInt(campana.getAttribute("data-n") || "0", 10) : 0;
    function irAlertas() {
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
