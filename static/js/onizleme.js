/* Önizleme kartları: sitedeki bir fişe ya da tanıtıma giden bağlantının üzerine gelindiğinde
   sayfadan ayrılmadan kısa bir tanım gösterir. Dokunmatik ekranlarda devre dışıdır. */
(function () {
  "use strict";
  var betik = document.currentScript;
  var veriAdresi = betik && betik.dataset.veri;
  if (!veriAdresi || !window.matchMedia || !window.matchMedia("(hover: hover)").matches) return;
  var veri = null, yukleniyor = null, kart = null, zamanlayici = null, etkin = null;

  function yukle() {
    if (veri) return Promise.resolve(veri);
    if (!yukleniyor) {
      yukleniyor = fetch(veriAdresi).then(function (r) { return r.json(); })
        .then(function (j) { veri = j; return j; })
        .catch(function () { veri = {}; return veri; });
    }
    return yukleniyor;
  }
  function anahtar(a) {
    try {
      var u = new URL(a.href, location.href);
      if (u.origin !== location.origin) return null;
      return u.pathname.replace(/index\.html$/, "");
    } catch (_) { return null; }
  }
  function uygunMu(a) {
    if (a.closest("header.site, footer.site, nav, .ag-panel, .ag-tuval, .tur-secici, .yol, .harita, ul.liste, table.kisiler")) return false;
    var k = anahtar(a);
    return k && k !== location.pathname.replace(/index\.html$/, "") ? k : null;
  }
  function kartiKur() {
    kart = document.createElement("div");
    kart.className = "onizleme";
    kart.setAttribute("role", "tooltip");
    kart.hidden = true;
    document.body.appendChild(kart);
  }
  function goster(a, k) {
    yukle().then(function (v) {
      var d = v[k];
      if (!d || etkin !== a) return;
      if (!kart) kartiKur();
      kart.innerHTML = "";
      var t = document.createElement("p"); t.className = "onizleme-tur"; t.textContent = d.t; kart.appendChild(t);
      var h = document.createElement("p"); h.className = "onizleme-ad"; h.textContent = d.ad; kart.appendChild(h);
      if (d.alt) { var al = document.createElement("p"); al.className = "onizleme-alt"; al.textContent = d.alt; kart.appendChild(al); }
      if (d.a) { var p = document.createElement("p"); p.className = "onizleme-metin"; p.textContent = d.a; kart.appendChild(p); }
      kart.hidden = false;
      var r = a.getBoundingClientRect(), kw = kart.offsetWidth, kh = kart.offsetHeight;
      var x = Math.min(Math.max(8, r.left + window.scrollX), window.scrollX + document.documentElement.clientWidth - kw - 8);
      var asagi = r.bottom + kh + 12 < window.innerHeight;
      var y = asagi ? r.bottom + window.scrollY + 8 : r.top + window.scrollY - kh - 8;
      kart.style.left = x + "px"; kart.style.top = y + "px";
    });
  }
  function gizle() { clearTimeout(zamanlayici); etkin = null; if (kart) kart.hidden = true; }
  function basla(e) {
    var a = e.target.closest && e.target.closest("a[href]");
    if (!a || a === etkin) return;
    var k = uygunMu(a);
    if (!k) return;
    clearTimeout(zamanlayici); etkin = a;
    zamanlayici = setTimeout(function () { goster(a, k); }, 280);
    yukle();
  }
  function bitir(e) {
    var a = e.target.closest && e.target.closest("a[href]");
    if (a && a === etkin && !(e.relatedTarget && a.contains(e.relatedTarget))) gizle();
  }
  document.addEventListener("mouseover", basla);
  document.addEventListener("mouseout", bitir);
  document.addEventListener("focusin", basla);
  document.addEventListener("focusout", bitir);
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") gizle(); });
  window.addEventListener("scroll", gizle, { passive: true });
})();
