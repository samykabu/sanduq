// Public check-runner JSON pages. Budget includes the final UTF-8 newline.
// Records are included whole; serialization is never sliced to make it fit.
export const DEFAULT_MAX_BYTES = 16384;
export const MIN_MAX_BYTES = 2048;
export function validateMaxBytes(n) {
  if (!Number.isInteger(n) || n < MIN_MAX_BYTES || n > 1048576) throw new Error('--max-bytes must be an integer from 2048 to 1048576');
  return n;
}
export function counts(checks) {
  const result = {};
  for (const c of checks) result[c.status] = (result[c.status] || 0) + 1;
  return result;
}
export function decodeCursor(text) {
  if (typeof text !== 'string' || text.length > 1024 || !/^[A-Za-z0-9_-]+$/.test(text)) throw new Error('invalid collection cursor');
  let c;
  try { c = JSON.parse(Buffer.from(text, 'base64url').toString('utf8')); } catch { throw new Error('invalid collection cursor'); }
  if (c.v !== 1 || !Number.isInteger(c.offset) || c.offset < 0 || typeof c.batch !== 'string' || typeof c.latest !== 'string' || typeof c.scope !== 'string') throw new Error('invalid collection cursor');
  return c;
}
const pick = (o, keys) => Object.fromEntries(keys.filter(k => k in o).map(k => [k, o[k]]));
const attemptKeys = ['schema', 'batch_id', 'attempt_id', 'retry_of', 'manifest_sha256', 'owner_pid', 'started_at', 'ended_at', 'status', 'status_provenance'];
function header(a) {
  return { ...pick(a, attemptKeys), status_provenance: a.status_provenance ?? null,
    total_checks: a.total_checks ?? a.checks.length, check_status_counts: a.check_status_counts || counts(a.checks), checks: [] };
}
function wire(o) {
  // emitted_bytes includes its own digits; converge before testing the budget.
  let text;
  for (let i = 0; i < 8; i++) {
    text = JSON.stringify(o) + '\n';
    const bytes = Buffer.byteLength(text, 'utf8');
    if (o.projection.emitted_bytes === bytes) return text;
    o.projection.emitted_bytes = bytes;
  }
  throw new Error('receipt byte accounting did not converge');
}
export function encodeReceipt(receipt, maxBytes = DEFAULT_MAX_BYTES, cursorText = null) {
  validateMaxBytes(maxBytes);
  const collection = Array.isArray(receipt.attempts);
  const attempts = collection ? receipt.attempts : Array.isArray(receipt.checks) ? [receipt] : [];
  const latest = receipt.latest_attempt_id || attempts.at(-1)?.attempt_id || '';
  const scope = JSON.stringify(receipt.selection || { attempt: receipt.attempt_id || null, limit: 1, check_index: null });
  const previous = cursorText ? decodeCursor(cursorText) : null;
  if (previous && (previous.batch !== receipt.batch_id || previous.latest !== latest || previous.scope !== scope)) throw new Error('cursor no longer matches latest attempt or selection; restart collection');
  const records = attempts.flatMap(a => a.checks.map((c, i) => ({ a, c, index: c.check_index ?? i })));
  let offset = previous?.offset || 0;
  if (offset > records.length) throw new Error('cursor offset exceeds selected checks');
  const root = collection
    ? pick(receipt, ['schema', 'batch_id', 'status', 'status_provenance', 'latest_attempt_id', 'latest_status', 'total_attempts', 'omitted_attempts', 'status_counts', 'omitted_status_counts', 'total_checks', 'check_status_counts', 'selection'])
    : Array.isArray(receipt.checks)
      ? { ...header(receipt), ...pick(receipt, ['busy', 'refused', 'requires_explicit_retry', 'execution_performed', 'latest_attempt_id']) }
      : { ...pick(receipt, ['schema', 'batch_id', 'busy', 'refused']), status: receipt.status ?? null,
        status_provenance: receipt.status_provenance ?? null, total_checks: null, check_status_counts: null, checks: [] };
  if (collection) root.attempts = [];
  root.projection = { max_bytes: maxBytes, emitted_bytes: 0, metadata_projected: true, truncated: false,
    selected_attempts: attempts.length, emitted_attempts: 0, omitted_attempts: attempts.length, offset,
    selected_checks: records.length, emitted_checks: 0, omitted_checks: records.length,
    oversized_records: 0, next_cursor: null, narrow: null };
  function update(next, oversized = null) {
    root.projection.emitted_attempts = collection ? root.attempts.length : attempts.length;
    root.projection.omitted_attempts = attempts.length - root.projection.emitted_attempts;
    root.projection.omitted_checks = records.length - root.projection.emitted_checks;
    root.projection.truncated = root.projection.omitted_checks > 0 || Boolean(receipt.omitted_attempts);
    root.projection.next_cursor = next < records.length
      ? Buffer.from(JSON.stringify({ v: 1, batch: receipt.batch_id, latest, scope, offset: next })).toString('base64url') : null;
    root.projection.narrow = oversized || (next < records.length ? { attempt: records[next].a.attempt_id, check_index: records[next].index, output_bytes: 0 } : null);
  }
  update(offset);
  if (Buffer.byteLength(wire(root), 'utf8') > maxBytes) throw new Error('mandatory receipt metadata exceeds --max-bytes; narrow with --attempt or raise the budget');
  for (; offset < records.length; offset++) {
    const { a, c, index } = records[offset];
    let target = collection ? root.attempts.find(x => x.attempt_id === a.attempt_id) : root;
    let addedHeader = false;
    if (!target) { target = header(a); root.attempts.push(target); addedHeader = true; }
    target.checks.push({ ...c, check_index: index });
    root.projection.emitted_checks++;
    update(offset + 1);
    if (Buffer.byteLength(wire(root), 'utf8') <= maxBytes) continue;
    target.checks.pop(); root.projection.emitted_checks--;
    if (addedHeader) root.attempts.pop();
    if (root.projection.emitted_checks > 0) { update(offset); break; }
    // A single record cannot fit an otherwise empty page. Advance one whole
    // record and expose a precise narrowing target rather than loop forever.
    root.projection.oversized_records = 1;
    update(offset + 1, { attempt: a.attempt_id, check_index: index, output_bytes: 0,
      metadata: `${a.attempt_id}/${String(index + 1).padStart(3, '0')}.result.json` });
    break;
  }
  const text = wire(root);
  if (Buffer.byteLength(text, 'utf8') > maxBytes) throw new Error('receipt metadata exceeds --max-bytes; raise the budget');
  return text;
}
