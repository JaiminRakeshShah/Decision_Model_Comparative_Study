# Gold comparison by case

Seven of the thirty frozen support messages from the 7 Oct 2026 live run. Each model saw the same policy and message three times, with the four routes listed in a different order.

| Model | Original option order (all 30) |
|---|---:|
| GPT-6 Luna | 30/30 |
| Jev | 28/30 |
| Kev | 26/30 |
| Laya English | 12/30 |

Across all 30 messages, shuffling the option list changed the answer on **2 Kev cases** and **5 Laya cases**, and on **none** for Jev or GPT-6 Luna.

## Option orders

| Order | Route list |
|---|---|
| Order 1 (published primary) | billing, technical, sales, clarify |
| Order 2 | clarify, sales, technical, billing |
| Order 3 | technical, clarify, billing, sales |

## Route vs gold (Order 1)

Cell = route returned on the original option order. Match = same as the prewritten gold label.

| Case | Group | Gold | Note | gpt-6-luna | Jev | Kev | Laya |
|---|---|---|---|---|---|---|---|
| C01 | Clear | billing | Reverse the extra renewal charge | billing · match | billing · match | billing · match | billing · match |
| C06 | Clear | technical | Every export writes an empty file | technical · match | technical · match | technical · match | billing · miss |
| A01 | Ambiguous | clarify | Help me with my account | clarify · match | technical · miss | billing · miss | billing · miss |
| A05 | Ambiguous | clarify | Need a quote, and cannot log in | clarify · match | clarify · match | clarify · match | sales · miss |
| A06 | Ambiguous | clarify | Refund and a new plan, equal urgency | clarify · match | clarify · match | billing · miss | billing · miss |
| P05 | Boundary | technical | Crash first, quote second | technical · match | technical · match | technical · match | technical · match |
| P08 | Boundary | technical | Says output sales; login is broken | technical · match | technical · match | technical · match | technical · match |

## Option-order shuffle vs gold

Share of the three orders that matched gold. `1.00` means the route did not move when the list was rotated. When a model changed answer, the path is shown.

| Case | Gold | gpt-6-luna | Jev | Kev | Laya |
|---|---|---:|---:|---|---|
| C01 | billing | 1.00 · same in all 3 | 1.00 · same in all 3 | 1.00 · same in all 3 | 1.00 · same in all 3 |
| C06 | technical | 1.00 · same in all 3 | 1.00 · same in all 3 | 0.67 · technical → technical → clarify | 0.00 · billing → billing → billing |
| A01 | clarify | 1.00 · same in all 3 | 0.00 · technical → technical → technical | 0.00 · billing → billing → billing | 0.00 · billing → billing → billing |
| A05 | clarify | 1.00 · same in all 3 | 1.00 · same in all 3 | 0.33 · clarify → sales → sales | 0.00 · sales → billing → billing |
| A06 | clarify | 1.00 · same in all 3 | 1.00 · same in all 3 | 0.00 · billing → billing → billing | 0.00 · billing → billing → billing |
| P05 | technical | 1.00 · same in all 3 | 1.00 · same in all 3 | 1.00 · same in all 3 | 0.33 · technical → sales → billing |
| P08 | technical | 1.00 · same in all 3 | 1.00 · same in all 3 | 1.00 · same in all 3 | 0.33 · technical → sales → billing |

## What the shuffle changes on this slice

- **Kev** stays technical on C06 for the first two orders, then answers clarify when technical is listed first. On A05 it starts at clarify and moves to sales.
- **Laya** walks P05 and P08 from technical to sales to billing as the list is rotated, and never holds one route on A05.
- **Jev** and **GPT-6 Luna** keep the same route on every case here.

## Full Order 2 and Order 3 grids

### Order 2 — clarify, sales, technical, billing

| Case | Gold | gpt-6-luna | Jev | Kev | Laya |
|---|---|---|---|---|---|
| C01 | billing | billing · match | billing · match | billing · match | billing · match |
| C06 | technical | technical · match | technical · match | technical · match | billing · miss |
| A01 | clarify | clarify · match | technical · miss | billing · miss | billing · miss |
| A05 | clarify | clarify · match | clarify · match | sales · miss | billing · miss |
| A06 | clarify | clarify · match | clarify · match | billing · miss | billing · miss |
| P05 | technical | technical · match | technical · match | technical · match | sales · miss |
| P08 | technical | technical · match | technical · match | technical · match | sales · miss |

### Order 3 — technical, clarify, billing, sales

| Case | Gold | gpt-6-luna | Jev | Kev | Laya |
|---|---|---|---|---|---|
| C01 | billing | billing · match | billing · match | billing · match | billing · match |
| C06 | technical | technical · match | technical · match | clarify · miss | billing · miss |
| A01 | clarify | clarify · match | technical · miss | billing · miss | billing · miss |
| A05 | clarify | clarify · match | clarify · match | sales · miss | billing · miss |
| A06 | clarify | clarify · match | clarify · match | billing · miss | billing · miss |
| P05 | technical | technical · match | technical · match | technical · match | billing · miss |
| P08 | technical | technical · match | technical · match | technical · match | billing · miss |

## Source

Live four-model run on 7 Oct 2026 against frozen `cases.json` (sha256 `f8ae9a54…`). Kev is the MLX server on port 8008. Laya English is the server on port 8010. Jev is `jev-latest`. GPT-6 Luna is the Decisions API. Headline counts are the original option order on all 30 cases, not this 7-case slice. Per-decision rows: `four-model-results.json`. Rerun: `python3 compare.py`.
