---
name: weights-watch
description: Measure how strongly and how correctly the leading LLMs recognize a set of entities (people, projects, standards) from parametric memory alone, grade each answer against ground truth, track it across runs and model releases, and surface corrective priorities. A weights-presence feedback loop.
---

# weights-watch

A monitoring loop for whether your entities are "in the weights," and represented correctly. It replicates what intheweights.com measures (parametric recall across a model panel, no web search) but with your own ground-truth grading, your own history, and no bot-wall to fight.

## Why a panel via OpenRouter, not intheweights

intheweights.com sits behind Cloudflare Turnstile; automating it means defeating a bot wall, which this skill does not do. Instead it queries a model panel through **OpenRouter**: one API key reaches GPT, Claude, Gemini, Llama, Mistral, Qwen, DeepSeek, and more, pay-per-use, pennies per run. You control the prompts and the grading.

## intheweights stays in the loop (by hand)

intheweights is a useful complementary signal: it measures the confident-description surface, what a casual user sees a model say about you, which counts confabulation as recognition. weights-watch measures real knowledge (honest UNKNOWN escape plus correctness grading). The divergence between them is the metric that matters: a high intheweights strength with near-zero weights-watch recognition is a **confabulation surface**, the model will describe you confidently and wrongly.

Because the site is Turnstile-protected, do not automate it. When you check it by hand, record the reading in `intheweights.json` (strength, headline description, date) per entity. The report then shows both signals side by side, flags the confabulation-surface gap, and you can re-render the report after editing that file with:

```bash
uv run python weights_watch.py --report
```

## The loop's shape (state this every run)

The monitor arm is fast; the correction arm is slow. Models only change their parametric memory on a new training generation, so seeding content now shows up months to a generation later. The value is early warning on hardening errors, measuring whether seeding actually changed the next generation, and never being surprised by what a new model thinks you are. Do not promise fast turnaround.

## Requirements

- `OPENROUTER_API_KEY` in the environment (the env var name is set in `config.json`). Export it directly, or keep it in a local `.env` and source it first with `set -a; source .env; set +a`.
- `uv` for running Python.
- Edit `config.json` first run: the model slugs change over time, so verify them against https://openrouter.ai/models. Entities and their ground-truth descriptions also live there.

## Arguments

- none: run the full panel over all entities in `config.json`.
- a quoted string: treat it as an ad-hoc entity to query this run only (does not persist to config).

## Procedure

1. Run the monitor (source the key first):
   ```bash
   set -a; source .env; set +a
   uv run python weights_watch.py
   ```
   It queries each entity across the panel, grades each answer (CORRECT / PARTIAL / HALLUCINATED / UNKNOWN) against the ground truth, writes `runs/<timestamp>.json`, and writes `report.md` with per-entity recognition, accuracy, and hallucination rates, plus deltas against the previous run and an alerts block.
2. Read `report.md` and the newest `runs/*.json`.
3. In chat, do the judgment layer the script cannot:
   - Summarize per entity: recognition, accuracy, hallucination, and the change since last run.
   - Call out **hardening errors** first (a wrong association gaining strength), then **foundational gaps** (high-priority entities effectively absent), then gains.
   - Quote one or two of the actual hallucinations ("the panel thinks you are X"), because that is the corrective target.
   - Propose **corrective priorities**: which canonical name to standardize on, which author binding is missing, and which trained-on sources to seed (Wikidata/Wikipedia, GitHub READMEs, OSF/Zenodo/arXiv, books, press/podcasts). Person first when the person is the gap.
   - Restate the latency caveat so expectations stay honest.

## Output

- `runs/<timestamp>.json`: full per-model answers and grades for the run (the history).
- `report.md`: the latest human-readable summary with deltas and alerts.
- Chat: the interpreted summary and corrective priorities.

## Scheduling (optional)

Run weekly and on any new model release. Point cron, a launchd plist, or a systemd timer at `run.sh`, and leave `report.md` for review; only escalate when the alerts block is non-empty. Keep the cadence gentle (a handful of entities, weekly) to stay cheap.

## House style

Authored summaries follow the Open Honest house style: no em-dashes, and calibrated claims. A strength number is recognition, not correctness, and a confident description can be a confabulation. Do not overclaim that seeding will produce fast results.

## Honesty note

This is a measurement instrument for entity recognition and confabulation, which is the Foundation's own subject matter. Use it as such: report what the panel actually says, including when it is confidently wrong about you, rather than chasing a vanity score. Never seed via spam, fake reviews, or manipulation; legitimate presence (real deposits, real code, real third-party engagement, consistent accurate naming) is the only method that fits an Open Honest project.
