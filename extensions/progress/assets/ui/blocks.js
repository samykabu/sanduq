/* Sanduq Progress UI: static block renderers + poller. No network, no framework.
   Every string from data is inserted with createTextNode/textContent only. */
(function () {
  'use strict';
  var POLL_MS = 3000;
  var LOAD_TIMEOUT_MS = 10000;
  var LAYOUT = window.__SANDUQ_PROGRESS_LAYOUT__ || {};
  var ALL = ['header', 'decisions', 'blockers', 'orchestrator', 'lanes', 'boards', 'events'];  /* attention first */
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
  /* Ids in the data are untrusted text: a run, stage or lane may be called "constructor" or "__proto__". Every lookup
     keyed by such an id goes through a prototype-free object or an own-property read, never a plain {} lookup. */
  function dict() { return Object.create(null); }
  function own(o, k) { return o && typeof o === 'object' && Object.prototype.hasOwnProperty.call(o, k) ? o[k] : undefined; }
  /* a short stable token for an id, safe inside a DOM id (djb2 over the id text) */
  function token(s) {
    var h = 5381, t = String(s);
    for (var i = 0; i < t.length; i++) h = ((h << 5) + h + t.charCodeAt(i)) | 0;
    return (h >>> 0).toString(16);
  }

  /* ---------- UI state in location.hash ---------- */
  function readState() {
    var p = new URLSearchParams(location.hash.replace(/^#/, ''));
    var list = function (k) { return (p.get(k) || '').split(',').filter(Boolean); };
    return { f: p.get('f') || '', k: p.get('k') || '', c: list('c'), o: list('o'), q: p.get('q') || '', s: p.get('s') || '', p: parseInt(p.get('p'), 10) || 1, g: p.get('g') || '' };
  }
  function writeState(s) {
    var p = new URLSearchParams();
    if (s.f) p.set('f', s.f);
    if (s.k) p.set('k', s.k);
    if (s.c.length) p.set('c', s.c.join(','));
    if (s.o.length) p.set('o', s.o.join(','));
    if (s.q) p.set('q', s.q);
    if (s.s) p.set('s', s.s);
    if (s.p > 1) p.set('p', String(s.p));
    if (s.g) p.set('g', s.g);
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
    else meta.appendChild(el('span', null, ['Stage ', f.stage && f.stage.value ? pill(f.stage.value) : unk(),
      f.stage && f.stage.status && f.stage.status !== 'in-progress' ? el('span', 'sub', ' \u00b7 ' + f.stage.status) : null]));
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
    var c = d.collection || {}, missing = o.model && o.model.value == null && c.automatic === false && (!o.host || o.host === 'codex' || o.host === 'unknown');
    return section('orchestrator', null, [kv,
      missing ? el('p', 'note warn', 'No host hook data for this report yet' + (o.host === 'codex' ? ' \u2014 are the Codex worktree hooks active?' : '.')) : null,
      el('p', 'note', 'Elapsed is wall time since start. Active counts only observed work intervals and stays unknown without them.')], st);
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

  function hasWork(l) {
    var t = l.tasks || {};
    return (l.attempts || []).length > 0 || ['active', 'waiting', 'blocked', 'done'].some(function (k) { return (t[k] || []).length; });
  }
  function laneRow(l, st) {
    var req = l.requested || {}, obs = l.observed || {};
    var open = st.o.indexOf(l.id) >= 0, at = l.attempts || [];
    var det = el('details');
    det.open = open;
    det.appendChild(attr(el('summary', null, at.length + (at.length === 1 ? ' attempt' : ' attempts')), { 'data-k': 'attempts-' + l.id }));
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
    return tr;
  }
  function laneTable(list, st) {
    var tbl = el('table', 'stack');
    var cols = ['Lane', 'Owner', 'Model', 'Effort', 'Status', 'Elapsed', 'Active', 'Last observed', 'Attempts'];
    tbl.appendChild(el('thead', null, el('tr', null, cols.map(function (c) { return attr(el('th', null, c), { scope: 'col' }); }))));
    tbl.appendChild(el('tbody', null, list.map(function (l) { return laneRow(l, st); })));
    return tbl;
  }

  function bLanes(d, st) {
    var lanes = d.lanes || [];
    var shown = visibleLanes(d, st);
    var busy = shown.filter(hasWork), quiet = shown.filter(function (l) { return !hasWork(l); });
    var filter = el('div', 'filter');
    filter.setAttribute('role', 'group');
    filter.setAttribute('aria-label', 'Filter by lane');
    [{ id: '' }].concat(lanes.filter(function (l) { return hasWork(l) || l.id === st.f; })).forEach(function (l) {
      var b = attr(el('button', null, l.id || 'All lanes'), { type: 'button', 'aria-pressed': String(st.f === l.id), 'data-k': 'f-' + l.id });
      b.addEventListener('click', function () {
        var s = readState();
        s.f = s.f === l.id ? '' : l.id;
        writeState(s);
        render();
      });
      filter.appendChild(b);
    });
    var body = [filter];
    if (!lanes.length) body.push(el('p', 'empty', 'No lanes yet.'));
    if (busy.length) body.push(laneTable(busy, st));
    if (quiet.length) {
      /* lanes with no tasks and no attempts have no board or run to read: one collapsed line, not table rows */
      var det = el('details', 'quiet', [attr(el('summary', null, quiet.length + (quiet.length === 1 ? ' lane' : ' lanes') + ' with no tasks or attempts'), { 'data-k': 'quiet-lanes' }), laneTable(quiet, st)]);
      det.open = st.o.indexOf('quiet-lanes') >= 0;
      det.addEventListener('toggle', function () {
        var s = readState();
        if (det.open === (s.o.indexOf('quiet-lanes') >= 0)) return;
        toggle(s.o, 'quiet-lanes', det.open);
        writeState(s);
      });
      body.push(det);
    }
    return section('lanes', lanes.length, body, st);
  }
  function tokText(t) {
    var parts = [];
    for (var k in t) if (typeof t[k] === 'number') parts.push(k + ' ' + t[k].toLocaleString());
    return parts.join(', ');
  }

  function chip(d, id, status, by) {
    var t = own(d.tasks, id) || {};
    var c = el('div', 'chip', [el('span', 'id', id), t.title || '']);
    c.style.setProperty('--s', 'var(--' + status + ')');
    if (by && by.length) c.appendChild(el('div', 'by', by.map(function (b) {
      return el('span', 'wrap', 'blocked by ' + (b.type === 'external' ? 'external: ' : '') + b.ref);
    })));
    return c;
  }
  function board(d, name, tasks, key, st) {
    var t = tasks || {};
    var spec = [['active', 'Active', t.active || []], ['waiting', 'Waiting', t.waiting || []], ['blocked', 'Blocked', t.blocked || []], ['done', 'Done', t.done || []]];
    var cols = el('div', 'cols', spec.map(function (s) {
      var items = s[2].map(function (x) {
        var tid = s[0] === 'blocked' ? x.task : x;
        return el('li', null, chip(d, tid, s[0], s[0] === 'blocked' ? x.by : null));
      });
      return el('div', 'col', [el('h4', null, [s[1], el('span', null, s[2].length)]), el('ul', null, items.length ? items : el('li', 'none', 'None'))]);
    }));
    /* a board with only finished work starts closed; a click flips it, and the flip is kept in the hash */
    var doneOnly = !(spec[0][2].length || spec[1][2].length || spec[2][2].length);
    var flipped = st.o.indexOf(key) >= 0;
    var det = el('details', 'board', [attr(el('summary', null, [el('h3', 'wrap', name), el('span', 'sub', doneOnly ? spec[3][2].length + ' done' : '')]), { 'data-k': 'board-' + key }), cols]);
    det.open = doneOnly === flipped;
    det.addEventListener('toggle', function () {
      var s = readState(), nowFlipped = det.open === doneOnly;
      if (nowFlipped === (s.o.indexOf(key) >= 0)) return;
      toggle(s.o, key, nowFlipped);
      writeState(s);
    });
    return det;
  }
  function taskTotal(t) {
    t = t || {};
    return ['active', 'waiting', 'blocked', 'done'].reduce(function (n, k) { return n + (t[k] || []).length; }, 0);
  }
  function bBoards(d, st) {
    /* a lane with no tasks has nothing to put on a board */
    var parts = visibleLanes(d, st).filter(function (l) { return taskTotal(l.tasks) > 0; }).map(function (l) {
      return board(d, l.id + (l.label ? ' ' + l.label : ''), l.tasks, 'bd:' + l.id, st);
    });
    var un = d.unassigned_tasks;
    if (!st.f && taskTotal(un) > 0) parts.push(board(d, 'Unassigned', un, 'bd:unassigned', st));
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
      el('p', 'sect', 'Made'), m.length ? el('ul', 'dec', m.map(function (x) { return decItem(x, true); })) : el('p', 'empty', 'No decisions recorded in Workflow decisions.')];
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
    var all = d.events || [], kinds = [];
    all.forEach(function (e) { if (e.kind && kinds.indexOf(e.kind) < 0) kinds.push(e.kind); });
    var filter = el('div', 'filter');
    filter.setAttribute('role', 'group');
    filter.setAttribute('aria-label', 'Filter events by kind');
    [''].concat(kinds).forEach(function (k) {
      var b = attr(el('button', null, k || 'All events'), { type: 'button', 'aria-pressed': String(st.k === k), 'data-k': 'k-' + k });
      b.addEventListener('click', function () {
        var s = readState();
        s.k = s.k === k ? '' : k;
        writeState(s);
        render();
      });
      filter.appendChild(b);
    });
    var ev = all.filter(function (e) { return !st.k || e.kind === st.k; }).slice(-100);
    var list = ev.length ? el('ol', 'ev', ev.map(function (e) {
      return el('li', null, [el('span', 't', e.at ? new Date(e.at).toLocaleTimeString() : ''), el('span', 'k', e.kind || ''), el('span', null, e.text || '')]);
    })) : el('p', 'empty', 'No events yet.');
    return section('events', ev.length, [kinds.length ? filter : null, list], st);
  }

  var RENDER = { header: bHeader, orchestrator: bOrch, lanes: bLanes, boards: bBoards, decisions: bDecisions, blockers: bBlockers, events: bEvents };

  /* ---------- v3 Timeline layout (schema sanduq.progress.v3) ---------- */
  var MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  var PAGE = 10, TL_LIMIT = 12;
  function isV3(d) { return !!d && d.schema === 'sanduq.progress.v3'; }
  /* the layout rides with each data revision (`ui.layout`), so a page left open follows `progress theme --layout` */
  function layoutOf(d) { return d && d.ui && typeof d.ui.layout === 'string' ? d.ui.layout : LAYOUT.layout; }
  function timelineLayout(d) { return isV3(d) && layoutOf(d) !== 'classic'; }
  function utc(iso) {
    var t = Date.parse(iso);
    if (isNaN(t)) return null;
    var s = new Date(t).toISOString();
    return parseInt(s.slice(8, 10), 10) + ' ' + MON[parseInt(s.slice(5, 7), 10) - 1] + ' ' + s.slice(11, 16);
  }
  function stamp(iso) {
    var u = utc(iso);
    return u ? attr(el('time', null, u + ' UTC'), { datetime: iso }) : unk();
  }
  function num(v) { return typeof v === 'number' && isFinite(v) ? v : null; }
  function cnt(v) { return num(v) == null ? unk() : String(v); }
  function tid(t) { return typeof t === 'string' ? t : t && (t.id || t.task) ? String(t.id || t.task) : '?'; }
  function slug(v) { return String(v == null ? 'unknown' : v).replace(/[^a-z]/gi, '').slice(0, 12).toLowerCase() || 'unknown'; }
  function tri(v) { return v === true ? 'yes' : v === false ? 'no' : 'unknown'; }
  /* a details element whose open state is kept in the hash under key */
  function keep(det, key, st, attrs) {
    det.open = st.o.indexOf(key) >= 0;
    det.addEventListener('toggle', function () {
      var s = readState();
      if (det.open === (s.o.indexOf(key) >= 0)) return;
      toggle(s.o, key, det.open);
      writeState(s);
    });
    return det;
  }
  /* a button that toggles key in the hash and redraws */
  function flip(label, key, dk, st, extra) {
    var on = st.o.indexOf(key) >= 0;
    var b = attr(el('button', 'tgl', label), { type: 'button', 'aria-expanded': String(on), 'data-k': dk });
    b.addEventListener('click', function () {
      var s = readState();
      toggle(s.o, key, s.o.indexOf(key) < 0);
      writeState(s);
      render();
    });
    return b;
  }
  function vsec(id, title, body, cls) {
    var h = el('h2', null, title);
    h.id = id + '-h';
    var s = el('section', 'blk v3 ' + (cls || ''), [h, el('div', 'body', body)]);
    s.id = id;
    s.setAttribute('data-v3', id);
    s.setAttribute('aria-labelledby', id + '-h');
    return s;
  }
  function prov(o, field) {
    var p = (o.provenance || {})[field];
    if (p === 'self-report') return el('span', 'prov self', 'self-reported');
    if (p === 'host-hook') return el('span', 'prov host', 'host hook');
    if (p === 'none') return el('span', 'prov none', 'no source');
    return null;
  }

  /* References between records. A timeline entry, an episode or a history row names a run, a stage, a workstream or a legacy
     lane id. Each one that exists in this report becomes a real button that opens and focuses its target. */
  var REFS = null, focusReq = null;
  function buildRefs(d) {
    var r = { runs: dict(), stages: dict(), ws: dict(), aliases: dict(), unresolved: dict(), byValue: dict() };
    (d.runs || []).forEach(function (x) { if (x && x.run_id != null) r.runs[String(x.run_id)] = true; });
    (d.stages || []).forEach(function (x) { if (x && x.id != null && x.selected !== false && x.status !== 'excluded') r.stages[String(x.id)] = true; });
    (d.workstreams || []).forEach(function (x) { if (x && x.id != null) r.ws[String(x.id)] = true; });
    var h = d.history || {}, al = h.lane_aliases || {};
    Object.keys(al).forEach(function (k) { r.aliases[k] = String(al[k]); if (!(String(al[k]) in r.byValue)) r.byValue[String(al[k])] = k; });
    (Array.isArray(h.unresolved) ? h.unresolved : []).forEach(function (u) { if (u && u.id != null) r.unresolved[String(u.id)] = true; });
    return r;
  }
  function refTarget(ref, noAlias) {
    var r = REFS, t = String(ref);
    if (!r) return null;
    if (t in r.runs) return { kind: 'run', id: t };
    if (t in r.stages) return { kind: 'stage', id: t };
    if (t.indexOf('run:') === 0 && t.slice(4) in r.runs) return { kind: 'run', id: t.slice(4) };
    if (t in r.ws) return { kind: 'ws', id: t };
    if (t.indexOf('workstream:') === 0 && t.slice(11) in r.ws) return { kind: 'ws', id: t.slice(11) };
    if (noAlias) return null;
    if (t in r.aliases) return { kind: 'alias', id: 'a:' + t };
    if (t in r.unresolved) return { kind: 'alias', id: 'u:' + t };
    if (t in r.byValue) return { kind: 'alias', id: 'a:' + r.byValue[t] };
    return null;
  }
  function runPage(runId) {
    var list = sortRuns((data && data.runs) || []), at = -1;
    list.forEach(function (r, i) { if (at < 0 && String(r.run_id) === String(runId)) at = i; });
    return at < 0 ? 1 : Math.floor(at / PAGE) + 1;
  }
  function go(t) {
    var s = readState();
    if (t.kind === 'run') {
      toggle(s.o, 'runs', true);
      toggle(s.o, 'run:' + t.id, true);
      s.q = '';
      s.s = '';
      s.p = runPage(t.id);
      focusReq = { key: 'run-' + t.id };
    } else if (t.kind === 'stage') {
      s.g = t.id;
      focusReq = { key: 'g-' + t.id };
    } else if (t.kind === 'ws') {
      focusReq = { id: 'ws-' + token(t.id) };
    } else {
      toggle(s.o, 'hist', true);
      focusReq = { id: 'hist-' + token(t.id) };
    }
    writeState(s);
    render();
  }
  function refNode(ref, noAlias) {
    var t = refTarget(ref, noAlias);
    if (!t) return el('code', 'wrap', String(ref));
    var b = attr(el('button', 'reflink wrap', String(ref)), { type: 'button', 'data-k': 'ref-' + token(ref), title: 'Go to ' + t.kind });
    b.addEventListener('click', function () { go(t); });
    return b;
  }
  function applyFocus() {
    var f = focusReq;
    focusReq = null;
    if (!f) return;
    var node = null;
    if (f.id) node = document.getElementById(f.id);
    else {
      var els = app.querySelectorAll('[data-k]');
      for (var i = 0; i < els.length; i++) if (els[i].getAttribute('data-k') === f.key) { node = els[i]; break; }
    }
    if (!node) return;
    node.classList.add('hit');
    if (!node.hasAttribute('tabindex') && node.tabIndex < 0) node.tabIndex = -1;
    node.focus();
    if (node.scrollIntoView) node.scrollIntoView({ block: 'center' });
  }

  /* 1. header */
  function vHeader(d) {
    var f = d.feature || {}, sm = d.summary || {}, na = f.next_action, stg = f.stage || {};
    var h = el('h1', 'wrap', LAYOUT.title || f.title || f.id || 'Progress');
    var meta = el('div', 'meta');
    if (f.id) meta.appendChild(el('span', 'mono wrap', f.id));
    if (f.issue) meta.appendChild(link('Issue #' + f.issue.number, f.issue.url));
    meta.appendChild(el('span', 'wrap', ['Branch ', f.branch ? el('code', null, f.branch) : unk()]));
    if (f.mode === 'plan') {
      meta.appendChild(el('span', 'wrap', ['Plan ', f.source ? el('code', null, f.source) : unk()]));
    } else {
      meta.appendChild(el('span', 'stg', ['Stage ', stg.value ? pill(stg.value) : unk(), ' · ', stg.status ? stg.status : unk(), ' · ', stg.validity ? stg.validity : unk()]));
    }
    var next = el('p', 'next', [el('b', null, 'Next action '), na && na.text ? el('span', 'wrap', na.text) : unk()]);
    if (na && na.text) {
      next.appendChild(el('span', 'sub', [' · ', na.kind === 'active-claim' ? 'active claim' : na.kind === 'next-stage' ? 'next stage' : 'kind unknown',
        na.stage ? ' (' + na.stage + ')' : '', ' · evaluated ', when(na.evaluated_at)]));
    }
    var counts = el('dl', 'counts');
    [['Tasks done', num(sm.tasks_done) == null || num(sm.tasks_total) == null ? unk() : sm.tasks_done + ' / ' + sm.tasks_total],
     ['Stages accepted', num(sm.stages_accepted) == null || num(sm.stages_selected) == null ? unk() : sm.stages_accepted + ' / ' + sm.stages_selected],
     ['Runs', num(sm.runs_total) == null ? unk() : sm.runs_total + (num(sm.runs_failed) ? ' (' + sm.runs_failed + ' failed or abandoned)' : '')],
     ['Decisions pending', cnt(sm.decisions_pending)], ['Blockers open', cnt(sm.blockers_open)]].forEach(function (c) {
      counts.appendChild(el('div', null, [el('dt', null, c[0]), el('dd', null, c[1])]));
    });
    var top = el('div', 'top v3top', [el('div', null, [h, meta]), el('p', 'snap', ['Snapshot ', stamp(d.generated_at), ' · ', when(d.generated_at)])]);
    var hd = el('header', 'hdr v3', [top, next, counts]);
    hd.id = 'v3-header';
    hd.setAttribute('data-v3', 'v3-header');
    return hd;
  }

  /* 2. attention strip */
  function vAttention(d) {
    var a = d.attention || [];
    var body = a.length ? el('ul', 'attn', a.map(function (x) {
      var sev = ['high', 'medium', 'info'].indexOf(x.severity) < 0 ? 'info' : x.severity;
      return el('li', 'item sev-' + sev, [el('span', 'k', (x.kind || 'note') + ' · ' + sev), el('span', 'wrap', x.text || ''), x.since ? el('span', 'sub', when(x.since)) : null]);
    })) : el('p', 'empty', 'Nothing needs attention.');
    return vsec('v3-attention', 'Needs attention', body, 'attention');
  }

  /* 3. orchestrator */
  function vOrch(d) {
    var o = d.orchestrator || {}, ctx = o.context || {};
    function field(label, m, fmt, key) {
      return item(label, [m && typeof m === 'object' && 'value' in m ? mv(m, fmt) : unk(), ' ', prov(o, key || label)]);
    }
    var cv = ctx.value && typeof ctx.value === 'object' ? ctx.value : null;
    var ctxNode = cv && typeof cv.used_percent === 'number' ? [el('span', 'mv', cv.used_percent.toFixed(1) + '%'), mvTag(ctx)] : unk();
    var kv = el('dl', 'kv', [
      item('Host', plain(o.host)),
      field('Model', o.model, null, 'model'), field('Effort', o.effort, null, 'effort'),
      item('Context used', [ctxNode, ' ', prov(o, 'context')]),
      field('Host elapsed', o.host_elapsed, dur, 'host_elapsed'), field('Active (observed work)', o.active, dur, 'active'),
      item('Session', plain(o.session_id)), item('Since', o.since ? stamp(o.since) : unk())
    ]);
    return vsec('v3-orchestrator', 'Orchestrator', [kv, o.note ? el('p', 'note', o.note) : null], 'orch');
  }

  /* 4. stages over time (Gantt) */
  /* Only the projection says a stage is open (a live run, a running episode or the active claim). A stage with a start and
     no recorded end is "end unknown": it is drawn to its start and never grown to now. */
  function stageOpen(s) { return s.open === true && !!s.first_start; }
  function endUnknown(s) { return s.open !== true && !!s.first_start && (!s.last_end || s.timing === 'end-unknown'); }
  function isFail(r) { return r.worker_status === 'failed' || r.worker_status === 'abandoned'; }
  function vStages(d, st) {
    var stages = (d.stages || []).filter(function (s) { return s.selected !== false && s.status !== 'excluded'; })
      .sort(function (a, b) { return (num(a.order) == null ? 1e9 : a.order) - (num(b.order) == null ? 1e9 : b.order); });
    var now = Date.now(), lo = Infinity, hi = -Infinity;
    var fails = dict();
    (d.runs || []).forEach(function (r) { if (isFail(r) && r.stage) (fails[r.stage] = fails[r.stage] || []).push(r); });
    function ext(t) { if (!isNaN(t)) { lo = Math.min(lo, t); hi = Math.max(hi, t); } }
    stages.forEach(function (s) {
      ext(Date.parse(s.first_start));
      if (s.last_end) ext(Date.parse(s.last_end));
      if (stageOpen(s)) ext(now);
      (fails[s.id] || []).forEach(function (r) { ext(Date.parse(r.started_at)); });
    });
    var body = [];
    if (!stages.length) {
      body.push(el('p', 'empty', d.feature && d.feature.mode === 'plan' ? 'This plan has no Workflow stages.' : 'No Workflow stages are recorded for this report.'));
      return vsec('v3-stages', 'Stages over time', body, 'stages');
    }
    if (!isFinite(lo)) lo = hi = now;
    var span = Math.max(hi - lo, 60000);
    function pct(t) { return Math.max(0, Math.min(100, (t - lo) / span * 100)); }
    var rows = stages.map(function (s) {
      var a = Date.parse(s.first_start), open = stageOpen(s), unknownEnd = endUnknown(s);
      var b = open ? now : s.last_end ? Date.parse(s.last_end) : a;
      var track = el('div', 'gtrack');
      if (!isNaN(a) && !isNaN(b)) {
        var bar = el('i', 'gbar st-' + slug(s.status) + (open ? ' open' : '') + (unknownEnd ? ' endunk' : '') + (fails[s.id] ? ' hasfail' : ''));
        bar.style.left = pct(a) + '%';
        bar.style.width = Math.max(unknownEnd ? 1.6 : 0.8, pct(b) - pct(a)) + '%';
        if (unknownEnd) bar.title = s.last_end ? 'a later run or episode has no recorded end' : 'end not recorded';
        track.appendChild(bar);
      } else {
        track.appendChild(el('span', 'gnone', s.status === 'pending' ? 'not started' : 'timing unknown'));
      }
      (fails[s.id] || []).forEach(function (r) {
        var t = Date.parse(r.started_at);
        if (isNaN(t)) return;
        var m = el('b', 'fm', '×');
        m.style.left = pct(t) + '%';
        m.title = r.run_id + ' ' + r.worker_status;
        track.appendChild(m);
      });
      var sel = st.g === s.id;
      var nruns = num(s.run_count), nfail = num(s.failed_runs);
      var label = el('span', 'glabel', [el('b', 'wrap', s.label || s.id), el('span', 'sub', (nruns == null ? 'runs unknown' : nruns + (nruns === 1 ? ' run' : ' runs')) + (nfail ? ' · ' + nfail + ' failed' : '') + (open ? ' · open' : unknownEnd ? ' · end unknown' : ''))]);
      var btn = attr(el('button', 'grow' + (sel ? ' sel' : ''), [label, track]), {
        type: 'button', 'aria-expanded': String(sel), 'aria-controls': 'v3-ep', 'data-k': 'g-' + s.id,
        'aria-label': (s.label || s.id) + ', ' + (s.status || 'unknown') + (open ? ', still open' : unknownEnd ? ', end unknown' : '') + ', ' + (nruns == null ? 'runs unknown' : nruns + ' runs') + (nfail ? ', ' + nfail + ' failed' : '') + '. Show episodes'
      });
      btn.addEventListener('click', function () {
        var x = readState();
        x.g = x.g === s.id ? '' : s.id;
        writeState(x);
        render();
      });
      return btn;
    });
    var axis = el('div', 'gaxis');
    for (var i = 0; i < 5; i++) axis.appendChild(el('span', null, utc(new Date(lo + span * i / 4).toISOString())));
    var inner = el('div', 'ginner', [el('div', 'grows', rows), el('div', 'gaxisrow', [el('span', 'sub', 'UTC'), axis])]);
    var scroll = el('div', 'gscroll', inner);
    scroll.tabIndex = 0;
    scroll.setAttribute('role', 'group');
    scroll.setAttribute('aria-label', 'Stage timeline, scrolls sideways');
    body.push(el('p', 'note legend', 'Bar runs from the first start to the last end. A hatched bar is still open and is drawn to now. A short bar with a broken edge has a start but no recorded end. A cross marks a failed or abandoned run.'));
    body.push(scroll);
    var det = el('div', 'epdetail');
    det.id = 'v3-ep';
    var cur = stages.filter(function (s) { return s.id === st.g; })[0];
    if (cur) det.appendChild(episodes(cur, d));
    else det.hidden = true;
    body.push(det);
    return vsec('v3-stages', 'Stages over time', body, 'stages');
  }
  function episodes(s, d) {
    var byId = dict();
    (d.runs || []).forEach(function (r) { byId[r.run_id] = r; });
    var eps = s.episodes || [], unknown = s.unknown_runs || [];
    var out = el('div', null, [el('h3', 'wrap', (s.label || s.id) + ': episodes'),
      el('p', 'note', [pill(s.status), ' validity ', s.validity || 'unknown', s.accepted_at ? [' · accepted ', stamp(s.accepted_at)] : null, ' · run time ', mv(s.run_time, dur), ' (summed, may overlap)'])]);
    if (eps.length) {
      out.appendChild(el('ol', 'eps', eps.map(function (e) {
        return el('li', null, [el('b', null, 'Episode ' + (e.n == null ? '?' : e.n)), ' ', pill(e.outcome || 'unknown'), ' ',
          el('span', 'sub', [stamp(e.started_at), ' to ', e.ended_at ? stamp(e.ended_at) : e.outcome === 'running' ? el('b', null, 'open') : el('b', null, 'end unknown'),
            ' · ', (e.runs || []).length + ' runs', ' · ', e.source || 'source unknown', e.fidelity ? el('span', 'fid', e.fidelity) : null,
            e.claim_id ? [' · claim ', el('code', null, e.claim_id)] : null]),
          e.reason ? el('div', 'wrap sub', e.reason) : null]);
      })));
    } else if (!unknown.length) {
      out.appendChild(el('p', 'empty', 'No episodes recorded for this stage.'));
    }
    if (unknown.length) {
      out.appendChild(el('div', 'epunknown', [el('h4', null, 'Episode unknown (' + unknown.length + ')'),
        el('p', 'note', 'These runs have no recorded claim, so they are not placed in an episode.'),
        el('ul', null, unknown.map(function (id) { var r = byId[id]; return el('li', 'wrap', [refNode(id), r ? [' ', pill(r.worker_status), ' ', r.summary || ''] : ' (not in the run list)']); }))]));
    }
    return out;
  }

  /* 5a. what happened */
  function vTimeline(d, st) {
    var all = (d.timeline || []).map(function (e, i) { return { e: e, i: i }; })
      .sort(function (a, b) { return (Date.parse(a.e.at) || 0) - (Date.parse(b.e.at) || 0) || a.i - b.i; }).map(function (x) { return x.e; });
    var showAll = st.o.indexOf('tl-all') >= 0, bounded = all.length > TL_LIMIT;
    var list = bounded && !showAll ? all.slice(-TL_LIMIT) : all;
    var body = [];
    if (!all.length) body.push(el('p', 'empty', 'No curated events yet.'));
    else {
      body.push(el('ol', 'tl', list.map(function (e) {
        var kind = ['stage', 'decision', 'failure', 'recovery', 'revalidation', 'note', 'blocker'].indexOf(e.kind) < 0 ? 'note' : e.kind;
        var det = keep(el('details', null, [attr(el('summary', null, [el('time', 'mono note', utc(e.at) || 'unknown time'), el('span', 'kd', kind), el('span', 'wrap', e.text || '')]), { 'data-k': 'tl-' + e.id }),
          el('p', 'note', ['At ', stamp(e.at), e.fidelity ? el('span', 'fid', e.fidelity) : null, (e.refs || []).length ? [' · refs: ', (e.refs || []).map(function (r) { return [refNode(r), ' ']; })] : ' · no linked records'])]), 'tl:' + e.id, st);
        return el('li', 'tl-row k-' + kind, det);
      })));
      if (bounded) {
        body.push(el('p', 'note', showAll ? 'Showing all ' + all.length + ' events.' : 'Showing the latest ' + TL_LIMIT + ' of ' + all.length + ' events.'));
        body.push(flip(showAll ? 'Show latest only' : 'Show all (' + all.length + ')', 'tl-all', 'tl-all', st));
      }
    }
    return vsec('v3-timeline', 'What happened', body, 'timeline');
  }

  /* 5b. workstreams */
  var BUCKETS = ['active', 'blocked', 'waiting', 'done'];
  function vWorkstreams(d, st) {
    var ws = d.workstreams || [], body = [];
    if (!ws.length) body.push(el('p', 'empty', 'No workstreams are recorded.'));
    ws.forEach(function (w) {
      var t = w.tasks || {}, total = BUCKETS.reduce(function (n, k) { return n + (t[k] || []).length; }, 0), done = (t.done || []).length;
      var track = attr(el('div', 'track'), { role: 'img', 'aria-label': done + ' of ' + total + ' tasks done' });
      BUCKETS.forEach(function (k) {
        if (!(t[k] || []).length || !total) return;
        var seg = el('i', 'seg b-' + k);
        seg.style.width = (t[k].length * 100 / total) + '%';
        track.appendChild(seg);
      });
      var chips = [];
      ['active', 'blocked', 'waiting'].forEach(function (k) {
        (t[k] || []).forEach(function (x) { var c = el('span', 'tchip b-' + k, tid(x)); c.title = k; chips.push(c); });
      });
      var owners = w.owners || [];
      var row = el('div', 'wsrow', [
        el('div', 'wshead', [el('b', 'wrap', w.label || w.id), el('span', 'sub', w.origin || 'origin unknown'), el('span', 'cnt', total ? done + ' / ' + total + ' done' : 'no tasks')]),
        track,
        chips.length ? el('div', 'chips', chips) : null,
        done ? keep(el('details', 'wsdone', [attr(el('summary', null, done + ' done'), { 'data-k': 'wsd-' + w.id }), el('div', 'chips', (t.done || []).map(function (x) { return el('span', 'tchip b-done', tid(x)); }))]), 'wsd:' + w.id, st) : null,
        owners.length ? el('ul', 'owners', owners.map(function (o) { return el('li', 'wrap sub', [el('b', null, o.agent || 'unknown'), ' ', stamp(o.from), ' to ', o.to ? stamp(o.to) : 'now']); })) : el('p', 'sub', ['Owner ', unk()]),
        (w.conflicts || []).length ? el('p', 'note warn', 'Conflicts: ' + w.conflicts.map(function (c) { return typeof c === 'string' ? c : JSON.stringify(c); }).join('; ')) : null
      ]);
      row.id = 'ws-' + token(w.id);
      row.tabIndex = -1;
      body.push(row);
    });
    return vsec('v3-workstreams', 'Workstreams during Execute', body, 'workstreams');
  }

  /* 5c. decisions */
  /* Option indexes an answer picks. The projection already carries the answer as option text and, when known, its explicit
     `index`. The UI uses that index, else exact option text. It never decodes a letter: "M" is the option "M". */
  function chosen(x) {
    var ans = x.answer, opts = x.options || [], out = [];
    if (!ans || ans.value == null) return out;
    function add(i) { if (typeof i === 'number' && Math.floor(i) === i && i >= 0 && i < opts.length && out.indexOf(i) < 0) out.push(i); }
    if (ans.index != null) { (Array.isArray(ans.index) ? ans.index : [ans.index]).forEach(add); return out; }
    (Array.isArray(ans.value) ? ans.value : [ans.value]).forEach(function (v) { add(opts.indexOf(String(v))); });
    return out;
  }
  function v3Decision(x) {
    var ans = x.answer, val = ans && ans.value != null ? (Array.isArray(ans.value) ? ans.value.join(', ') : String(ans.value)) : null;
    var by = x.decided_by ? x.decided_by : 'editor not recorded';
    var li = el('li', null, [el('h3', 'wrap', [el('span', 'mono', x.source_id || x.key || '?'), ' ', x.question || el('span', 'unk', 'question not recorded')]), pill(x.state || 'unknown')]);
    var picked = chosen(x);
    if ((x.options || []).length) li.appendChild(el('div', 'opts', x.options.map(function (o, i) { return el('span', 'wrap' + (picked.indexOf(i) >= 0 ? ' sel' : ''), o); })));
    if (ans) li.appendChild(el('p', 'note', ['Answer ', el('strong', 'wrap', val == null ? 'unknown' : val), ' · ', by, ' · answered ', x.answered_at ? stamp(x.answered_at) : el('span', 'unk', 'time not recorded')]));
    if (x.applied) {
      var ae = Array.isArray(x.applied.evidence) ? x.applied.evidence : x.applied.evidence ? [x.applied.evidence] : [];
      li.appendChild(el('p', 'note', ['Applied ', stamp(x.applied.at), ae.length ? ' · ' + ae.map(String).join('; ') : null]));
    }
    var ev = Array.isArray(x.evidence) ? x.evidence : [], links = Array.isArray(x.evidence_links) ? x.evidence_links : [];
    if (ev.length) {
      li.appendChild(el('ul', 'evid', ev.map(function (t) {
        var l = links.filter(function (k) { return k && k.text === t; })[0];
        return el('li', 'wrap sub', l ? link(String(t), l.url) : String(t));
      })));
    }
    li.appendChild(el('p', 'note', ['Source ', x.source || 'unknown', x.stage ? ' · stage ' + x.stage : null, ' · ', x.url ? link('evidence', x.url) : el('span', 'unk', 'no evidence link')]));
    return li;
  }
  function vDecisions(d) {
    var dc = d.decisions || {}, p = dc.pending || [], m = dc.made || [], src = dc.sources || [];
    var ok = src.filter(function (s) { return s.state === 'available'; }).map(function (s) { return s.name; });
    var bad = src.filter(function (s) { return s.state !== 'available'; }).map(function (s) { return s.name + ' (' + (s.state || 'unknown') + ')'; });
    var body = [el('p', 'sect', 'Pending'), p.length ? el('ul', 'dec', p.map(v3Decision)) : el('p', 'empty', 'None pending.'),
      el('p', 'sect', 'Made'), m.length ? el('ul', 'dec', m.map(v3Decision)) : el('p', 'empty', ok.length ? 'None recorded.' : 'None recorded; no decision source was readable.')];
    body.push(el('p', 'note srcline', ['Sources checked: ', ok.length ? ok.join(', ') : 'none', '. Unavailable: ', bad.length ? bad.join(', ') : 'none', '.']));
    return vsec('v3-decisions', 'Decisions', body, 'decisions');
  }

  /* 6. all runs */
  function runHay(r) {
    return [r.run_id, r.identity, r.stage, r.harness, r.requested_model, r.actual_model && r.actual_model.value, r.worker_status, r.workstream, (r.tasks || []).join(' '), r.summary].join(' ').toLowerCase();
  }
  /* failures first, then newest first, then the order in the data */
  function sortRuns(list) {
    return list.map(function (r, i) { return { r: r, i: i }; }).sort(function (a, b) {
      return (isFail(b.r) ? 1 : 0) - (isFail(a.r) ? 1 : 0) || (Date.parse(b.r.started_at) || 0) - (Date.parse(a.r.started_at) || 0) || a.i - b.i;
    }).map(function (x) { return x.r; });
  }
  function vRuns(d, st) {
    var runs = d.runs || [], dispatch = d.dispatch || [];
    var statuses = [];
    runs.forEach(function (r) { if (r.worker_status && statuses.indexOf(r.worker_status) < 0) statuses.push(r.worker_status); });
    statuses.sort();
    var q = attr(el('input'), { type: 'search', 'aria-label': 'Search runs', placeholder: 'Search runs', 'data-k': 'q', value: st.q });
    q.value = st.q;
    var sel = attr(el('select'), { 'aria-label': 'Filter by status', 'data-k': 'rs' });
    [''].concat(statuses).forEach(function (s) { var o = el('option', null, s || 'All statuses'); o.value = s; sel.appendChild(o); });
    sel.value = st.s;
    var out = el('div', 'runsbody');
    function draw() {
      var s = readState(), key = document.activeElement && document.activeElement.getAttribute && document.activeElement.getAttribute('data-k');
      var needle = s.q.toLowerCase();
      var list = runs.filter(function (r) { return (!s.s || r.worker_status === s.s) && (!needle || runHay(r).indexOf(needle) >= 0); });
      list = sortRuns(list);
      var pages = Math.max(1, Math.ceil(list.length / PAGE)), pg = Math.min(Math.max(1, s.p), pages);
      var slice = list.slice((pg - 1) * PAGE, pg * PAGE);
      out.textContent = '';
      var status = attr(el('p', 'note runcount', list.length ? 'Showing ' + ((pg - 1) * PAGE + 1) + ' to ' + ((pg - 1) * PAGE + slice.length) + ' of ' + list.length + ' runs' + (list.length !== runs.length ? ' (filtered from ' + runs.length + ')' : '') + '. Failures first.' : 'No runs match.'), { role: 'status' });
      out.appendChild(status);
      if (slice.length) {
        var cols = ['Run', 'Stage', 'Tasks', 'Model', 'Effort', 'Started', 'Duration', 'Status', 'Accepted'];
        var tbl = el('table', 'stack runs');
        tbl.appendChild(el('thead', null, el('tr', null, cols.map(function (c) { return attr(el('th', null, c), { scope: 'col' }); }))));
        var tb = el('tbody');
        slice.forEach(function (r) {
          var open = s.o.indexOf('run:' + r.run_id) >= 0;
          var b = attr(el('button', 'tgl mono', r.run_id), { type: 'button', 'aria-expanded': String(open), 'data-k': 'run-' + r.run_id });
          b.addEventListener('click', function () {
            var x = readState();
            toggle(x.o, 'run:' + r.run_id, x.o.indexOf('run:' + r.run_id) < 0);
            writeState(x);
            draw();
          });
          var cells = [['Run', b], ['Stage', plain(r.stage)], ['Tasks', (r.tasks || []).length ? (r.tasks || []).join(', ') : unk()],
            ['Model', [el('span', 'sub', 'requested ' + (r.requested_model || 'unknown')), el('span', null, ['actual ', mv(r.actual_model)])]],
            ['Effort', mv(r.effort)], ['Started', stamp(r.started_at)], ['Duration', mv(r.duration, dur)], ['Status', pill(r.worker_status)],
            ['Accepted', 'evidence ' + tri(r.evidence_accepted) + ', candidate ' + tri(r.candidate_accepted)]];
          tb.appendChild(el('tr', isFail(r) ? 'failrow' : null, cells.map(function (c) { return attr(el('td', null, c[1]), { 'data-label': c[0] }); })));
          if (open) {
            var dt = el('dl', 'kv', [item('Identity', plain(r.identity)), item('Harness', plain(r.harness)), item('Episode', r.episode_id ? el('code', null, r.episode_id) : el('span', 'unk', 'episode unknown')),
              item('Workstream', plain(r.workstream)), item('Retry of', r.retry_of ? el('code', null, r.retry_of) : el('span', 'unk', 'none recorded')),
              item('Ended', r.ended_at ? stamp(r.ended_at) : el('span', 'unk', 'unknown')), item('Summary', plain(r.summary))]);
            var dtr = el('tr', 'rdetail', attr(el('td', null, dt), { colspan: String(cols.length) }));
            tb.appendChild(dtr);
          }
        });
        tbl.appendChild(tb);
        out.appendChild(tbl);
      }
      var pager = el('div', 'pager');
      function pbtn(label, to, dk) {
        var dis = to < 1 || to > pages;
        var bt = attr(el('button', 'tgl', label), { type: 'button', 'data-k': dk, 'aria-disabled': String(dis) });
        bt.addEventListener('click', function () {
          if (dis) return;
          var x = readState();
          x.p = to;
          writeState(x);
          draw();
        });
        return bt;
      }
      pager.appendChild(pbtn('Previous', pg - 1, 'pg-prev'));
      pager.appendChild(el('span', null, 'Page ' + pg + ' of ' + pages));
      pager.appendChild(pbtn('Next', pg + 1, 'pg-next'));
      out.appendChild(pager);
      if (key) {
        var cand = out.querySelectorAll('[data-k]');
        for (var i = 0; i < cand.length; i++) if (cand[i].getAttribute('data-k') === key) { cand[i].focus(); break; }
      }
    }
    q.addEventListener('input', function () {
      var x = readState();
      x.q = q.value;
      x.p = 1;
      writeState(x);
      draw();
    });
    sel.addEventListener('change', function () {
      var x = readState();
      x.s = sel.value;
      x.p = 1;
      writeState(x);
      draw();
    });
    draw();
    var disp = el('div', 'dispatch', [el('h3', null, 'Dispatch intents (' + dispatch.length + ')'), el('p', 'note', 'Intents that have no run yet. They are not counted as runs.'),
      dispatch.length ? el('ul', null, dispatch.map(function (x) { return el('li', 'wrap', [el('code', null, x.intent_id || '?'), ' ', x.identity || 'identity unknown', ' · ', pill(x.state || 'unknown'), ' ', stamp(x.created_at)]); })) : el('p', 'empty', 'None.')]);
    var det = keep(el('details', 'runsec', [attr(el('summary', null, 'All runs (' + runs.length + ')'), { 'data-k': 'runs' }),
      el('div', 'toolbar', [q, sel]), out, disp]), 'runs', st);
    var sec = el('section', 'blk v3 runs', el('div', 'body', det));
    sec.id = 'v3-runs';
    sec.setAttribute('data-v3', 'v3-runs');
    return sec;
  }

  /* 7. history: legacy lane ids stay navigable */
  function vHistory(d, st) {
    var h = d.history || {}, al = h.lane_aliases || {}, un = Array.isArray(h.unresolved) ? h.unresolved : [];
    var keys = Object.keys(al).sort();
    var rows = keys.map(function (k) {
      var li = el('li', null, [el('code', null, k), ' maps to ', refTarget(al[k], true) ? refNode(al[k], true) : el('span', 'wrap', String(al[k]))]);
      li.id = 'hist-' + token('a:' + k);
      li.tabIndex = -1;
      return li;
    });
    var open = un.map(function (u) {
      var owners = Array.isArray(u.owners) ? u.owners : [];
      var li = el('li', null, [el('code', null, String(u.id)), ' ', el('span', 'wrap', u.label || ''), ' ',
        el('span', 'sub', u.reason || 'no link recorded'),
        owners.length ? el('div', 'sub wrap', ['Owners: ', owners.map(function (o, i) { return [i ? '; ' : '', String(o.agent || 'unknown'), ' ', stamp(o.from), ' to ', o.to ? stamp(o.to) : 'now']; })]) : null]);
      li.id = 'hist-' + token('u:' + u.id);
      li.tabIndex = -1;
      return li;
    });
    var body = [
      el('p', 'note', 'Older reports named lanes (L1, W7, ...). Each one that an explicit record links to a run, identity or workstream is listed with that link. The rest are kept here as unresolved, with their owner history.'),
      el('p', 'sect', 'Aliases (' + keys.length + ')'), rows.length ? el('ul', 'hist', rows) : el('p', 'empty', 'No aliases.'),
      el('p', 'sect', 'Unresolved (' + un.length + ')'), open.length ? el('ul', 'hist', open) : el('p', 'empty', 'None unresolved.')];
    var det = keep(el('details', 'histsec', [attr(el('summary', null, 'History (' + keys.length + ' aliases, ' + un.length + ' unresolved)'), { 'data-k': 'hist' }), el('div', null, body)]), 'hist', st);
    var sec = el('section', 'blk v3 history', el('div', 'body', det));
    sec.id = 'v3-history';
    sec.setAttribute('data-v3', 'v3-history');
    return sec;
  }

  function renderV3(d, st) {
    REFS = buildRefs(d);
    var frag = document.createDocumentFragment();
    frag.appendChild(vHeader(d));
    frag.appendChild(vAttention(d));
    frag.appendChild(vOrch(d));
    frag.appendChild(vStages(d, st));
    frag.appendChild(el('div', 'v3cols', [vTimeline(d, st), el('div', 'v3right', [vWorkstreams(d, st), vDecisions(d)])]));
    frag.appendChild(vRuns(d, st));
    frag.appendChild(vHistory(d, st));
    return frag;
  }

  /* ---------- render ---------- */
  function render() {
    if (!data) return;
    var st = readState(), active = document.activeElement, key = active && active.getAttribute && active.getAttribute('data-k');
    var caret = key === 'q' && active.selectionStart != null ? [active.selectionStart, active.selectionEnd] : null;
    var oldScroll = app.querySelector('.gscroll'), sx = oldScroll ? oldScroll.scrollLeft : 0, sy = window.pageYOffset;
    try {
      var frag = document.createDocumentFragment();
      if (timelineLayout(data)) {
        frag = renderV3(data, st);
      } else {
        var order = Array.isArray(LAYOUT.blocks) ? LAYOUT.blocks : ALL;
        var hidden = Array.isArray(LAYOUT.hidden) ? LAYOUT.hidden : [];
        if (isV3(data)) frag.appendChild(el('p', 'note warn', 'The classic layout needs a v2 report. Showing what this v3 report has in common with it.'));
        order.forEach(function (n) {
          if (RENDER[n] && hidden.indexOf(n) < 0) frag.appendChild(RENDER[n](data, st));
        });
      }
      app.textContent = '';
      app.appendChild(frag);
      var ns = app.querySelector('.gscroll');
      if (ns) ns.scrollLeft = sx;
      if (sy) window.scrollTo(0, sy);
      renderError = '';
      document.title = (LAYOUT.title || (data.feature && data.feature.title) || 'Sanduq Progress') + ' - Progress';
    } catch (e) {
      renderError = 'The report could not be drawn (' + (e && e.message ? e.message : 'error') + '). Showing the last good view if any.';
    }
    if (key) {
      var els = app.querySelectorAll('[data-k]');
      for (var i = 0; i < els.length; i++) if (els[i].getAttribute('data-k') === key) {
        els[i].focus({ preventScroll: true });
        if (caret && els[i].setSelectionRange) try { els[i].setSelectionRange(caret[0], caret[1]); } catch (e) { /* not a text input */ }
        break;
      }
    }
    applyFocus();
    updateBanners();
  }

  function updateBanners() {
    var list = [];
    if (loadError) list.push(['banner', 'Update failed', loadError + ' Showing the last good report.']);
    if (renderError) list.push(['banner', 'Render problem', renderError]);
    if (data) {
      var c = data.collection || {}, t = Date.parse(data.generated_at), lim = (data.stale_after_seconds || 600) * 1000;
      if (Array.isArray(c.inconsistent_sources) && c.inconsistent_sources.length) list.push(['banner', 'Snapshot may mix generations', 'A source file changed while the report was being built (' + c.inconsistent_sources.join(', ') + '). A new refresh is pending.']);
      if (c.dirty) list.push(['banner', 'Stale', 'Updates are pending; this view is behind the latest activity.']);
      else if (!isNaN(t) && Date.now() - t > lim) list.push(['banner', 'Stale', 'Last generated ' + ago(data.generated_at) + '. Automatic refresh may have stopped.']);
      if (c.automatic === false) list.push(['banner info', 'Automatic collection unavailable', 'Values come from files only; run progress refresh to update them.']);
    }
    banners.textContent = '';
    list.forEach(function (b) { banners.appendChild(el('p', b[0], [el('b', null, b[1] + '. '), b[2]])); });
  }

  /* ---------- poller ---------- */
  function accept(d) {
    if (!d || typeof d !== 'object') return false;
    if (/^sanduq\.progress\.v3$/.test(d.schema || '')) {
      if (typeof d.rev !== 'number') d.rev = Date.parse(d.generated_at) || 0;  /* a v3 report without a counter orders by snapshot time */
      return true;
    }
    return /^sanduq\.progress\.v2$/.test(d.schema || '') && typeof d.rev === 'number';
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
