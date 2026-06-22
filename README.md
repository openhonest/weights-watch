# weights-watch

A small monitoring loop for one question: do the leading language models know who or what you are, from memory alone, and do they get it right?

It asks a panel of models to describe a set of entities (people, projects, standards) with no web search, gives each model an explicit way to say it does not know, and then grades every answer against a ground truth you supply. It stores each run and diffs it against the last one, so you can watch recognition rise, accuracy improve, or a wrong answer harden across model releases.

## Why this exists, and how it differs from "in the weights"

There is a popular tool, [intheweights.com](https://intheweights.com), that types a name into several models and reports how strongly they recognize it. It is a good idea and it is what prompted this. But it counts any confident description as recognition. If a model has never heard of you and assembles a plausible-sounding paragraph out of the words in your name, that still scores as "recognized."

weights-watch is built to separate real knowledge from confident guessing. It does two things differently:

1. **It gives the model an honest exit.** The prompt says: if you do not recognize this, reply with the single word UNKNOWN. A model that does not know is allowed to say so instead of inventing.
2. **It grades against the truth.** A second model compares each answer to a ground-truth description you wrote and labels it CORRECT, PARTIAL, HALLUCINATED, or UNKNOWN. Only correct recognition counts.

The interesting number is the gap between the two tools. A high "in the weights" strength next to a near-zero weights-watch recognition is a **confabulation surface**: the model will describe you confidently and wrongly to anyone who asks. weights-watch keeps the manual "in the weights" reading in the loop (you record it by hand in `intheweights.json`, since that site is bot-protected and should not be automated) and shows both signals side by side so the gap is visible.

## What you get

For each entity, per run:

- **Recognition**: the fraction of the panel that recognized it at all (did not say UNKNOWN).
- **Accuracy**: of those that recognized it, the fraction that got it right rather than confabulating.
- **Hallucination**: the fraction that confidently described the wrong thing.
- **Deltas** against the previous run, and an alerts block that flags hardening errors, foundational gaps, and confabulation surfaces.

The report also quotes actual hallucinations from the panel, because the specific wrong answer ("the models think you represent a soccer player") is the thing you correct.

## Quick start

You need an [OpenRouter](https://openrouter.ai) API key (one key reaches GPT, Claude, Gemini, Llama, Mistral, Qwen, DeepSeek, and more, pay-per-use, a few cents per run) and [uv](https://github.com/astral-sh/uv).

```bash
git clone https://github.com/adamzwasserman/weights-watch
cd weights-watch
cp config.example.json config.json     # then edit: your models and entities
export OPENROUTER_API_KEY=sk-or-...     # or put it in a local .env
uv run python weights_watch.py
```

It writes `runs/<timestamp>.json` (the full history) and `report.md` (the readable summary). Edit `config.json` first: the OpenRouter model slugs change over time, so verify them against [openrouter.ai/models](https://openrouter.ai/models), and write a one or two sentence `ground_truth` for each entity, including a "NOT ..." clause that rules out the confusions you expect.

Pass a quoted string to probe an ad-hoc entity for one run without saving it:

```bash
uv run python weights_watch.py "Some Name You Want To Check"
```

Re-render the report after editing your manual readings, without re-querying the panel:

```bash
uv run python weights_watch.py --report
```

To run it on a schedule, point cron, launchd, or a systemd timer at `run.sh`. Keep the panel small and the cadence gentle (weekly is plenty) to stay cheap.

## The honest part

This tool measures confident-but-wrong description, which is its author's actual research subject, so it is held to its own standard in two ways.

**It passes the Honest Framework's own linter.** weights-watch is published under the [Open Honest Foundation](https://openhonest.org), whose [Honest Framework](https://github.com/adamzwasserman) defines code that is correct by construction and ships a linter (`honest-check`) as its operational definition. `weights_watch.py` passes that linter clean: a pure core that does the prompting, grading, and report logic with no I/O and no hidden state, and a thin declared boundary that does the network calls, file reads, and clock. An honesty tool that could not survive its own framework's discipline would be a joke, so it does.

**It will not game itself.** The correct way to raise these scores is the slow one: write true, verifiable descriptions in durable places and wait for the next training generation to pick them up. weights-watch is a measurement, not a growth hack. Do not seed with spam, fake reviews, or filler. A project about honesty cannot inflate a measurement of honesty without becoming the thing it warns about.

## License

Code is Apache-2.0. See [LICENSE](LICENSE).

By **Adam Zachary Wasserman** ([ORCID](https://orcid.org/0009-0002-8865-6583), [OSF](https://osf.io/user/8t64r)), founder of the **Open Honest Foundation** ([openhonest.org](https://openhonest.org)).
