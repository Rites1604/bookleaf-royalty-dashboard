// Validates the payload Bubble sends and drops duplicate triggers.
//
// Bubble posts the author's full record (author + books) in one request, so n8n never
// needs Bubble's Data API (which Bubble's free plan does not expose).
//
// Idempotency: a request for the same author inside DEDUPE_WINDOW_MS is rejected as a
// duplicate. Workflow static data persists between production executions, so this
// survives across separate webhook calls. Bubble also disables the button while a
// request is in flight; this is the server-side backstop.
const DEDUPE_WINDOW_MS = 2 * 60 * 1000;

const body = $input.first().json.body ?? {};
const author = body.author ?? {};
const books = Array.isArray(body.books) ? body.books : [];
const requestId = String(body.request_id ?? '').trim();

const fail = (error) => [{ json: { ok: false, error, request_id: requestId } }];

if (!requestId) return fail('Missing request_id');
if (!author.author_code || !author.name) return fail('Missing author_code or author name');
if (books.length === 0) return fail(`No books found for ${author.author_code}`);

const state = $getWorkflowStaticData('global');
state.recent = state.recent ?? {};
const now = Date.now();
for (const [key, at] of Object.entries(state.recent)) {
  if (now - at > DEDUPE_WINDOW_MS) delete state.recent[key];
}
const last = state.recent[author.author_code];
if (last && now - last < DEDUPE_WINDOW_MS) {
  const seconds = Math.ceil((DEDUPE_WINDOW_MS - (now - last)) / 1000);
  return fail(`Duplicate request: a summary for ${author.author_code} was generated moments ago. Try again in ${seconds}s.`);
}
state.recent[author.author_code] = now;

return [{ json: { ok: true, request_id: requestId, author, books } }];
