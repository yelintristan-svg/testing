// Shared front-end behaviour: audience toggle, Calendly popups, forms, join bar.
(function () {
  var body = document.body;
  var store = {
    get: function (k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set: function (k, v) { try { localStorage.setItem(k, v); } catch (e) {} },
  };

  // ── Audience toggle (client / candidate) ──────────────────
  // ?for=candidate in a URL (e.g. from outreach emails) wins, then the last choice.
  function setView(view) {
    if (view !== 'client' && view !== 'candidate') return;
    body.setAttribute('data-view', view);
    store.set('audience', view);
    document.querySelectorAll('[data-set-view]').forEach(function (b) {
      b.setAttribute('aria-pressed', String(b.getAttribute('data-set-view') === view));
    });
    document.querySelectorAll('[data-filter]').forEach(function (b) {
      b.setAttribute('aria-pressed', String(b.getAttribute('data-filter') === view));
    });
    filterPosts(view);
  }
  function filterPosts(aud) {
    document.querySelectorAll('.post-card[data-audience]').forEach(function (el) {
      var a = el.getAttribute('data-audience');
      el.style.display = (aud === 'all' || a === 'both' || a === aud) ? '' : 'none';
    });
  }
  if (body.hasAttribute('data-view')) {
    var q = new URLSearchParams(location.search).get('for');
    setView(q || store.get('audience') || body.getAttribute('data-view'));
    document.querySelectorAll('[data-set-view]').forEach(function (b) {
      b.addEventListener('click', function () { setView(b.getAttribute('data-set-view')); });
    });
  }
  document.querySelectorAll('[data-filter]').forEach(function (b) {
    b.addEventListener('click', function () {
      var f = b.getAttribute('data-filter');
      if (f === 'all') {
        document.querySelectorAll('[data-filter]').forEach(function (x) { x.setAttribute('aria-pressed', String(x === b)); });
        filterPosts('all');
      } else setView(f);
    });
  });

  // ── Mobile nav ────────────────────────────────────────────
  var menu = document.querySelector('.menu-btn');
  if (menu) menu.addEventListener('click', function () {
    var nav = document.querySelector('.nav');
    nav.classList.toggle('open');
    menu.setAttribute('aria-expanded', String(nav.classList.contains('open')));
  });

  // ── Calendly popup (falls back to opening the link) ───────
  var calendlyLoaded = false;
  function loadCalendly(cb) {
    if (calendlyLoaded) return cb();
    var css = document.createElement('link');
    css.rel = 'stylesheet'; css.href = 'https://assets.calendly.com/assets/external/widget.css';
    document.head.appendChild(css);
    var s = document.createElement('script');
    s.src = 'https://assets.calendly.com/assets/external/widget.js';
    s.onload = function () { calendlyLoaded = true; cb(); };
    s.onerror = function () { cb(true); };
    document.head.appendChild(s);
  }
  document.addEventListener('click', function (e) {
    var a = e.target.closest('[data-calendly]');
    if (!a) return;
    e.preventDefault();
    var url = a.getAttribute('href');
    var utm = 'utm_source=website&utm_medium=' + encodeURIComponent(body.getAttribute('data-site') || 'site') +
              '&utm_content=' + encodeURIComponent(a.getAttribute('data-calendly') || 'button');
    url += (url.indexOf('?') > -1 ? '&' : '?') + utm;
    loadCalendly(function (failed) {
      if (failed || !window.Calendly) return window.open(url, '_blank', 'noopener');
      window.Calendly.initPopupWidget({ url: url });
    });
  });

  // ── Forms: POST to the configured endpoint, show a thank-you ──
  document.querySelectorAll('form[data-ajax]').forEach(function (form) {
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var btn = form.querySelector('[type=submit]');
      if (btn) { btn.disabled = true; btn.textContent = 'Sending…'; }
      var data = new FormData(form);
      data.append('page', location.pathname);
      data.append('referrer', document.referrer);
      var params = new URLSearchParams(location.search);
      ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'ref'].forEach(function (k) {
        if (params.get(k)) data.append(k, params.get(k));
      });
      fetch(form.action, { method: 'POST', body: data, headers: { Accept: 'application/json' } })
        .catch(function () {})
        .then(function () {
          form.style.display = 'none';
          var ok = form.parentNode.querySelector('.form-ok');
          if (ok) ok.style.display = 'block';
          store.set('joined', '1');
          hideBar();
        });
    });
  });

  // ── Sticky "join" bar: appears after some scrolling, dismissible ──
  var bar = document.querySelector('.join-bar');
  function hideBar() { if (bar) bar.classList.remove('show'); }
  if (bar && !store.get('joined') && store.get('barDismissed') !== new Date().toDateString()) {
    var shown = false;
    window.addEventListener('scroll', function () {
      if (!shown && window.scrollY > 700) { shown = true; bar.classList.add('show'); }
    }, { passive: true });
    bar.querySelector('.x').addEventListener('click', function () {
      hideBar(); store.set('barDismissed', new Date().toDateString());
    });
  }
})();
