/* Sanduq Progress UI: static block renderers + poller. No network, no framework.
   Every string from data is inserted with createTextNode/textContent only. */
(function () {
  'use strict';
  var POLL_MS = 3000;
  var LOAD_TIMEOUT_MS = 10000;
  var LAYOUT = window.__SANDUQ_PROGRESS_LAYOUT__ || {};
  var ALL = ['header', 'orchestrator', 'lanes', 'boards', 'decisions', 'blockers', 'events'];
  var TITLES = { orchestrator: 'Orchestrator', lanes: 'Lanes', boards: 'Boards', decisions: 'Decisions', blockers: 'Blockers', events: 'Events' };
  var cur = -1, inflight = false, data = null, loadError = '', renderError = '';
  var app = document.getElementById('app'), banners = document.getElementById('banners');
  if (LAYOUT.density) document.documentElement.setAttribute('data-density', String(LAYOUT.density));

  /* ---------- DOM helpers ---------- */
  function el(tag, cls, kids) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    add(n, kids);
    return n;
  }
  function add(n, k) {
    if (k == null || k === false) return;
    if (Array.isArray(k)) { k.forEach(function (x) { add(n, x); }); return; }
    n.appendChild(typeof k === 'object' ? k : document.createTextNode(String(k)));
  }
  function attr(n, o) { for (var k in o) n.setAttribute(k, o[k]); return n; }
  function unk() { return el('span', 'unk', 'unknown'); }
  function safeUrl(u) { return typeof u === 'string' && /^https?:\/\//i.test(u) ? u : null; }
  function link(text, url) {
    var u = safeUrl(url);
    if (!u) return el('span', 'wrap', text);
    return attr(el('a', 'wrap', text), { href: u, rel: 'noopener noreferrer', target: '_blank' });
  }
  function pill(status) {
    var s = String(status || 'unknown');
    return el('span', 'pill s-' + s.replace(/[^a-z]/gi, '').slice(0, 12).toLowerCase(), s);
  }
  /* every duration in the projection is whole seconds (docs/contracts.md, "Units") */
  function dur(seconds) {
    if (typeof seconds !== 'number' || !isFinite(seconds) || seconds < 0) return null;
    var s = Math.round(seconds), h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60);
    return h ? h + 'h ' + m + 'm' : m ? m + 'm ' + (s % 60) + 's' : s + 's';
  }
  function ago(iso) {
    var t = Date.parse(iso);
    if (isNaN(t)) return null;
    return (dur(Math.max(0, Date.now() - t) / 1000) || '0s') + ' ago';
  }
  function when(iso) {
    var a = iso && ago(iso);
    return a ? attr(el('time', null, a), { datetime: iso, title: iso }) : unk();
  }
  /* measurement M = {value, source, observed_at, fidelity}; unknown is a value */
  function mv(m, fmt) {
    if (!m || m.value == null) return unk();
    var w = el('span', 'mv', fmt ? fmt(m.value) : String(m.value));
    var f = ['exact', 'partial', 'estimated', 'unknown'].indexOf(m.fidelity) < 0 ? 'unknown' : m.fidelity;
    var tag = el('span', 'fid', f === 'estimated' ? 'est' : f);
    tag.title = 'source: ' + (m.source || 'none') + (m.observed_at ? ', observed ' + m.observed_at : '');
    w.appendChild(tag);
    return w;
  }
  function plain(v) { return v == null || v === '' ? unk() : el('span', 'wrap', v); }

  /* ---------- UI state in location.hash ---------- */
  function readState() {
    var p = new URLSearchParams(location.hash.replace(/^#/, ''));
    var list = function (k) { return (p.get(k) || '').split(',').filter(Boolean); };
    return { f: p.get('f') || '', c: list('c'), o: list('o') };
  }
  function writeState(s) {
    var p = new URLSearchParams();
    if (s.f) p.set('f', s.f);
    if (s.c.length) p.set('c', s.c.join(','));
    if (s.o.length) p.set('o', s.o.join(','));
    var h = p.toString();
    try { history.replaceState(null, '', location.pathname + location.search + (h ? '#' + h : '')); } catch (e) { location.hash = h; }
  }
  function toggle(list, v, on) {
    var i = list.indexOf(v);
    if (on && i < 0) list.push(v);
    if (!on && i >= 0) list.splice(i, 1);
  }

  /* ---------- blocks ---------- */
  function section(name, count, body, st) {
    var open = st.c.indexOf(name) < 0;
    var id = 'b-' + name;
    var btn = attr(el('button', null, [TITLES[name], count != null ? el('span', 'n', count) : null]), { type: 'button', 'aria-expanded': String(open), 'aria-controls': id, 'data-k': 'c-' + name });
    btn.addEventListener('click', function () {
      var s = readState();
      toggle(s.c, name, open);
      writeState(s);
      render();
    });
    var b = el('div', 'body', body);
    b.id = id;
    if (!open) b.hidden = true;
    return el('section', 'blk', [el('h2', null, btn), b]);
  }

  function bHeader(d) {
    var f = d.feature || {}, sm = d.summary || {};
    var total = sm.tasks_total || 0, done = sm.tasks_done || 0, pct = total ? Math.round(done * 100 / total) : 0;
    var top = el('div', 'top');
    var logo = LAYOUT.logo;
    if (typeof logo === 'string' && !/^\s*(javascript|vbscript):/i.test(logo)) top.appendChild(attr(el('img'), { src: logo, alt: '' }));
    var head = el('div', null, [el('h1', 'wrap', LAYOUT.title || f.title || f.id || 'Progress')]);
    var meta = el('div', 'meta');
    if (f.id) meta.appendChild(el('span', 'mono wrap', f.id));
    if (f.issue) meta.appendChild(link('Issue #' + f.issue.number, f.issue.url));
    meta.appendChild(el('span', 'wrap', ['Branch ', f.branch ? el('code', null, f.branch) : unk()]));
    if (f.mode === 'plan') meta.appendChild(el('span', 'wrap', ['Plan ', f.source ? el('code', null, f.source) : unk()]));
    else meta.appendChild(el('span', null, ['Stage ', f.stage && f.stage.value ? pill(f.stage.value) : unk()]));
    head.appendChild(meta);
    top.appendChild(head);
    var bar = attr(el('div', 'bar', el('i')), { role: 'progressbar', 'aria-label': 'Tasks done', 'aria-valuemin': '0', 'aria-valuemax': String(total), 'aria-valuenow': String(done) });
    bar.firstChild.style.width = pct + '%';
    var counts = el('dl', 'counts');
    [['Tasks done', done + ' / ' + total + ' (' + pct + '%)'], ['Lanes active', sm.lanes_active || 0], ['Blocked', sm.blocked || 0], ['Decisions pending', sm.decisions_pending || 0]].forEach(function (c) {
      counts.appendChild(el('div', null, [el('dt', null, c[0]), el('dd', null, c[1])]));
    });
    return el('header', 'hdr', [top, bar, counts]);
  }

  function bOrch(d, st) {
    var o = d.orchestrator || {}, ctx = o.context || {}, cv = ctx.value;
    var gauge = unk();
    if (cv && typeof cv.used_percent === 'number') {
      var p = Math.max(0, Math.min(100, cv.used_percent));
      var g = attr(el('div', 'gauge' + (p >= 80 ? ' hot' : ''), el('i')), { role: 'meter', 'aria-label': 'Context used', 'aria-valuemin': '0', 'aria-valuemax': '100', 'aria-valuenow': String(p) });
      g.firstChild.style.width = p + '%';
      var tok = typeof cv.used_tokens === 'number' && cv.window ? ' (' + cv.used_tokens.toLocaleString() + ' / ' + cv.window.toLocaleString() + ')' : '';
      gauge = el('div', null, [el('span', 'mv', p.toFixed(1) + '%' + tok), mvTag(ctx), g]);
    }
    var kv = el('dl', 'kv', [
      item('Host', plain(o.host)), item('Model', mv(o.model)), item('Effort', mv(o.effort)),
      item('Context used', gauge),
      item('Elapsed (wall time)', mv(o.elapsed, dur)), item('Active (observed work)', mv(o.active, dur)),
      item('Session', plain(o.session_id)), item('Since', when(o.since))
    ]);
    return section('orchestrator', null, [kv, el('p', 'note', 'Elapsed is wall time since start. Active counts only observed work intervals and stays unknown without them.')], st);
  }
  function mvTag(m) {
    var f = ['exact', 'partial', 'estimated'].indexOf(m.fidelity) < 0 ? 'unknown' : m.fidelity;
    var t = el('span', 'fid', f === 'estimated' ? 'est' : f);
    t.title = 'source: ' + (m.source || 'none');
    return t;
  }
  function item(k, v) { return el('div', null, [el('dt', null, k), el('dd', null, v)]); }

  function visibleLanes(d, st) {
    return (d.lanes || []).filter(function (l) { return !st.f || l.id === st.f; });
  }

  function bLanes(d, st) {
    var lanes = d.lanes || [];
    var filter = el('div', 'filter');
    filter.setAttribute('role', 'group');
    filter.setAttribute('aria-label', 'Filter by lane');
    [{ id: '' }].concat(lanes).forEach(function (l) {
      var b = attr(el('button', null, l.id || 'All lanes'), { type: 'button', 'aria-pressed': String(st.f === l.id), 'data-k': 'f-' + l.id });
      b.addEventListener('click', function () {
        var s = readState();
        s.f = s.f === l.id ? '' : l.id;
        writeState(s);
        render();
      });
      filter.appendChild(b);
    });
    var tbl = el('table', 'stack');
    var cols = ['Lane', 'Owner', 'Model', 'Effort', 'Status', 'Elapsed', 'Active', 'Last observed', 'Attempts'];
    tbl.appendChild(el('thead', null, el('tr', null, cols.map(function (c) { return attr(el('th', null, c), { scope: 'col' }); }))));
    var tb = el('tbody');
    visibleLanes(d, st).forEach(function (l) {
      var req = l.requested || {}, obs = l.observed || {};
      var open = st.o.indexOf(l.id) >= 0, at = l.attempts || [];
      var det = el('details');
      det.open = open;
      det.appendChild(el('summary', null, at.length + (at.length === 1 ? ' attempt' : ' attempts')));
      if (at.length) det.appendChild(el('ul', null, at.map(function (a) {
        return el('li', 'wrap', [a.run_id || '?', ' ', pill(a.status), ' ', dur((Date.parse(a.ended_at) - Date.parse(a.started_at)) / 1000) || (a.ended_at ? '' : 'running'),
          a.tokens ? ' ' + tokText(a.tokens) : '', a.fidelity ? el('span', 'fid', a.fidelity) : null]);
      })));
      det.addEventListener('toggle', function () {
        var s = readState();
        if (det.open === (s.o.indexOf(l.id) >= 0)) return;
        toggle(s.o, l.id, det.open);
        writeState(s);
      });
      var rowHead = el('td', null, [el('strong', 'wrap', l.id), el('span', 'sub', l.label || ''), el('span', 'sub', l.origin || '')]);
      rowHead.setAttribute('data-label', 'Lane');
      var cells = [
        [rowHead],
        ['Owner', plain(l.owner)],
        ['Model', [el('span', 'sub', 'requested ' + ([req.harness, req.model].filter(Boolean).join(' ') || 'unknown')), el('span', null, ['observed ', mv(obs.model)])]],
        ['Effort', [el('span', 'sub', 'requested ' + (req.effort || 'unknown')), el('span', null, ['observed ', mv(obs.effort)])]],
        ['Status', pill(l.status)],
        ['Elapsed', mv(l.elapsed, dur)],
        ['Active', mv(l.active, dur)],
        ['Last observed', when(l.last_observed_at)],
        ['Attempts', det]
      ];
      var tr = el('tr');
      cells.forEach(function (c) {
        if (c.length === 1) { tr.appendChild(c[0]); return; }
        tr.appendChild(attr(el('td', null, c[1]), { 'data-label': c[0] }));
      });
      tb.appendChild(tr);
    });
    tbl.appendChild(tb);
    var body = [filter, lanes.length ? tbl : el('p', 'empty', 'No lanes yet.')];
    return section('lanes', lanes.length, body, st);
  }
  function tokText(t) {
    var parts = [];
    for (var k in t) if (typeof t[k] === 'number') parts.push(k + ' ' + t[k].toLocaleString());
    return parts.join(', ');
  }

  function chip(d, id, status, by) {
    var t = (d.tasks || {})[id] || {};
    var c = el('div', 'chip', [el('span', 'id', id), t.title || '']);
    c.style.setProperty('--s', 'var(--' + status + ')');
    if (by && by.length) c.appendChild(el('div', 'by', by.map(function (b) {
      return el('span', 'wrap', 'blocked by ' + (b.type === 'external' ? 'external: ' : '') + b.ref);
    })));
    return c;
  }
  function board(d, name, tasks, id) {
    var t = tasks || {};
    var spec = [['active', 'Active', t.active || []], ['waiting', 'Waiting', t.waiting || []], ['blocked', 'Blocked', t.blocked || []], ['done', 'Done', t.done || []]];
    var cols = el('div', 'cols', spec.map(function (s) {
      var items = s[2].map(function (x) {
        var tid = s[0] === 'blocked' ? x.task : x;
        return el('li', null, chip(d, tid, s[0], s[0] === 'blocked' ? x.by : null));
      });
      return el('div', 'col', [el('h4', null, [s[1], el('span', null, s[2].length)]), el('ul', null, items.length ? items : el('li', 'none', 'None'))]);
    }));
    return el('div', 'board', [el('h3', 'wrap', name), cols]);
  }
  function bBoards(d, st) {
    var parts = visibleLanes(d, st).map(function (l) { return board(d, l.id + (l.label ? ' ' + l.label : ''), l.tasks); });
    var un = d.unassigned_tasks;
    if (!st.f && un && ['active', 'waiting', 'blocked', 'done'].some(function (k) { return (un[k] || []).length; })) parts.push(board(d, 'Unassigned', un));
    return section('boards', null, parts.length ? parts : el('p', 'empty', 'No boards.'), st);
  }

  function selectedList(x) { return Array.isArray(x.selected) ? x.selected : x.selected == null ? [] : [x.selected]; }
  function decItem(x, made) {
    var li = el('li', null, [el('h3', 'wrap', [x.id, ' ', x.question || '']), pill(made ? 'done' : 'waiting')]);
    li.lastChild.textContent = made ? 'made' : 'pending';
    var opts = el('div', 'opts', (x.options || []).map(function (o) { return el('span', 'wrap' + (made && selectedList(x).indexOf(o) >= 0 ? ' sel' : ''), o); }));
    li.appendChild(opts);
    if (made) {
      li.appendChild(el('p', 'note', ['Selected ', el('strong', 'wrap', selectedList(x).length ? selectedList(x).join(', ') : 'unknown'), ' by ', x.decided_by || 'unknown', x.at ? ' ' + (ago(x.at) || '') : '', ' ', x.url ? link('evidence', x.url) : el('span', 'unk', 'no evidence link')]));
    }
    return li;
  }
  function bDecisions(d, st) {
    var dc = d.decisions || {}, p = dc.pending || [], m = dc.made || [];
    var body = [el('p', 'sect', 'Pending'), p.length ? el('ul', 'dec', p.map(function (x) { return decItem(x, false); })) : el('p', 'empty', 'None pending.'),
      el('p', 'sect', 'Made'), m.length ? el('ul', 'dec', m.map(function (x) { return decItem(x, true); })) : el('p', 'empty', 'None made.')];
    return section('decisions', p.length + ' pending', body, st);
  }

  function bBlockers(d, st) {
    var bl = d.blockers || [];
    var body = el('p', 'empty', 'No open blockers.');
    if (bl.length) {
      var tbl = el('table', 'stack', [el('thead', null, el('tr', null, ['Id', 'Target', 'Blocked by', 'Since', 'Source'].map(function (c) { return attr(el('th', null, c), { scope: 'col' }); }))),
        el('tbody', null, bl.map(function (b) {
          var by = b.by || {};
          var cells = [['Id', b.id], ['Target', b.target], ['Blocked by', (by.type || '?') + ': ' + (by.ref == null ? '' : by.ref)], ['Since', when(b.since)], ['Source', b.source || 'unknown']];
          return el('tr', null, cells.map(function (c) { return attr(el('td', null, c[1]), { 'data-label': c[0] }); }));
        }))]);
      body = tbl;
    }
    return section('blockers', bl.length, body, st);
  }

  function bEvents(d, st) {
    var ev = (d.events || []).slice(0, 30);
    var body = ev.length ? el('ol', 'ev', ev.map(function (e) {
      return el('li', null, [el('span', 't', e.at ? new Date(e.at).toLocaleTimeString() : ''), el('span', 'k', e.kind || ''), el('span', null, e.text || '')]);
    })) : el('p', 'empty', 'No events yet.');
    return section('events', ev.length, body, st);
  }

  var RENDER = { header: bHeader, orchestrator: bOrch, lanes: bLanes, boards: bBoards, decisions: bDecisions, blockers: bBlockers, events: bEvents };

  /* ---------- render ---------- */
  function render() {
    if (!data) return;
    var st = readState(), active = document.activeElement, key = active && active.getAttribute && active.getAttribute('data-k');
    try {
      var frag = document.createDocumentFragment();
      var order = Array.isArray(LAYOUT.blocks) ? LAYOUT.blocks : ALL;
      var hidden = Array.isArray(LAYOUT.hidden) ? LAYOUT.hidden : [];
      order.forEach(function (n) {
        if (RENDER[n] && hidden.indexOf(n) < 0) frag.appendChild(RENDER[n](data, st));
      });
      app.textContent = '';
      app.appendChild(frag);
      renderError = '';
      document.title = (LAYOUT.title || (data.feature && data.feature.title) || 'Sanduq Progress') + ' - Progress';
    } catch (e) {
      renderError = 'The report could not be drawn (' + (e && e.message ? e.message : 'error') + '). Showing the last good view if any.';
    }
    if (key) {
      var els = app.querySelectorAll('[data-k]');
      for (var i = 0; i < els.length; i++) if (els[i].getAttribute('data-k') === key) { els[i].focus(); break; }
    }
    updateBanners();
  }

  function updateBanners() {
    var list = [];
    if (loadError) list.push(['banner', 'Update failed', loadError + ' Showing the last good report.']);
    if (renderError) list.push(['banner', 'Render problem', renderError]);
    if (data) {
      var c = data.collection || {}, t = Date.parse(data.generated_at), lim = (data.stale_after_seconds || 600) * 1000;
      if (c.dirty) list.push(['banner', 'Stale', 'Updates are pending; this view is behind the latest activity.']);
      else if (!isNaN(t) && Date.now() - t > lim) list.push(['banner', 'Stale', 'Last generated ' + ago(data.generated_at) + '. Automatic refresh may have stopped.']);
      if (c.automatic === false) list.push(['banner info', 'Automatic collection unavailable', 'Values come from files only; run progress refresh to update them.']);
    }
    banners.textContent = '';
    list.forEach(function (b) { banners.appendChild(el('p', b[0], [el('b', null, b[1] + '. '), b[2]])); });
  }

  /* ---------- poller ---------- */
  function accept(d) {
    return d && typeof d === 'object' && /^sanduq\.progress\.v2$/.test(d.schema || '') && typeof d.rev === 'number';
  }
  function poll() {
    if (inflight) return;
    inflight = true;
    window.__SANDUQ_PROGRESS__ = undefined;
    var s = document.createElement('script');
    var settled = false, guard = setTimeout(function () { done('data.js did not load in time.'); }, LOAD_TIMEOUT_MS);
    var done = function (err) {
      if (settled) return;  // a load that never settles must not stop the poller for good
      settled = true;
      clearTimeout(guard);
      inflight = false;
      if (s.parentNode) s.parentNode.removeChild(s);
      var d = window.__SANDUQ_PROGRESS__;
      window.__SANDUQ_PROGRESS__ = undefined;
      if (err || !accept(d)) {
        loadError = err || (d ? 'The data file uses an unsupported format.' : 'The data file could not be read.');
        updateBanners();
      } else {
        loadError = '';
        if (d.rev > cur) { cur = d.rev; data = d; render(); } else updateBanners();
      }
      setTimeout(poll, POLL_MS);
    };
    s.onload = function () { done(''); };
    s.onerror = function () { done('data.js is missing or unreadable.'); };
    s.src = 'data.js?rev=' + cur + '&t=' + Date.now();
    document.head.appendChild(s);
  }
  window.addEventListener('hashchange', render);
  poll();
})();
