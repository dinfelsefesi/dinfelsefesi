/* İlişki ağı: fişler ve makaleler arasındaki bağlantıları kuvvet yönelimli bir ağ olarak çizer.
   Veri sayfadaki <script id="ag-veri" type="application/json"> öğesinden okunur. */
(function () {
  "use strict";
  var kap = document.getElementById("ag");
  var veriEl = document.getElementById("ag-veri");
  if (!kap || !veriEl || !window.d3) return;
  var V = JSON.parse(veriEl.textContent);
  var TURLER = V.turler; // [{kod, ad, renk}]
  var RENK = {};
  var SIRA = {};  // panelde komşular türe göre (başlık, terim, kişi, eser) sonra ada göre dizilir
  TURLER.forEach(function (t, i) { RENK[t.kod] = t.renk; SIRA[t.kod] = i; });
  var azHareket = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  var dugumler = V.dugumler.map(function (d) { return Object.assign({}, d); });
  // b[3] === "d": dolaylı bağ (kişi -> başlık/terim, makaleleri üzerinden). Yalnızca eserler gizliyken görünür.
  var baglar = V.baglar.map(function (b) { return { source: b[0], target: b[1], w: b[2] || 1, dolayli: b[3] === "d" }; });
  var suz = function (d) { return d.tur; };
  var byId = {};
  dugumler.forEach(function (d) { byId[d.id] = d; d.dogrudan = new Set(); d.dolayliK = new Set(); });
  baglar.forEach(function (b) {
    var k = b.dolayli ? "dolayliK" : "dogrudan";
    byId[b.source][k].add(b.target); byId[b.target][k].add(b.source);
  });
  dugumler.forEach(function (d) {
    d.komsu = d.dogrudan;
    d.derece = d.dogrudan.size;
    d.r = d.kucuk ? 3 + 1.2 * Math.sqrt(d.derece) : 5 + 3.2 * Math.sqrt(d.derece);
  });

  var svg = d3.select(kap).append("svg").attr("role", "img")
    .attr("aria-label", "Fişler ve makaleler arasındaki bağlantıları gösteren ağ");
  var g = svg.append("g");
  var cizgi = g.append("g").attr("class", "ag-baglar").selectAll("line").data(baglar).join("line")
    .style("stroke-width", function (b) { return b.w > 1 ? (1.1 + 0.9 * Math.log2(b.w)) + "px" : null; });
  var dugum = g.append("g").attr("class", "ag-dugumler").selectAll("g").data(dugumler).join("g")
    .attr("class", function (d) { return "ag-dugum tur-" + d.tur; })
    .attr("tabindex", 0).attr("role", "button")
    .attr("aria-label", function (d) { return d.ad + " (" + d.turAd + ")"; });
  dugum.append("circle").attr("r", function (d) { return d.r; })
    .attr("fill", function (d) { return RENK[d.tur]; });
  var kisalt = function (t, n) { return t.length > n ? t.slice(0, n - 1).replace(/\s+\S*$/, "") + "…" : t; };
  var etiket = dugum.append("text").text(function (d) { return kisalt(d.ad, 34); })
    .attr("dy", function (d) { return d.r + 13; })
    .style("font-size", function (d) { return Math.min(16, 11.5 + d.derece * 0.45) + "px"; });

  var genislik = kap.clientWidth, yukseklik = kap.clientHeight;
  var sim = d3.forceSimulation(dugumler)
    .force("bag", d3.forceLink(baglar).id(function (d) { return d.id; })
      .distance(function (l) { return (l.source.kucuk || l.target.kucuk ? 30 : 55) + 16 * Math.sqrt(Math.min(30, Math.max(l.source.derece || 1, l.target.derece || 1))); })
      .strength(function (l) { return l.dolayli ? 0.08 : 0.45; }))
    .force("itme", d3.forceManyBody().strength(function (d) { return d.kucuk ? -40 : -260 - 34 * Math.min(d.derece, 30); }))
    .force("carpisma", d3.forceCollide(function (d) { return d.r + (d.kucuk ? 3 : 18); }))
    .force("x", d3.forceX(genislik / 2).strength(0.05))
    .force("y", d3.forceY(yukseklik / 2).strength(0.08))
    .stop();

  function ciz() {
    cizgi.attr("x1", function (b) { return b.source.x; }).attr("y1", function (b) { return b.source.y; })
      .attr("x2", function (b) { return b.target.x; }).attr("y2", function (b) { return b.target.y; });
    dugum.attr("transform", function (d) { return "translate(" + d.x + "," + d.y + ")"; });
  }
  // Yerleşim önceden hesaplanır, sayfa açıldığında ağ durgun görünür; sürükleyince yeniden canlanır.
  for (var i = 0; i < 400; i++) sim.tick();
  ciz();
  sim.on("tick", ciz);

  var olcek = 1;
  var yakinlik = d3.zoom().scaleExtent([0.25, 6]).on("zoom", function (e) {
    g.attr("transform", e.transform); olcek = e.transform.k; etiketleriAyarla();
  });
  svg.call(yakinlik).on("dblclick.zoom", null);

  dugum.call(d3.drag()
    .on("start", function (e, d) { if (!e.active && !azHareket) sim.alphaTarget(0.2).restart(); d.fx = d.x; d.fy = d.y; })
    .on("drag", function (e, d) { d.fx = e.x; d.fy = e.y; if (azHareket) { d.x = e.x; d.y = e.y; ciz(); } })
    .on("end", function (e, d) { if (!e.active) sim.alphaTarget(0); d.fx = null; d.fy = null; }));

  // Vurgulama
  var secili = null, uzerinde = null, gizliTurler = new Set(), aramaEslesen = null;
  // Dolaylı bağlar (kişi -> başlık/terim) eserler gizliyken hep, eserler açıkken yalnızca o kişi seçili ya da üzerindeyken görünür.
  // Böylece her kişiye tıklandığında hem eserleri hem çalıştığı konular birlikte görünür.
  function bagGizli(b) {
    if (gizliTurler.has(suz(b.source)) || gizliTurler.has(suz(b.target))) return true;
    if (!b.dolayli || gizliTurler.has("eser")) return false;
    var d = uzerinde || secili;
    return !(d && (b.source.id === d.id || b.target.id === d.id));
  }
  function komsulariKur() {
    var eserGizli = gizliTurler.has("eser");
    dugumler.forEach(function (d) {
      var s = new Set();
      d.dogrudan.forEach(function (x) { if (!gizliTurler.has(suz(byId[x]))) s.add(x); });
      if (eserGizli || d.tur === "kisi") d.dolayliK.forEach(function (x) { if (!gizliTurler.has(suz(byId[x]))) s.add(x); });
      d.komsu = s;
    });
  }
  function odakKumesi() {
    var d = uzerinde || secili;
    if (!d) return null;
    var s = new Set(d.komsu); s.add(d.id); return s;
  }
  function boya() {
    var k = odakKumesi();
    dugum.classed("soluk", function (d) { return (k && !k.has(d.id)) || (aramaEslesen && !aramaEslesen.has(d.id)); })
      .classed("secili", function (d) { return secili && d.id === secili.id; })
      .classed("gizli", function (d) { return gizliTurler.has(suz(d)); });
    cizgi.classed("vurgu", function (b) { var d = uzerinde || secili; return d && (b.source.id === d.id || b.target.id === d.id); })
      .classed("soluk", function (b) { var d = uzerinde || secili; return (d && b.source.id !== d.id && b.target.id !== d.id) || !!aramaEslesen; })
      .classed("gizli", bagGizli);
    etiketleriAyarla();
  }
  function etiketleriAyarla() {
    var k = odakKumesi();
    etiket.classed("goster", function (d) {
      if (k) return k.has(d.id);
      if (aramaEslesen) return aramaEslesen.has(d.id);
      if (d.tur === "eser" || d.tur === "makale" || d.suz === "kisi-tr") return olcek > 1.8;
      return d.derece >= 3 || d.tur === "baslik" || olcek > 1.3;
    });
  }
  dugum.on("mouseenter", function (e, d) { uzerinde = d; boya(); })
    .on("mouseleave", function () { uzerinde = null; boya(); })
    .on("click", function (e, d) { e.stopPropagation(); sec(d); })
    .on("keydown", function (e, d) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); sec(d); } });
  svg.on("click", function () { sec(null); });

  // Bilgi paneli
  var panel = document.getElementById("ag-panel");
  function sec(d, ortala) {
    secili = d; boya();
    // Seçili düğüm adrese yazılır; bir fişe gidip geri dönüldüğünde aynı düğüm yeniden seçili gelir.
    try { history.replaceState(null, "", location.pathname + (d ? "?odak=" + encodeURIComponent(d.id) : "")); } catch (_) {}
    if (!d) { panel.hidden = true; document.body.classList.remove("ag-panel-acik"); return; }
    var komsular = Array.from(d.komsu).map(function (id) { return byId[id]; })
      .sort(function (a, b) { return (SIRA[a.tur] - SIRA[b.tur]) || a.ad.localeCompare(b.ad, "tr"); });
    panel.innerHTML = "";
    // telefonda kart kapalı (küçük) açılır; tutamağa dokununca büyür
    var dar = kap.clientWidth <= 760;
    panel.classList.toggle("kapali", dar);
    var tut = document.createElement("button"); tut.type = "button"; tut.className = "ag-tutamak";
    tut.setAttribute("aria-label", "Kartı büyüt ya da küçült");
    tut.addEventListener("click", function () { panel.classList.toggle("kapali"); });
    panel.appendChild(tut);
    var ust = document.createElement("p"); ust.className = "ust-etiket"; ust.textContent = d.turAd; panel.appendChild(ust);
    var h = document.createElement("h2"); h.textContent = d.ad; panel.appendChild(h);
    if (dar) h.addEventListener("click", function () { panel.classList.toggle("kapali"); });
    if (d.aciklama) { var p = document.createElement("p"); p.className = "ag-aciklama"; p.textContent = d.aciklama; panel.appendChild(p); }
    var a = document.createElement("a"); a.href = d.url; a.className = "ag-ac";
    if (d.dis) { a.target = "_blank"; a.rel = "noopener"; }
    a.textContent = d.tanitim ? "Tanıtımı okuyun →" : d.suz === "kisi-tr" ? "Akademisyen sayfasını açın →" : d.dis ? "Makaleyi açın ↗" : "Fişi açın →";
    panel.appendChild(a);
    if (d.makaleler && d.makaleler.length) {
      var mh = document.createElement("h3"); mh.textContent = "DergiPark'taki makaleleri (" + d.makaleler.length + ")"; panel.appendChild(mh);
      var ol = document.createElement("ol"); ol.className = "ag-makaleler";
      d.makaleler.slice(0, 8).forEach(function (m) {
        var li = document.createElement("li"), ma = document.createElement("a");
        ma.href = m.u; ma.target = "_blank"; ma.rel = "noopener"; ma.textContent = m.b;
        var y = document.createElement("span"); y.textContent = " · " + m.y;
        li.appendChild(ma); li.appendChild(y); ol.appendChild(li);
      });
      panel.appendChild(ol);
      if (d.tumu) { var ta = document.createElement("a"); ta.href = d.tumu; ta.className = "ag-ac"; ta.textContent = "Bütün makaleleri listede →"; panel.appendChild(ta); }
    }
    if (komsular.length) {
      var kh = document.createElement("h3"); kh.textContent = komsular.length + " bağlantı"; panel.appendChild(kh);
      var ul = document.createElement("ul");
      komsular.forEach(function (n) {
        var li = document.createElement("li");
        var b = document.createElement("button"); b.type = "button";
        b.innerHTML = '<span class="nokta" style="--renk:' + RENK[n.tur] + '"></span>';
        b.appendChild(document.createTextNode(n.ad));
        b.addEventListener("click", function () { sec(n, true); });
        li.appendChild(b); ul.appendChild(li);
      });
      panel.appendChild(ul);
    }
    var kapat = document.createElement("button"); kapat.type = "button"; kapat.className = "ag-kapat";
    kapat.setAttribute("aria-label", "Paneli kapat"); kapat.textContent = "×";
    kapat.addEventListener("click", function () { sec(null); });
    panel.appendChild(kapat);
    panel.hidden = false;
    document.body.classList.add("ag-panel-acik");
    if (ortala || dar) ortalaDugum(d);
  }
  function ortalaDugum(d, k) {
    k = k || Math.max(olcek, 1.3);
    var pay = (!panel.hidden && kap.clientWidth > 760) ? panel.offsetWidth / 2 : 0;
    // telefonda panel ekranın altını kapladığı için düğüm tuvalin üst kısmına getirilir
    var dar = kap.clientWidth <= 760 && !panel.hidden;
    var t = d3.zoomIdentity.translate(kap.clientWidth / 2 - pay, kap.clientHeight * (dar ? 0.42 : 0.5)).scale(k).translate(-d.x, -d.y);
    svg.transition().duration(azHareket ? 0 : 600).call(yakinlik.transform, t);
  }

  // Tür süzgeçleri
  document.querySelectorAll(".ag-tur button").forEach(function (b) {
    b.addEventListener("click", function () {
      var kod = b.dataset.tur, acik = b.getAttribute("aria-pressed") === "true";
      b.setAttribute("aria-pressed", acik ? "false" : "true");
      if (acik) gizliTurler.add(kod); else gizliTurler.delete(kod);
      komsulariKur();
      if (secili && !gizliTurler.has(suz(secili))) { sec(secili); return; }
      if (secili && gizliTurler.has(suz(secili))) sec(null); else boya();
    });
  });

  // Arama
  var ara = document.getElementById("ag-ara");
  var kucuk = function (s) { return s.replace(/I/g, "ı").replace(/İ/g, "i").toLowerCase(); };
  if (ara) {
    ara.addEventListener("input", function () {
      var q = kucuk(ara.value.trim());
      aramaEslesen = q ? new Set(dugumler.filter(function (d) { return kucuk(d.ad).indexOf(q) > -1; }).map(function (d) { return d.id; })) : null;
      boya();
    });
    ara.addEventListener("keydown", function (e) {
      if (e.key !== "Enter" || !aramaEslesen || !aramaEslesen.size) return;
      e.preventDefault();
      var d = byId[Array.from(aramaEslesen)[0]]; sec(d, true);
    });
  }

  // Görünümü sıfırla
  var sifirla = document.getElementById("ag-sifirla");
  function sigdir() {
    var x0 = d3.min(dugumler, function (d) { return d.x - d.r; }), x1 = d3.max(dugumler, function (d) { return d.x + d.r; });
    var y0 = d3.min(dugumler, function (d) { return d.y - d.r; }), y1 = d3.max(dugumler, function (d) { return d.y + d.r + 18; });
    var w = kap.clientWidth, h = kap.clientHeight;
    var k = Math.min(1.6, 0.8 / Math.max((x1 - x0) / w, (y1 - y0) / h));
    var t = d3.zoomIdentity.translate(w / 2, h / 2).scale(k).translate(-(x0 + x1) / 2, -(y0 + y1) / 2);
    svg.transition().duration(azHareket ? 0 : 500).call(yakinlik.transform, t);
  }
  if (sifirla) sifirla.addEventListener("click", function () {
    if (ara) { ara.value = ""; aramaEslesen = null; }
    sec(null); sigdir();
  });

  // Adres çubuğunda ?odak=tur/kimlik varsa o düğümle başla
  var odak = new URLSearchParams(location.search).get("odak");
  var ilkKez = true;
  function hazir() {
    if (!ilkKez) return; ilkKez = false;
    if (odak && byId[odak]) sec(byId[odak], true); else sigdir();
  }
  hazir();

  new ResizeObserver(function () {
    genislik = kap.clientWidth; yukseklik = kap.clientHeight;
    sim.force("x").x(genislik / 2); sim.force("y").y(yukseklik / 2);
  }).observe(kap);
  komsulariKur();
  boya();
})();
