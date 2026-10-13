#!/usr/bin/env python3
"""Score the frozen support-routing cases on every model listed in .env.

The published pair (results.json, analyze.py) stays a two-model record.
This script is a separate live run. It does not rewrite those files.

Models, from COMPARE_MODELS:

  jev-latest     System One at JEV_BASE_URL, key TYPESAFE_API_KEY
  kev-latest     System One at KEV_BASE_URL
  laya-english   System One at LAYA_BASE_URL; the wire model field is english
  gpt-6-luna     OpenAI Decisions API; choice and noul are translated

Usage:
  python3 compare.py
  python3 compare.py --case C01 --orders 0
"""

from __future__ import annotations

import argparse
import json
import os
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


ROOT = Path(__file__).resolve().parent
QUESTION = "Choose the support route using the policy in the state. Return one listed option."
WARMUP = "The spare monitor arm will not clamp onto the standing desk."


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def catalog() -> dict[str, dict]:
    return {
        "jev-latest": {
            "family": "systemone",
            "url": os.environ.get("JEV_BASE_URL", "https://api.typesafe.ai/v1/systemone"),
            "wire_model": "jev-latest",
            "api_key_env": "TYPESAFE_API_KEY",
        },
        "kev-latest": {
            "family": "systemone",
            "url": os.environ.get("KEV_BASE_URL", "http://127.0.0.1:8008/v1/systemone"),
            "wire_model": "kev-latest",
            "api_key_env": "",
        },
        "laya-english": {
            "family": "systemone",
            "url": os.environ.get("LAYA_BASE_URL", "http://127.0.0.1:8010/v1/systemone"),
            "wire_model": "english",
            "api_key_env": "",
        },
        "gpt-6-luna": {
            "family": "decisions",
            "url": os.environ.get("OPENAI_DECISIONS_URL", "https://api.openai.com/v1/decisions"),
            "wire_model": "gpt-6-luna",
            "api_key_env": "OPENAI_API_KEY",
        },
    }


def state_text(instructions: str, message: str) -> str:
    return f"Routing policy: {instructions}\n\nCustomer message: {message}"


def systemone_body(wire_model: str, state: str, criteria: dict[str, str]) -> dict:
    return {
        "model": wire_model,
        "state": state,
        "questions": {
            "route": {
                "type": "choice",
                "instructions": QUESTION,
                "criteria": criteria,
            }
        },
    }


def to_decisions(body: dict) -> dict:
    """Translate one System One request into an OpenAI Decisions request."""
    state = body["state"]
    if not isinstance(state, str):
        state = json.dumps(state)
    questions = []
    for name, question in body["questions"].items():
        kind = question["type"]
        instructions = question.get("instructions") or ""
        if kind == "choice":
            questions.append(
                {
                    "type": "choice",
                    "name": name,
                    "instructions": instructions,
                    "choices": [
                        {
                            "value": value,
                            "description": text if isinstance(text, str) else json.dumps(text),
                        }
                        for value, text in question["criteria"].items()
                    ],
                }
            )
        elif kind == "noul":
            questions.append({"type": "predicate", "name": name, "instructions": instructions})
        elif kind == "score":
            levels = question["criteria"]
            if isinstance(levels, dict):
                items = [
                    {"label": label, "description": text if isinstance(text, str) else json.dumps(text)}
                    for label, text in levels.items()
                ]
            else:
                items = [{"label": str(level)} for level in levels]
            questions.append(
                {"type": "score", "name": name, "instructions": instructions, "levels": items}
            )
        else:
            raise ValueError(f"unsupported question type: {kind}")
    return {"model": body["model"], "input": state, "questions": questions}


def probability_map(raw) -> dict[str, float]:
    if isinstance(raw, dict):
        return {str(key): float(value) for key, value in raw.items()}
    mapped = {}
    for item in raw or []:
        key = item.get("value", item.get("label"))
        mapped[str(key)] = float(item["probability"])
    return mapped


def read_choice(family: str, payload: dict) -> tuple[str, dict[str, float], int | None]:
    usage = payload.get("usage") or {}
    tokens = usage.get("input_tokens")
    tokens = int(tokens) if isinstance(tokens, int) else None
    if family == "systemone":
        answer = payload["answers"]["route"]
        return str(answer["choice"]), probability_map(answer.get("probabilities")), tokens
    answers = payload["answers"]
    if isinstance(answers, dict):
        answer = answers["route"]
    else:
        answer = next(item for item in answers if item.get("name") == "route")
    if answer.get("type") == "refusal":
        raise RuntimeError("model refused the route question")
    probabilities = probability_map(answer.get("probabilities"))
    choice = answer.get("choice")
    if choice is None and probabilities:
        choice = max(probabilities, key=probabilities.get)
    return str(choice), probabilities, tokens


def post_json(url: str, payload: dict, api_key: str, timeout: float) -> dict:
    data = json.dumps(payload).encode("utf-8")
    headers = {"content-type": "application/json", "accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    delay = 1.0
    last = "request failed"
    for attempt in range(4):
        request = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")[:400]
            last = f"HTTP {error.code}: {detail}"
            if error.code not in (429, 500, 502, 503, 504) or attempt == 3:
                raise RuntimeError(last) from error
        except urllib.error.URLError as error:
            last = str(error.reason)
            if attempt == 3:
                raise RuntimeError(last) from error
        time.sleep(delay)
        delay *= 2
    raise RuntimeError(last)


def ask(spec: dict, api_key: str, state: str, criteria: dict[str, str], timeout: float) -> dict:
    body = systemone_body(spec["wire_model"], state, criteria)
    outgoing = to_decisions(body) if spec["family"] == "decisions" else body
    started = time.perf_counter()
    payload = post_json(spec["url"], outgoing, api_key, timeout)
    elapsed_ms = (time.perf_counter() - started) * 1000
    choice, probabilities, tokens = read_choice(spec["family"], payload)
    return {
        "choice": choice,
        "probabilities": probabilities,
        "elapsed_ms": elapsed_ms,
        "tokens": tokens,
        "server_model": payload.get("model"),
    }


def selected_models(argument: str | None) -> list[str]:
    raw = argument or os.environ.get("COMPARE_MODELS", "")
    names = [part.strip() for part in raw.split(",") if part.strip()]
    known = catalog()
    unknown = [name for name in names if name not in known]
    if unknown or not names:
        raise SystemExit(
            "COMPARE_MODELS must list one or more of: " + ", ".join(known)
        )
    return names


def run_model(name: str, spec: dict, cases: dict, orders: list[int], timeout: float, warmup: bool) -> list[dict]:
    key_name = spec["api_key_env"]
    api_key = os.environ.get(key_name, "") if key_name else ""
    if key_name and not api_key:
        raise RuntimeError(f"{key_name} is empty")
    instructions = cases["instructions"]
    options = cases["options"]
    if warmup:
        criteria = {label: options[label] for label in cases["permutations"][0]}
        ask(spec, api_key, state_text(instructions, WARMUP), criteria, timeout)
    rows = []
    for case in cases["cases"]:
        for order_index in orders:
            order = cases["permutations"][order_index]
            criteria = {label: options[label] for label in order}
            result = ask(spec, api_key, state_text(instructions, case["state"]), criteria, timeout)
            choice = result["choice"]
            row = {
                "model": name,
                "id": case["id"],
                "group": case["group"],
                "state": case["state"],
                "expected": case["expected"],
                "order_index": order_index,
                "order": order,
                "choice": choice,
                "correct": choice == case["expected"],
                "probabilities": result["probabilities"],
                "elapsed_ms": result["elapsed_ms"],
                "tokens": result["tokens"],
                "server_model": result["server_model"],
            }
            rows.append(row)
            mark = "ok" if row["correct"] else "miss"
            print(f"{name} {case['id']} order {order_index} {choice} {mark} {row['elapsed_ms']:.0f}ms", flush=True)
    return rows


def summarize(rows: list[dict], orders: list[int], names: list[str] | None = None) -> dict:
    summary = {}
    order = names or list(dict.fromkeys(row["model"] for row in rows))
    for name in order:
        selected = [row for row in rows if row["model"] == name]
        if not selected:
            continue
        primary = [row for row in selected if row["order_index"] == orders[0]]
        by_group = {}
        for group in ("clear", "ambiguous", "boundary"):
            group_rows = [row for row in primary if row["group"] == group]
            by_group[group] = {
                "correct": sum(row["correct"] for row in group_rows),
                "n": len(group_rows),
            }
        ids = dict.fromkeys(row["id"] for row in selected)
        unstable = [
            case_id
            for case_id in ids
            if len({row["choice"] for row in selected if row["id"] == case_id}) > 1
        ]
        summary[name] = {
            "primary_correct": sum(row["correct"] for row in primary),
            "primary_n": len(primary),
            "primary_by_group": by_group,
            "all_orders_correct": sum(row["correct"] for row in selected),
            "all_orders_n": len(selected),
            "order_unstable_cases": len(unstable),
            "order_unstable_ids": unstable,
            "median_ms": _median(row["elapsed_ms"] for row in selected),
        }
    return summary


def _median(values) -> float | None:
    numbers = sorted(values)
    if not numbers:
        return None
    mid = len(numbers) // 2
    if len(numbers) % 2:
        return numbers[mid]
    return (numbers[mid - 1] + numbers[mid]) / 2


def print_table(summary: dict) -> None:
    names = list(summary)
    header = " | ".join(f"{name:>16}" for name in names)
    print("\nOriginal option order")
    print(f"{'group':<28} | {header}")
    for group, label in (
        ("clear", "Clear requests"),
        ("ambiguous", "Missing evidence or conflicting requests"),
        ("boundary", "Negation and policy boundaries"),
    ):
        cells = []
        for name in names:
            cell = summary[name]["primary_by_group"][group]
            cells.append(f"{cell['correct']}/{cell['n']}".rjust(16))
        print(f"{label:<28} | " + " | ".join(cells))
    totals = []
    for name in names:
        item = summary[name]
        totals.append(f"{item['primary_correct']}/{item['primary_n']}".rjust(16))
    print(f"{'Total':<28} | " + " | ".join(totals))
    across = []
    for name in names:
        item = summary[name]
        across.append(f"{item['all_orders_correct']}/{item['all_orders_n']}".rjust(16))
    print(f"{'All orders':<28} | " + " | ".join(across))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", help="Comma-separated model ids. Defaults to COMPARE_MODELS.")
    parser.add_argument("--case", help="Comma-separated case ids. Default: all 30.")
    parser.add_argument("--orders", default="0,1,2", help="Comma-separated permutation indexes.")
    parser.add_argument("--output", default="four-model-results.json")
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--no-warmup", action="store_true")
    args = parser.parse_args()

    load_env(ROOT / ".env")
    names = selected_models(args.models)
    specs = catalog()
    orders = [int(part) for part in args.orders.split(",") if part.strip()]
    cases = json.loads((ROOT / "cases.json").read_text(encoding="utf-8"))
    if args.case:
        wanted = {part.strip() for part in args.case.split(",") if part.strip()}
        cases = dict(cases)
        cases["cases"] = [case for case in cases["cases"] if case["id"] in wanted]
        missing = wanted - {case["id"] for case in cases["cases"]}
        if missing:
            raise SystemExit(f"unknown case ids: {', '.join(sorted(missing))}")

    rows: list[dict] = []
    failures: dict[str, str] = {}
    lock = threading.Lock()
    output = ROOT / args.output

    def work(name: str) -> tuple[str, list[dict] | None, str | None]:
        try:
            return name, run_model(name, specs[name], cases, orders, args.timeout, not args.no_warmup), None
        except Exception as error:  # noqa: BLE001 -- one model must not cancel the others
            return name, None, str(error)

    with ThreadPoolExecutor(max_workers=len(names)) as pool:
        futures = [pool.submit(work, name) for name in names]
        for future in as_completed(futures):
            name, model_rows, error = future.result()
            if error:
                failures[name] = error
                print(f"{name} FAILED: {error}", flush=True)
                continue
            with lock:
                rows.extend(model_rows or [])
                _write(output, rows, failures, orders, names)

    _write(output, rows, failures, orders, names)
    if rows:
        print_table(summarize(rows, orders, names))
        print(f"\nwrote {output.name}")
    if failures:
        raise SystemExit(2)


def _write(path: Path, rows: list[dict], failures: dict[str, str], orders: list[int], names: list[str]) -> None:
    import hashlib

    document = {
        "case_sha256": hashlib.sha256((ROOT / "cases.json").read_bytes()).hexdigest(),
        "instructions": QUESTION,
        "failures": failures,
        "results": rows,
        "summary": summarize(rows, orders, names) if rows else {},
    }
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
