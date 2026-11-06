# BookLeaf – Author Royalty Dashboard & Automated Notifications

Bubble.io front end + n8n workflow + Claude (Anthropic API) for royalty summary emails.

| Piece | Where |
|---|---|
| Bubble app (editor) | [bubble.io/page?id=riteshgaur221](https://bubble.io/page?id=riteshgaur221) – the editor is set to "Everyone can view" (the free plan can't invite collaborators) |
| Live app | https://riteshgaur221.bubbleapps.io/version-test (free plan: deploying to live needs a paid plan) |
| n8n workflow | `n8n/royalty-summary-workflow.json` (import into any n8n instance) |
| Webhook | `POST https://bookleafassignment.app.n8n.cloud/webhook/royalty-summary` |
| Dataset | `scripts/bookleaf_sample_data.json` → `data/*.csv` via `scripts/make_csvs.py` |

---

## 1. Bubble database

**Option sets** (fixed vocabularies, so filters and conditionals never depend on free text)

| Option set | Options |
|---|---|
| Role | Author, Admin |
| PayoutStatus | Paid, Pending, Overdue |
| NotificationStatus | Processing, Success, Failed |
| Platform | Amazon India, Flipkart, Amazon US, Amazon UK, BookLeaf Store |
| PrintPartner | In-House, Repro India, Epitome Books |

**Data types**

- **User** – built-in login. `full_name`, `role` (Role), `author_profile` (Author).
- **Author** – `author_code`, `name`, `email`, `phone`, `city`, `joined_date`, `user`, and
  denormalised totals `total_books`, `total_earned`, `total_paid`, `total_pending`, `payout_status`.
- **Book** – `book_code`, `title`, `isbn`, `genre`, `status`, `is_published`, `production_stage`,
  `publication_date`, `mrp`, `royalty_per_copy`, `copies_sold`, `royalty_earned`, `royalty_paid`,
  `royalty_pending`, `last_payout_date`, `print_partner`, `available_on` (list of Platform),
  `author` (Author), `royalty_status`.
- **Payout** – `author`, `book`, `amount`, `paid_on`, `note` (payout history).
- **NotificationLog** – `author`, `status` (NotificationStatus), `request_id`, `triggered_by`,
  `trigger_type` (single / bulk), `triggered_at`, `completed_at`, `email_subject`, `email_body`,
  `error_message`, `model`.

Why it is shaped this way:

- **User and Author are separate.** An author record exists whether or not that person has
  ever logged in (the dataset has 10 authors and no logins). `User.author_profile` links a
  login to exactly one author, and every privacy rule hangs off that link.
- **Totals are stored on Author.** The admin overview lists every author with four sums and
  filters on payout status; storing them avoids nested searches in every row of a repeating group.
  They match the dataset's `author totals` and are the figures the admin filters on.
- **The book badge is computed live** (conditionals on `royalty_pending`, `last_payout_date`,
  `publication_date` vs *Current date/time*), so it changes colour as time passes without any job.
- **NotificationLog stores the generated email**, so an admin can read exactly what the AI wrote.

### Status rule (badge)

| Badge | Rule |
|---|---|
| Green – Paid | `royalty_pending = 0` |
| Red – Overdue | pending > 0 and last payout more than 90 days ago, or never paid on a published book that is more than 90 days old |
| Yellow – Pending | any other pending amount (inside the normal quarterly cycle) |
| Grey – In production | unpublished book (shows its production stage) |

With today's date (Nov 2026) every pending balance in the sample data is older than 90 days
(last payouts are in 2025), so 9 of 10 authors show **Overdue** and only Farhan Siddiqui is fully
paid. That is a property of the data, not a bug; shift the dates and yellow appears.

## 2. Privacy rules (A4)

| Type | Rule | Condition |
|---|---|---|
| Author | Own profile | `This Author is Current User's author_profile` |
| Book | Own books | `This Book's author is Current User's author_profile` |
| Payout | Own payouts | `This Payout's author is Current User's author_profile` |
| NotificationLog | — | admins only |
| User | Own data | Bubble default (`This User is Current User`) |
| all of the above | Admins see all | `Current User's role is Admin` |

*Everyone else* sees nothing and can't find anything in searches. These rules run on Bubble's
server, so an author can't read another author's data even by editing requests in the browser;
hiding elements on the page would not be enough.

**Linking a login to an author.** A sign-up gets `role = Author`. An admin then sets that user's
`author_profile` in App Data. Linking by matching email would be a self-service alternative, but
Bubble privacy rules can't compare against `Current User's email`, and letting any new account
search all authors by email would leak data. Admin linking keeps the rules strict.

## 3. Integration (Bubble ⇄ n8n ⇄ Claude)

```
Admin clicks "Generate & Send"
  └─ Bubble: create NotificationLog (status Processing, request_id = unique id), disable button
  └─ Bubble API Connector → POST /webhook/royalty-summary
        header  X-BookLeaf-Secret: <shared secret>   (private key, never sent to the browser)
        body    { request_id, author{author_code,name}, books[ … per-book figures … ] }
  └─ n8n: verify secret → validate + de-duplicate → compute facts → Claude → parse/validate
  └─ n8n responds { status: Success|Failed, email_subject, email_body, model, error_message, completed_at }
  └─ Bubble: update the same NotificationLog with status + email/error + completed_at, re-enable button
```

**Push the data in the webhook, don't fetch it (B.2).** Bubble sends the author and their books
in the request. Reasons:

1. The n8n side needs no Bubble credentials and no knowledge of the Bubble schema.
2. The email is generated from exactly what the admin was looking at when they clicked.
3. Bubble's Data API is **not available on the free plan** ("This application does not expose an
   API. Please upgrade your Bubble subscription"), so fetching from Bubble was not possible anyway.

**Callback (B.5).** The brief asks n8n to call Bubble back with status and timestamp. On the free
plan Bubble can't receive calls (no Data API, no backend workflows), so the workflow returns the
status in its **synchronous webhook response** instead, and Bubble's workflow writes it to the log.
Same contract: `status`, `completed_at`, plus the email or error. On a paid plan the
"Respond" nodes would become an HTTP Request to a Bubble backend workflow, with no other changes.

**Bulk trigger.** "Send to all pending" on the admin page calls the webhook **once per author**
with pending royalties and creates one NotificationLog per author (`trigger_type = bulk`). With
no backend workflows on the free plan, it runs on the page:

1. The button sets the page state `bulk_queue` = `Search for Authors (total_pending > 0)` and
   triggers the custom event `bulk_next`. It only runs when `bulk_queue` is empty, so a second
   click can't start a parallel batch.
2. `bulk_next` (only when `bulk_queue:count > 0`) runs the same five steps as the single-author
   button for `bulk_queue:first item`, removes that author from the queue, and schedules
   `bulk_loop`.
3. `bulk_loop` schedules `bulk_next` again after 1 s. Bubble doesn't let a custom event schedule
   itself, so the two events hand off to each other until the queue is empty.

Each author is a separate call with its own log row, so one failure doesn't stop the batch. The
admin has to keep the page open while it runs; a backend workflow would remove that limit on a
paid plan.

**Notification Log.** The `notifications` page (admins only) lists every NotificationLog,
newest first, with the author's name, time, Success / Failed / Processing pill, subject and error.
The author detail page shows the same list for one author.

## 4. n8n workflow

`n8n/royalty-summary-workflow.json` (generated by `n8n/build_workflow.py`; the Code-node
JavaScript lives in `n8n/code/*.js` so it can be read and diffed).

| # | Node | Purpose |
|---|---|---|
| 1 | Webhook (from Bubble) | POST, **Header Auth** on `X-BookLeaf-Secret`. Wrong/missing secret → 403 before any node runs. |
| 2 | Validate & de-duplicate | Requires `request_id`, `author_code`, `name`, at least one book. Rejects a repeat request for the same author within 2 minutes (workflow static data). |
| 3 | Valid request? | false → *Respond: rejected* (`status: Failed`, reason). |
| 4 | Compute royalty facts | All numbers and dates in code: totals, per-book status, 90-day overdue rule, ₹1,000 minimum, next payout deadline (end of quarter + 45 days), production stages. |
| 5 | Claude: write summary email | Anthropic Messages API, `claude-haiku-5-5`, structured output `{subject, body}`. 60 s timeout, 3 tries 3 s apart; on final error goes to the error branch. |
| 6 | Parse email → Email usable? | Handles refusal / truncation / invalid JSON / too-short body. |
| 7 | Respond: success / failed | Always answers Bubble with a definite status. |

### Error handling

| Failure | What happens | What the admin sees |
|---|---|---|
| Wrong secret | n8n returns 403 before any node runs | Log → Failed (via the page error handler) |
| Bad / empty payload | Respond: rejected | Log → Failed with the reason |
| Double click / repeat within 2 min | Respond: rejected | Log → Failed, "Duplicate request … try again in Ns" |
| Anthropic 5xx / 429 / timeout | Retried 3×, then error branch | Log → Failed, "AI service error (HTTP …)" |
| AI refuses / truncated / invalid JSON | Parse email → error branch | Log → Failed with the reason |
| n8n unreachable / wrong secret | The API call fails; the page's "unexpected error" workflow marks this author's Processing logs as Failed | Log → Failed, button re-enabled |

Every path ends in a response, so the Bubble button never spins forever.

### Idempotency

- **Bubble:** the button is disabled while the author's latest log is *Processing*.
- **n8n:** a server-side dedupe window per author (2 min) catches double clicks, two admins
  clicking at once, or a client retry. `request_id` is generated per click and echoed back so the
  response updates the right log row.

## 5. Prompt strategy (AI 20%)

- **Facts in code, prose by the model.** Totals, statuses, overdue checks and the payout
  deadline are computed in `compute_facts.js` and passed as a `<facts>` JSON block. The model
  never does arithmetic or date maths, so it can't invent a figure.
- **System prompt = BookLeaf knowledge**: the royalty policy (80/20 split, quarterly + 45 days,
  ₹1,000 minimum rolls over, per-platform breakdown in the dashboard), the production stages,
  and the tone guide (empathetic, specific, own delays plainly, commit to 48-hour resolution when
  overdue, clear next step). The per-author facts go in the user turn.
- **Email rules mirror the brief:** first-name greeting, one line per book, totals, next payout
  date, a positive note when all paid, one sentence per in-production book, warm sign-off from
  "The BookLeaf Author Support Team", 150–280 words, plain text.
- **Structured output** (`output_config.format` JSON schema `{subject, body}`) means no
  regex-parsing of free text; `parse_email.js` still validates it.
- **Prompt injection:** the facts are wrapped in tags and the system prompt says to treat them as
  data. Author names and titles come from the database, but they are still user-supplied text.
- **Edge cases checked:** overdue (Ananya – apologises, 48 h commitment), all paid
  (Farhan – warm thank-you), pending below ₹1,000 (Kavita – explains rollover rather than
  calling it late), author with an in-production book (stage sentence).
- **Model choice:** Haiku is fast (≈5–7 s end to end) and cheap (~1.2k input / ~0.5k output
  tokens per email); the task is constrained writing over given facts, which doesn't need a
  larger model.

## 6. Running it

1. Import `n8n/royalty-summary-workflow.json` into n8n, create two **Header Auth** credentials
   (`X-BookLeaf-Secret` = shared secret; `x-api-key` = Anthropic key), attach them to the Webhook
   and Claude nodes, publish.
2. In Bubble → Plugins → API Connector → *BookLeaf n8n*, set **Private key** to the same shared secret.
3. Test logins: see the submission email (author + admin).

Quick check of the webhook from a terminal:

```bash
curl -X POST https://bookleafassignment.app.n8n.cloud/webhook/royalty-summary \
  -H "Content-Type: application/json" -H "X-BookLeaf-Secret: $SECRET" \
  -d '{"request_id":"t1","author":{"author_code":"AUTH003","name":"Ananya Reddy"},"books":[{"title":"Between Two Temples","status":"Published","is_published":true,"copies_sold":67,"royalty_per_copy":38,"royalty_earned":2546,"royalty_paid":0,"royalty_pending":2546,"publication_date":"2025-03-01"}]}'
```

## 7. Challenges & learning

- **Bubble free plan limits** shaped the design: no Data API or Workflow API (so no callback
  into Bubble and no n8n-side fetch), no CSV import (data was entered through the App Data
  editor), no backend workflows (bulk trigger runs as a page-level recursive event), no live
  deploy (app runs on `version-test`). Each limit and its workaround is documented above;
  on a paid plan the callback would become an HTTP Request to a backend workflow.
- **n8n Cloud trial** blocks the public API, so the workflow is imported from the JSON file.
- **Keeping the AI honest:** an early version told an author with ₹850 pending both "this is
  overdue, we'll fix it in 48 h" and "it rolls over below ₹1,000". Fix: decide that rule in code
  (`below_threshold` suppresses overdue) and give the model one unambiguous status per book.
  Same for dates – computing "as of" in Asia/Kolkata fixed an off-by-one day.
- **Privacy rules over UI hiding** – the first idea was to filter searches on the page; rules
  on the server are the only thing that actually stops data reaching another author's browser.
- **The first live send logged Failed although n8n had succeeded.** The API Connector had
  "Include errors in response" ticked, which wraps the reply as `body.status`,
  `body.email_subject`, and so on, while the call's fields were defined flat. Every field read
  as empty. n8n already answers every application failure with HTTP 200 and `status: Failed`,
  so I turned that option off. Transport errors such as a timeout or a wrong secret now go to
  the page's error handler instead.
- **Bubble's AI Agent** built the first versions of the login, dashboard, admin and author
  detail pages from written specs. I checked each one in the editor and finished the
  notification log and bulk send by hand once the free AI credits ran low. The Agent was fast
  at layout, but I still had to check every expression: it flagged that the API call exposes no
  "returned an error" field, so the workflow treats an empty `status` as a failed call. That
  is correct here because n8n always answers HTTP 200 with a status.
