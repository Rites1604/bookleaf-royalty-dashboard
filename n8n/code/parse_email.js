// Pulls subject/body out of Claude's structured-output response and checks it is usable.
const res = $input.first().json;
const { request_id } = $('Compute royalty facts').first().json;

const fail = (error) => [{ json: { ok: false, request_id, error } }];

if (res.stop_reason === 'refusal') return fail('The AI declined to write this summary.');
if (res.stop_reason === 'max_tokens') return fail('The AI response was cut off before finishing.');

const text = (res.content ?? []).filter((c) => c.type === 'text').map((c) => c.text).join('');
let email;
try {
  email = JSON.parse(text);
} catch {
  return fail('The AI returned text that was not valid JSON.');
}
if (!email.subject || !email.body || email.body.length < 80) return fail('The AI returned an empty or too-short email.');

return [{ json: { ok: true, request_id, subject: email.subject.trim(), body: email.body.trim(), model: res.model } }];
