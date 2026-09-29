# AI usage

How AI tools were used to build this backend, what I did myself, and where the AI got things wrong.

## Tools

| Tool | Used for |
|---|---|
| **Claude desktop app** | Brainstorming the product, working through a design review to lock the requirements, and generating the design spec (`SPEC.md`) that drives both the backend and the frontend. |
| **Claude Code** (Claude Opus 5.5, in the terminal) | Planning and implementing the backend feature by feature: code, tests, local Docker checks, looking up current model and SDK documentation on the web, and reading the installed SDKs' source. |

## How we worked

- **Spec first.** Every decision was written down and locked in the spec before any code. Where the spec was silent, Claude picked the simplest option and flagged it; those choices are listed in the README under "Decisions we made".
- **Plan, approve, then code.** For each feature, Claude wrote a plan (files, functions, edge cases, tests). I reviewed it, asked questions or changed it, and only after my approval did Claude create a feature branch and write the code.
- **One branch per feature, commits by me.** Claude never committed or pushed. I reviewed each branch, committed it and merged it, so the history is one reviewed branch per feature.
- **Rules I set for the code:** no code before approval; the simplest possible code — no comprehensions, generator expressions or lambdas, small single-purpose functions, blank lines between steps, no comments in code files.
- **Decisions I made:** the hosting choice (Google Cloud Run, then back to Render — below); uv and `pyproject.toml` instead of pip; fix the printed-tip bug (below); keep plain SDK calls for the LLM but record that LangChain would have avoided vendor lock-in.
- **Verification beyond unit tests:** Claude ran throwaway scripts against a real Postgres in Docker for every endpoint, including parallel requests, and ran both LLM providers against a mocked HTTP layer to check the exact requests the SDKs send.

## Where the AI got it wrong

### 1. A printed tip was counted twice (main example)

**What happened.** In the validation feature, Claude wrote the step that converts the LLM's answer from rupees to paise. As the spec said, it moved `tip` lines out of the charges into `suggested_tip_paise`, which pre-fills the tip field. But it left the **printed total** untouched. The extraction prompt treats every line above the grand total as a charge, so a printed tip is already *inside* the printed total. The result, for any receipt with a printed tip:

- validation raised a false `TOTAL_MISMATCH` (subtotal + charges no longer equalled the total), and
- once the bill was created, the tip would be counted twice, because the grand total is total + tip.

The test at the time only checked that the tip line had moved — not that the receipt still reconciled — so it passed.

**How it was found.** Two features later, while writing the `/extract` tests, Claude built a receipt with a printed ₹100 tip and noticed it no longer reconciled. It raised this with me as a gap in the spec, with a proposed fix, instead of silently changing already-merged behaviour.

**The fix.** I approved it: normalisation now subtracts printed tip lines from the total (`total_without_tip` in `app/extraction.py`), so `total_paise` is the pre-tip receipt total and total + tip equals what's printed. Both tip tests now use a receipt whose printed total includes the tip, and assert that there are **no issues** at all.

**Lesson.** Tests should check the invariant (the receipt still adds up), not just that a transformation happened.

### 2. Code that was too clever

Claude's first version of the split (`app/split.py`) used list and dict comprehensions, a lambda as a sort key, and one large function doing everything. It worked, but it was hard to review. I rejected it. Claude rewrote it as small single-purpose functions with plain loops (`allocate`, `item_weights`, `split_items`, `split_charges`, `fill_row_totals`, …), and that style became a rule for all later code — including going back to fix a generator expression it had written earlier in `app/main.py`.

### 3. Smaller corrections

- **Hosting.** The spec (also AI-generated) named Render for the API. I first moved it to Google Cloud Run, but deploying from source failed: Cloud Build wasn't allowed to push the image to the auto-created Artifact Registry repository. I went back to Render and deployed the same Dockerfile with Render's Docker runtime. Because the container listens on whatever `$PORT` the platform gives it, the same image works on both.
- **Temperature.** The spec asked for temperature 0 on both providers. When Claude checked the current docs, it found that Gemini 3 deprecates sampling parameters and Google warns that low values can make it loop, so Gemini now runs without a temperature setting while OpenAI keeps `temperature=0`.

### Something the AI did to avoid mistakes

The installed `openai` (3.x) and `google-genai` (2.x) SDKs were newer major versions than Claude knew well. Rather than guessing their APIs, it read the installed packages — method signatures, exception classes, which HTTP library raises timeouts, whether the SDK retries by default — and then ran both providers against a mocked HTTP transport to confirm the exact requests (temperature, strict schema, the Gemini key sent in a header rather than the URL) before relying on them.

## What was verified, and how

| Check | How |
|---|---|
| Split is exact to the paisa | Named cases plus Hypothesis properties over thousands of random bills |
| Every validation rule | One test per rule code, using the sample receipts' expected LLM output |
| Extraction and error mapping | Tests with a fake provider; real SDK exception objects for the mapping |
| The LLM key never leaks | A test where a provider logs its key on purpose; the key must not appear in logs or the response |
| Every endpoint | Scripts against real Postgres in Docker |
| Unit cap and 10-person cap under load | Parallel requests against a running server |
| The requests the SDKs actually send | Both providers run against a mocked HTTP transport |
| Real extractions with live keys | Both providers on the sample receipts as text and as images, a non-receipt, a prompt-injection attempt, a printed tip and invalid keys — all matched the expected output — then the whole bill flow on the real Supabase database, with a server-log scan confirming no key or secret was logged |
| The live deployment on Render | The same extraction cases and full bill flow against the deployed URL, plus 9 parallel claims on a 3-unit item through Supabase's connection pooler: exactly 3 succeeded; test data deleted afterwards |
