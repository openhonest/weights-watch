#!/usr/bin/env python3
"""weights-watch: measure how strongly and how correctly LLMs recognize a set of
entities from parametric memory (no web search), grade each answer against a
ground-truth description, store the run, and diff it against the previous run.

Written to the Honest Framework discipline: a pure core (prompts, grading,
summarising, report rendering) that does no I/O and reads no globals, and a thin
boundary (network, files, clock) called only from main. Config travels as a
parameter. Failures are typed results, not magic strings or swallowed
exceptions. That is the point: the confabulation meter passes the framework it
is published under.
"""
from __future__ import annotations
import os
import sys
import json
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import TypedDict


# --------------------------------------------------------------------------- #
# Types: data is just data.
# --------------------------------------------------------------------------- #
class CallResult(TypedDict):
    ok: bool
    text: str
    error: str


class Cell(TypedDict):
    answer: str
    grade: str


class Stats(TypedDict):
    priority: str
    per_model: dict
    n: int
    recognition: float
    accuracy: float
    hallucination: float


# --------------------------------------------------------------------------- #
# Pure core: prompts.
# --------------------------------------------------------------------------- #
RECALL_TEMPLATE = (
    'Who or what is "{name}"? Answer in at most two sentences, using only your '
    "own knowledge. Do not use tools or search. If you do not recognize it, "
    "reply with the single word UNKNOWN and nothing else."
)
GRADE_TEMPLATE = (
    "You are grading whether a model recognized an entity correctly.\n"
    'GROUND TRUTH about "{name}": {truth}\n'
    "THE MODEL ANSWERED: {answer}\n\n"
    "Classify the model's answer with exactly one word: CORRECT (matches the "
    "ground truth in substance), PARTIAL (right entity but vague or missing the "
    "substance), HALLUCINATED (confidently describes a different or made-up "
    "entity), or UNKNOWN (the model said it does not know). Reply with one word."
)
GRADE_LABELS = ("CORRECT", "PARTIAL", "HALLUCINATED", "UNKNOWN")


def recall_prompt(name: str) -> str:
    return RECALL_TEMPLATE.format(name=name)


def grade_prompt(name: str, truth: str, answer: str) -> str:
    return GRADE_TEMPLATE.format(name=name, truth=truth, answer=answer)


# --------------------------------------------------------------------------- #
# Pure core: grading and statistics.
# --------------------------------------------------------------------------- #
def is_unknown(answer: str) -> bool:
    return answer.strip().upper().startswith("UNKNOWN")


def normalize_grade(grader_text: str) -> str:
    upper = grader_text.strip().upper()
    matches = [label for label in GRADE_LABELS if label in upper]
    return matches[0] if matches else "UNCLEAR"


def summarize(priority: str, per_model: dict) -> Stats:
    grades = [c["grade"] for c in per_model.values() if c["grade"] != "ERROR"]
    known = [g for g in grades if g != "UNKNOWN"]
    good = [g for g in grades if g in ("CORRECT", "PARTIAL")]
    hall = [g for g in grades if g == "HALLUCINATED"]
    return Stats(
        priority=priority,
        per_model=per_model,
        n=len(grades),
        recognition=round(len(known) / len(grades), 2) if grades else 0.0,
        accuracy=round(len(good) / len(known), 2) if known else 0.0,
        hallucination=round(len(hall) / len(grades), 2) if grades else 0.0,
    )


def select_entities(argv: list, entities: list) -> list:
    query = " ".join(a for a in argv if not a.startswith("--")).strip()
    if not query:
        return entities
    matches = [e for e in entities if query.lower() in e["name"].lower()]
    if matches:
        return matches
    return [{"name": query, "priority": "adhoc",
             "ground_truth": "No ground truth on file; judge whether the answer "
                             "is a real, consistent description or a confabulation."}]


# --------------------------------------------------------------------------- #
# Pure core: report rendering.
# --------------------------------------------------------------------------- #
PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2, "": 3, "adhoc": 4}


def delta(now: float, prior_stats, key: str) -> str:
    if prior_stats is None or prior_stats.get(key) is None:
        return ""
    d = round(now - prior_stats[key], 2)
    return " (=)" if abs(d) < 0.01 else f" ({'+' if d > 0 else ''}{d})"


def entity_alerts(name: str, r: Stats, prior_r, strength) -> list:
    checks = [
        (r["hallucination"] >= 0.5,
         f"- HIGH HALLUCINATION: {name} at {r['hallucination']} of the panel."),
        (prior_r is not None and r["hallucination"] - prior_r["hallucination"] >= 0.2,
         f"- HARDENING ERROR: {name} hallucination rose since last run. Counter-seed before it cements."),
        (prior_r is not None and r["recognition"] - prior_r["recognition"] >= 0.2,
         f"- GAINING: {name} recognition rose since last run."),
        (r["priority"] == "high" and r["recognition"] <= 0.2,
         f"- FOUNDATIONAL GAP: {name} (high priority) effectively absent from the panel's real knowledge."),
        (strength is not None and strength >= 150 and r["recognition"] <= 0.2,
         f"- CONFABULATION SURFACE: {name} reads strong on intheweights ({strength}) but near-zero real recognition here. A casual user gets a confident wrong or empty answer."),
    ]
    return [message for condition, message in checks if condition]


def render_report(run: dict, prior, intheweights: dict) -> str:
    prior_results = (prior or {}).get("results", {})
    results = run["results"]

    def strength_of(name):
        return (intheweights.get(name) or {}).get("strength")

    ordered = sorted(results.items(), key=lambda kv: PRIORITY_ORDER.get(kv[1]["priority"], 3))

    header = [
        "# weights-watch report", "",
        f"Run: {run['timestamp']}", f"Panel: {len(run['models'])} models",
    ] + ([f"Compared against prior run: {prior['timestamp']}"] if prior else []) + [
        "",
        "Two signals per entity. **weights-watch** (this panel): recognition with "
        "an honest UNKNOWN escape, plus correctness grading, so only real knowledge "
        "counts. **intheweights** (manual, the confident-description surface that "
        "also counts confabulation): the strength last recorded by hand.",
        "",
        "| Entity | Pri | Recognition | Accuracy | Hallucination | intheweights |",
        "|---|---|---|---|---|---|",
    ]
    rows = [
        f"| {name} | {r['priority']} "
        f"| {r['recognition']}{delta(r['recognition'], prior_results.get(name), 'recognition')} "
        f"| {r['accuracy']}{delta(r['accuracy'], prior_results.get(name), 'accuracy')} "
        f"| {r['hallucination']}{delta(r['hallucination'], prior_results.get(name), 'hallucination')} "
        f"| {strength_of(name) if strength_of(name) is not None else '-'} |"
        for name, r in ordered
    ]

    alerts = [a
              for name, r in results.items()
              for a in entity_alerts(name, r, prior_results.get(name), strength_of(name))]
    new_models = sorted(set(run["models"]) - set(prior["models"])) if prior else []
    if new_models:
        alerts = alerts + [f"- NEW MODELS in panel: {new_models}"]
    alerts_section = ["", "## Alerts", ""] + (alerts or ["- none"])

    itw_lines = [f"- {name}: strength {e['strength']} ({e.get('date', '')}). {e.get('description', '')}"
                 for name in results
                 for e in [intheweights.get(name)]
                 if e and e.get("strength") is not None]
    itw_section = ["", "## intheweights readings (manual, last recorded)", ""] + (
        itw_lines or ["- none recorded; update intheweights.json by hand when you check the site."])

    sample = ["", "## Sample hallucinations from this panel", ""] + [
        f"- {name}: {model} said: {cell['answer'][:160]}"
        for name, r in results.items()
        for model, cell in [next(((m, c) for m, c in r["per_model"].items() if c["grade"] == "HALLUCINATED"), (None, None))]
        if model is not None
    ]

    return "\n".join(header + rows + alerts_section + itw_section + sample) + "\n"


# --------------------------------------------------------------------------- #
# Boundary: network, files, clock. The only place I/O and exceptions live.
#
# Everything below this line IS the boundary (and the edge orchestration that
# drives it): it performs I/O and catches exceptions by design, because catching
# belongs at the boundary. The pure core above is under full enforcement. Once
# the Honest Framework ships the @boundary decorator these functions will carry
# it; until then the boundary is declared here, the same way honest-check's own
# cli.py declares its boundary. Suppressed diagnostics are downgraded to info,
# not dropped, so the declaration stays visible.
# honest: disable HC-P004, HC-P002
# --------------------------------------------------------------------------- #
def call_model(model: str, prompt: str, config: dict) -> str:
    """One chat completion. Raises on transport failure or empty content."""
    settings = config["settings"]
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": settings["temperature"],
        "max_tokens": settings["max_tokens"],
        "reasoning": {"effort": "low"},
    }).encode()
    request = urllib.request.Request(
        config["provider"]["base_url"], data=body, method="POST",
        headers={"Authorization": f"Bearer {config['api_key']}",
                 "Content-Type": "application/json",
                 "HTTP-Referer": "https://openhonest.org", "X-Title": "weights-watch"})
    with urllib.request.urlopen(request, timeout=settings["request_timeout_s"]) as response:
        message = json.load(response)["choices"][0]["message"]
    text = (message.get("content") or message.get("reasoning") or "").strip()
    if not text:
        raise ValueError("empty content (model may have spent the budget on reasoning)")
    return text


def safe_call(model: str, prompt: str, config: dict) -> CallResult:
    """The single boundary that turns a raised exception into a typed result."""
    try:
        return CallResult(ok=True, text=call_model(model, prompt, config), error="")
    except (urllib.error.HTTPError, urllib.error.URLError, ValueError, KeyError) as exc:
        return CallResult(ok=False, text="", error=str(exc)[:160])


def read_json(path: str) -> dict:
    with open(path) as handle:
        return json.load(handle)


def write_text(path: str, text: str) -> None:
    with open(path, "w") as handle:
        handle.write(text)


def load_intheweights(directory: str) -> dict:
    path = os.path.join(directory, "intheweights.json")
    return read_json(path) if os.path.exists(path) else {}


def load_runs(runs_dir: str) -> list:
    files = sorted(f for f in os.listdir(runs_dir) if f.endswith(".json"))
    return [read_json(os.path.join(runs_dir, f)) for f in files]


def now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------- #
# Edge orchestration: drives the boundary, hands data to the pure core.
# --------------------------------------------------------------------------- #
def grade_answer(name: str, truth: str, answer: CallResult, config: dict) -> str:
    if not answer["ok"]:
        return "ERROR"
    if is_unknown(answer["text"]):
        return "UNKNOWN"
    verdict = safe_call(config["grader_model"], grade_prompt(name, truth, answer["text"]), config)
    return "ERROR" if not verdict["ok"] else normalize_grade(verdict["text"])


def probe_cell(name: str, truth: str, model: str, config: dict) -> Cell:
    pause = config["settings"]["sleep_between_calls_s"]
    answer = safe_call(model, recall_prompt(name), config)
    time.sleep(pause)
    grade = grade_answer(name, truth, answer, config)
    time.sleep(pause)
    return Cell(answer=answer["text"] if answer["ok"] else f"(error: {answer['error']})", grade=grade)


def probe_entity(entity: dict, config: dict) -> Stats:
    per_model = {model: probe_cell(entity["name"], entity["ground_truth"], model, config)
                 for model in config["models"]}
    return summarize(entity.get("priority", ""), per_model)


def main(argv: list) -> None:
    here = os.path.dirname(os.path.abspath(__file__))
    runs_dir = os.path.join(here, "runs")
    os.makedirs(runs_dir, exist_ok=True)

    config = read_json(os.path.join(here, "config.json"))
    config["api_key"] = os.environ.get(config["provider"]["api_key_env"])
    if not config["api_key"]:
        raise SystemExit(f"Missing API key: set {config['provider']['api_key_env']} in the environment.")

    if "--report" in argv:
        runs = load_runs(runs_dir)
        if not runs:
            raise SystemExit("No runs yet; run the panel first.")
        report = render_report(runs[-1], runs[-2] if len(runs) > 1 else None, load_intheweights(here))
        write_text(os.path.join(here, "report.md"), report)
        print(f"Re-rendered report.md from {runs[-1]['timestamp']}")
        return

    prior_runs = load_runs(runs_dir)
    entities = select_entities(argv, config["entities"])
    run = {
        "timestamp": now_stamp(),
        "models": config["models"],
        "results": {e["name"]: probe_entity(e, config) for e in entities},
    }
    write_text(os.path.join(runs_dir, run["timestamp"].replace(":", "") + ".json"),
               json.dumps(run, indent=2))
    report = render_report(run, prior_runs[-1] if prior_runs else None, load_intheweights(here))
    write_text(os.path.join(here, "report.md"), report)
    print(f"weights-watch run {run['timestamp']} written; report at {os.path.join(here, 'report.md')}")


if __name__ == "__main__":
    main(sys.argv[1:])
