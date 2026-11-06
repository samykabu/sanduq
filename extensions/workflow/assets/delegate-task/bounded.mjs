// bounded.mjs - helpers shared by check-runner.mjs and `delegate.mjs collect --summary`.
//
// Everything here exists so a projection stays small, valid JSON and free of
// obvious secrets, however large the log or result behind it is.

import fs from 'node:fs';

// Names whose value is a credential. Matched as a whole token inside an
// assignment-looking pair (`NAME=value`, `NAME: value`, `"NAME": "value"`).
const SECRET_NAME = /token|secret|passw(?:or)?d|api[_-]?key|apikey|private[_-]?key|credential|authorization|auth/i;
// A bounded name and a word boundary keep a megabyte word without assignments
// linear to scan. An unbounded greedy name prefix would retry at every letter.
const PAIR_RE = /(?<![A-Za-z0-9_.-])(["']?[A-Za-z0-9_.-]{1,128}["']?\s*[:=]\s*)("[^"\r\n]*"|'[^'\r\n]*'|[^\s,;&]+)/gi;
const BEARER_RE = /\b(Bearer|Basic)\s+[A-Za-z0-9._~+/=-]+/g;
const TOKEN_SHAPES = [
  /\bgh[pousr]_[A-Za-z0-9]{20,}\b/g,
  /\bgithub_pat_[A-Za-z0-9_]{20,}\b/g,
  /\bsk-[A-Za-z0-9_-]{20,}\b/g,
  /\bAKIA[0-9A-Z]{16}\b/g,
  /\bxox[abprs]-[A-Za-z0-9-]{10,}\b/g,
  /\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b/g,
];
export const REDACTED = '[redacted]';

// `extraValues` are exact secret strings the caller knows (plan env values).
function knownSecretSpans(text, extraValues) {
  const variants = new Set();
  for (const v of extraValues) {
    if (typeof v === 'string' && v.length > 0) {
      for (const part of [v, JSON.stringify(v).slice(1, -1), ...v.split(/\r?\n/)]) if (part) variants.add(part);
    }
  }
  // Look ahead at every original start position, including inside earlier
  // matches. Merge coverage before replacing so crossing secrets cannot leak.
  if (variants.size) variants.add(REDACTED);
  const alternatives = [...variants].sort((a, b) => b.length - a.length)
    .map(v => v.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
  const intervals = [];
  if (!alternatives.length) return intervals;
  for (const match of text.matchAll(new RegExp(`(?=(${alternatives.join('|')}))`, 'g'))) {
    const start = match.index, end = start + match[1].length;
    const previous = intervals[intervals.length - 1];
    if (previous && start <= previous[1]) previous[1] = Math.max(previous[1], end);
    else intervals.push([start, end]);
  }
  return intervals;
}

function redactKnown(text, extraValues) {
  const s = String(text), parts = [];
  let offset = 0;
  for (const [start, end] of knownSecretSpans(s, extraValues)) {
    parts.push(s.slice(offset, start), REDACTED);
    offset = end;
  }
  return parts.join('') + s.slice(offset);
}

function redactPlain(text, extraValues = []) {
  let s = redactKnown(text, extraValues);
  s = s.replace(BEARER_RE, (_m, scheme) => `${scheme} ${REDACTED}`);
  s = s.replace(PAIR_RE, (match, lead) => SECRET_NAME.test(lead) ? `${lead}${REDACTED}` : match);
  for (const re of TOKEN_SHAPES) s = s.replace(re, REDACTED);
  return s;
}

const TOKEN_METRICS = new Set(['input_tokens', 'output_tokens', 'cached_input_tokens',
  'cache_creation_input_tokens', 'cache_read_input_tokens', 'cache_write_input_tokens',
  'reasoning_output_tokens', 'reasoning_tokens', 'thinking_tokens', 'total_tokens',
  'inputTokens', 'outputTokens', 'cacheReadTokens', 'cacheWriteTokens']);
const TOKEN_FIELDS = new Set(['input_total', 'input_fresh', 'cache_read', 'cache_write',
  'output_total', 'reasoning', 'total', 'input', 'output', 'cacheRead', 'cacheWrite']);

// Replace value spans, not the serialized document: numeric lexemes, whitespace
// and record boundaries survive, including counters outside JS's safe integers.
function redactJson(text, extraValues) {
  try { JSON.parse(text); } catch { return null; }
  const strings = /"[^"\\]*(?:\\.[^"\\]*)*"|true|false|null|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?/g;
  const known = knownSecretSpans(text, extraValues);
  const opaque = () => text.slice(0, text.length - text.trimStart().length) + JSON.stringify(REDACTED) + text.slice(text.trimEnd().length);
  // A known secret crossing literal boundaries contains JSON syntax. Hide the
  // record rather than discard part of that match or publish broken JSON.
  let next = 0;
  for (let match; next < known.length && (match = strings.exec(text));) {
    while (next < known.length && known[next][0] < strings.lastIndex) {
      if (known[next][0] < match.index || known[next][1] > strings.lastIndex) return opaque();
      next++;
    }
  }
  if (next < known.length) return opaque();
  strings.lastIndex = 0;
  const separator = /\s*:\s*/y;
  const parts = [];
  let offset = 0;
  const replace = (start, end, value) => {
    parts.push(text.slice(offset, start), JSON.stringify(value));
    offset = end;
  };
  for (let match; (match = strings.exec(text));) {
    if (match[0][0] !== '"') {
      if (redactKnown(match[0], extraValues) !== match[0]) replace(match.index, strings.lastIndex, REDACTED);
      continue;
    }
    const value = JSON.parse(match[0]);
    const hidden = redactKnown(match[0], extraValues) !== match[0] ? REDACTED : redactPlain(value, extraValues);
    if (hidden !== value) replace(match.index, strings.lastIndex, hidden);
    separator.lastIndex = strings.lastIndex;
    if (!separator.exec(text) || !SECRET_NAME.test(value)) continue;
    const start = separator.lastIndex;
    let end = start;
    if (text[start] === '{' || text[start] === '[') {
      const tokens = /"[^"\\]*(?:\\.[^"\\]*)*"|[{}\[\]]/g;
      tokens.lastIndex = start;
      let depth = 0;
      for (let token; (token = tokens.exec(text));) {
        if (token[0][0] === '"') continue;
        depth += token[0] === '{' || token[0] === '[' ? 1 : -1;
        if (!depth) { end = tokens.lastIndex; break; }
      }
    } else if (text[start] === '"') {
      strings.lastIndex = start;
      strings.exec(text);
      end = strings.lastIndex;
    } else {
      while (end < text.length && !/[\s,}\]]/.test(text[end])) end++;
    }
    const raw = text.slice(start, end), parsed = JSON.parse(raw);
    const metric = TOKEN_METRICS.has(value) && (typeof parsed === 'number' || parsed === null);
    const counters = value === 'tokens' && parsed && !Array.isArray(parsed) && typeof parsed === 'object'
      && Object.keys(parsed).length > 0 && Object.entries(parsed).every(([key, number]) =>
        (TOKEN_FIELDS.has(key) || TOKEN_METRICS.has(key)) && (typeof number === 'number' || number === null)
        || key === 'fidelity' && ['exact', 'partial', 'unavailable'].includes(number));
    const details = value === 'output_tokens_details' && parsed && typeof parsed === 'object'
      && !Array.isArray(parsed) && Object.keys(parsed).length > 0
      && Object.entries(parsed).every(([key, number]) => TOKEN_METRICS.has(key) && (typeof number === 'number' || number === null));
    if ((metric || counters || details) && redactKnown(raw, extraValues) === raw) {
      strings.lastIndex = start;
      continue;
    }
    replace(start, end, REDACTED);
    strings.lastIndex = end;
  }
  return parts.join('') + text.slice(offset);
}

export function redact(text, extraValues = []) {
  const s = String(text);
  const json = redactJson(s, extraValues);
  if (json !== null) return json;
  // Mixed diagnostics and JSONL keep complete records parseable; partial records
  // still receive the existing plain-text credential masking.
  const lines = s.split(/(?<=\n)/), records = lines.map(line => redactJson(line, extraValues));
  if (records.every(record => record === null)) return redactPlain(s, extraValues);
  return records.map((record, index) => record ?? redactPlain(lines[index], extraValues)).join('');
}

// Cut `text` to at most `max` characters (code points), reporting what was lost.
export function clipChars(text, max) {
  const s = String(text ?? '');
  let chars = 0, prefix = '';
  for (const ch of s) { if (chars < max) prefix += ch; chars++; }
  return { text: chars <= max ? s : prefix, chars, truncated: chars > max };
}

// A byte slice can start or end inside a multibyte character. Drop the partial
// sequences so the decoded text never carries a replacement character that was
// not in the original output.
function trimPartial(buf, atStart, atEnd) {
  let a = 0;
  let b = buf.length;
  if (atStart) while (a < b && (buf[a] & 0xc0) === 0x80) a++;
  if (atEnd && b > a) {
    let i = b - 1;
    let back = 0;
    while (i > a && (buf[i] & 0xc0) === 0x80 && back < 3) { i--; back++; }
    const lead = buf[i];
    const need = lead >= 0xf0 ? 4 : lead >= 0xe0 ? 3 : lead >= 0xc0 ? 2 : 1;
    if (need > b - i) b = i;
  }
  return buf.subarray(a, b);
}

// Read the first `head` and last `tail` bytes of a file without loading the rest.
// Returns decoded, redacted excerpts plus the byte accounting the reader needs to
// know what was left out. A file that fits in head+tail comes back whole, in
// `head`, with an empty `tail`.
export function excerptFile(file, { head = 4096, tail = 4096, secrets = [] } = {}) {
  let size;
  try { size = fs.statSync(file).size; } catch { return null; }
  const fd = fs.openSync(file, 'r');
  try {
    const read = (pos, len) => {
      const buf = Buffer.alloc(len);
      let got = 0;
      while (got < len) {
        const n = fs.readSync(fd, buf, got, len - got, pos + got);
        if (n <= 0) break;
        got += n;
      }
      return buf.subarray(0, got);
    };
    if (size <= head + tail) {
      const whole = read(0, size);
      return {
        total_bytes: size, omitted_bytes: 0, truncated: false,
        head: redact(whole.toString('utf8'), secrets), tail: '',
      };
    }
    // Keep complete lines at excerpt boundaries. A sliced credential could evade
    // redaction, and a sliced JSON record is not useful evidence. Oversized
    // single records are omitted with byte accounting rather than leaked.
    let h = trimPartial(read(0, head), false, true);
    let t = trimPartial(read(size - tail, tail), true, false);
    const hn = h.lastIndexOf(10), tn = t.indexOf(10);
    h = hn < 0 ? h.subarray(0, 0) : h.subarray(0, hn + 1);
    t = tn < 0 ? t.subarray(0, 0) : t.subarray(tn + 1);
    return {
      total_bytes: size, omitted_bytes: size - h.length - t.length, truncated: true,
      head: redact(h.toString('utf8'), secrets), tail: redact(t.toString('utf8'), secrets),
    };
  } finally {
    fs.closeSync(fd);
  }
}

// Bound every variable-sized result field, retaining semantic keys and unknowns.
// The original result and logs are never rewritten by this projection.
export function projectResult(result, { chars = 2000, items = 40,
  secrets = Object.entries(process.env).filter(([k, v]) => v && /token|secret|passw|api.?key|credential|authorization/i.test(k)).map(([, v]) => v),
} = {}) {
  const truncated = [];
  let remainingChars = 32000, remainingNodes = 1000;
  function visit(v, key, depth = 0) {
    if (--remainingNodes < 0) {
      if (truncated.length < 200) truncated.push({ path: key, node_limit: true });
      return null;
    }
    if (depth > 12) { truncated.push({ path: key, depth_limit: true }); return null; }
    if (typeof v === 'string') {
      const c = clipChars(redact(v, secrets), Math.min(chars, remainingChars));
      remainingChars -= Array.from(c.text).length;
      if (c.truncated) truncated.push({ path: key, original_chars: c.chars });
      return c.text;
    }
    if (Array.isArray(v)) {
      if (v.length > items) truncated.push({ path: key, original_items: v.length });
      return v.slice(0, items).map((x, i) => visit(x, `${key}[${i}]`, depth + 1));
    }
    if (v && typeof v === 'object') {
      const entries = Object.entries(v);
      if (entries.length > 100) truncated.push({ path: key, original_keys: entries.length });
      return Object.fromEntries(entries.slice(0, 100).map(([k, x]) => {
        const safeKey = clipChars(redact(k, secrets), 128);
        if (safeKey.truncated) truncated.push({ path: key, key_truncated: true });
        return [safeKey.text, visit(x, key ? `${key}.${safeKey.text}` : safeKey.text, depth + 1)];
      }));
    }
    return v;
  }
  // Explicit top-level selection excludes prompt/task/raw usage content from the
  // public summary, while keeping normalised usage and all failure provenance.
  const keys = ['schema', 'legacy', 'run_id', 'parent_run_id', 'harness', 'status',
    'requested_model', 'actual_model', 'model', 'model_observed', 'model_reported', 'tokens',
    'cost_usd', 'cost_reported', 'exit_code', 'signal', 'duration_ms',
    'truncated_output', 'records_dropped', 'files_claimed', 'dirty_paths_changed', 'head_changed',
    'index_changed', 'coverage_complete', 'read_only_violation', 'started_at', 'ended_at', 'execution',
    'status_reason', 'status_provenance', 'summary', 'artifacts'];
  const projected = visit(Object.fromEntries(keys.filter(k => k in result).map(k => [k, result[k]])), '');
  projected.actual_model ??= null;
  projected.model_observed ??= false;
  projected.requested_model ??= null;
  return { ...projected, projection: { mode: 'summary', truncated: truncated.length > 0, limits: { chars, items, total_chars: 32000, nodes: 1000, depth: 12 }, omissions: truncated } };
}
