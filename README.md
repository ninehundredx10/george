# George

A small, curious explorer. No assigned topic, productivity target, mandatory report, shell,
code execution, publishing tool, or ability to change his own permissions or budget.

## First launch

Repository Actions secrets: `OPENAI_API_KEY` and `TELEGRAM_BOT_TOKEN` (already configured).
Run **Actions → George → Run workflow**, with `initialize` checked **only for first creation**.
Send `/start` to [@GeorgeVagabond_bot](https://t.me/GeorgeVagabond_bot). The next check sends a
random one-time pairing code to private chats that requested pairing. Enter **your** code
in the workflow's `pairing_code` field and run again. Repository write access authenticates
the pairing approval; a stranger's `/start` cannot claim George. Codes expire after 24 hours.
Do not share a code except with your trusted setup conversation or workflow.

Pairing triggers the first awakening. Manual `force_wake` can wake him later.
`/pause`, `/resume`, `/status` work without OpenAI calls. Other messages become conversation.
Telegram is polled hourly, so replies can take an hour or longer if GitHub delays a run.
Only paired private-chat messages reach the model. Text only in this version.

## Memory and boundaries

`state.enc` is an authenticated Fernet-encrypted checkpoint committed to GitHub, including
notes, recent conversation, pending messages, chosen next wake, pairing and spending ledger.
The key is derived from the high-entropy Telegram bot token, which is never committed or logged.
The repository is public; checkpoint timing/size and source code are public, memory is encrypted.
OpenAI receives the selected memory, conversation, and fetched page text (`store=false`).
Telegram receives messages sent to your chat. No third-party browsing proxy or analytics.
**Rotating the bot token requires migrating/re-encrypting state with the old token first.**
An unreadable or missing checkpoint fails closed. Never delete or roll back `state.enc`,
or initialize again to recover lost state: restoring an old ledger can invalidate spend limits.
Repository administrators can change code and state; the budget boundary assumes they do not
tamper with the ledger. Keep only one deployment using these credentials and this state.

George chooses a wake delay of 1–168 hours. An hourly workflow checks messages and the delay;
checks alone make no OpenAI calls. GitHub schedules are best-effort, can be delayed, and public
repos can have scheduled workflows disabled after 60 days without repository activity.
Encrypted state commits normally provide activity; check Actions if he becomes silent.
Disable the George workflow to stop all checks.

Read-only browsing permits public HTTPS GETs only, with bounded text downloads, timeouts,
redirect revalidation, DNS/IP pinning and blocked private/link-local addresses. HTML and scripts
are never executed. No authenticated browsing, paid search tools, attachments, or Drive OAuth.
He can choose a search-engine URL and follow links; sites may refuse automated access.

## Independent spending cap

The runtime refuses paid calls after **$5 in conservative reservations per UTC calendar month**,
independent of the OpenAI project's $10 alert budget. Each request durably reserves **$0.05**
BEFORE contacting OpenAI, with no refunds, including failed/uncertain calls and no automatic
paid retries. At most 3 model calls per awakening. Single workflow concurrency and GitHub's
SHA compare-and-swap prevent simultaneous writers from spending against the same balance.
The cap is not writable by model output or Telegram commands. George requests approval via
Telegram on exhaustion; an owner must review and edit the constant to raise it. Otherwise
the next UTC month's allowance resumes automatically. The cap covers this runtime's OpenAI
requests, not other clients on your project or GitHub Actions billing.

Pinned model `gpt-5.4-mini-2026-03-17`, no hosted tools, at most 24,000 UTF-8 input bytes including
instructions and 3,000 output tokens. With a conservative one-token-per-byte input bound plus
protocol overhead, published standard rates ($0.75/M input, $4.50/M output) fit well below $0.05.
Actual charges will generally be lower than reservations. Review prices before changing the
model, request bounds, or reservation amount; no automatic model fallback.
[OpenAI model pricing](https://developers.openai.com/api/docs/models/gpt-5.4-mini).

Costly execution, new integrations, external writes or publishing require a specific approval
request describing scope and cost. This version records/sends such requests but cannot execute
them, even if a chat reply says yes; a human must implement a reviewed capability change.
The preauthorized writes are only encrypted memory checkpoints and private Telegram conversation.

## Validation and operations

Python 3.13; install `requirements.txt`; `python -m unittest discover -s tests -v`.
Unit tests mock paid services and Telegram. Actions runs the same tests before any agent call.
HTTP exceptions are reported by class only: never raw URLs, bot tokens, response bodies or
tracebacks. Do not enable shell tracing or HTTP debug logs. Paid request failures retain their
reservation and back off 12 hours; inbound messages can cause another attempt at the next check.
Model messages use a durable outbox, retried on the next check after a failed send. Delivery is
at least once: a crash after sending but before checkpointing can cause a duplicate. Pairing and
command acknowledgments are best effort. Incoming messages are checkpointed before processing; at most 20 are kept.
Memory is intentionally bounded (6000 characters and six recent conversation entries).

Sources: [Responses API](https://developers.openai.com/api/reference/resources/responses/methods/create),
[Telegram polling](https://core.telegram.org/bots/api#getupdates),
[GitHub schedules](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).
