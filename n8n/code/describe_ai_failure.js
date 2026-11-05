// Turns an AI-step failure (HTTP error after retries, or an unusable response) into a
// short message the admin can read in the Notification Log.
const item = $input.first().json;
const { request_id } = $('Compute royalty facts').first().json;

let error = item.error;
if (typeof error === 'object' && error !== null) {
  const status = error.httpCode ?? error.status ?? '';
  const message = error.message ?? error.description ?? 'unknown error';
  error = `AI service error${status ? ` (HTTP ${status})` : ''}: ${message}`;
}
if (!error) error = 'AI step failed for an unknown reason.';

return [{ json: { request_id, error: `${error} The summary was not generated; you can retry from the author page.` } }];
