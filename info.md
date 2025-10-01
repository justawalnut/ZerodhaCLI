Got it, Mr. Walnut. I went through Insilico Terminal’s CLI docs and mapped every relevant command to what Zerodha’s Kite Connect API can/can’t do. Below is a decision-ready feasibility report, followed by a clean, copy-pasteable prompt you can hand to your app-builder agent.

---

# Can we build an Insilico-style CLI on Zerodha Kite?

## What Insilico CLI actually does (representative commands)

* **Simple ordering:** market/limit entries, “best” price, and “reduce” close-outs.
* **Stops:** dedicated stop commands (page exists in the set; simple examples are under “Ordering with Stops”).
* **Cancel:** nuke all or selectively (“cancel top/bottom/first N”, “cancel buys/sells”).
* **Close position:** `close`, `close <side>` etc..
* **Scale:** spray N limit orders across a price band.
* **Chase:** continually move a limit to follow the tape until filled/limit reached.
* **Swarm:** burst N child orders totalling a size (regular/irregular).
* **Hotkeys/UI control:** key-bindings are defined in the CLI; UI control is local to the terminal (DOM focus etc.),.
* **General/Nuke:** switch instruments, show balances, `max` size, and “nuke orders/positions”.

> The list above is pulled from Insilico’s CLI pages (Simple Ordering, Cancel, Close, Scale, Chase, Swarm, Hotkeys, UI Control, General) to ensure we model the right behaviors.

---

## What Kite Connect exposes (ground truth)

* **Order API:** place/modify/cancel; varieties = `regular`, `amo`, `co`, `iceberg`, `auction`. Order types = `MARKET`, `LIMIT`, `SL`, `SL-M`. Validities = `DAY`, `IOC`, `TTL`. Extras: market protection %, auto-slice above exchange freeze limits.
* **GTT (Good-Till-Triggered):** server-side triggers with **`single`** and **`two-leg (OCO)`** types; when triggered, Kite places the specified **LIMIT** order(s). Endpoints to create/modify/delete/list GTTs.
* **Positions/Portfolio & Margins:** fetch positions/holdings; margin & basket margin/charges calculators.
* **Streaming:** WebSocket (Kite Ticker) for live ticks and order updates (subscribe/unsubscribe, modes), with SDKs in Python/JS/Go.
* **Limits & guardrails:** 10 req/s general; **order placement** 10 req/s, **200 orders/min, 3000/day**; order-modification max **25** per order; quotes 1 req/s; historical 3 req/s.
* **Order auto-slicing:** Kite can auto-split large orders above exchange freeze limits.
* **Far-from-LTP rejection:** Zerodha blocks option limits 50%–150% away from LTP (exceptions and GTT workaround outlined).
* **Bracket orders:** BO is **discontinued** (since 2020 and still discontinued).

---

## Feature-by-feature feasibility

| Insilico CLI feature                                                | Zerodha API feasibility                    | How to implement (or why not)                                                                                                                                                                                                                          |
| ------------------------------------------------------------------- | ------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Market/Limit entries; “best”**                                    | **Yes**                                    | `POST /orders/regular` with `MARKET` or `LIMIT`. “Best” = market or limit at bid/ask from Ticker; enforce market-protection % if using `MARKET`.                                                                                                       |
| **Reduce / close portion**                                          | **Yes (client-side)**                      | No “reduce-only” flag. Compute net position via Positions and place opposite order for desired qty; for intraday, use `MIS` or relevant product.                                                                                                       |
| **Stop orders (SL, SL-M)**                                          | **Yes**                                    | Use `order_type=SL` with `price` + `trigger_price`, or `SL-M` with `trigger_price` only.                                                                                                                                                               |
| **Attach stop to entry in one shot (true OCO/BO)**                  | **Partially**                              | **BO is discontinued**; can’t send entry+TP+SL as one atomic order. Alternatives: (a) place entry, then place separate SL/TP orders; (b) use **GTT two-leg OCO** for delivery CNC **LIMIT** exits (not market), which triggers when either level hits. |
| **Cancel: all / buys / sells / top / bottom / first N**             | **Mostly yes (client-side orchestration)** | API supports cancel by **order_id**. Implement filters (by side/price/time) in CLI: fetch day’s orders and cancel the selected ids; no single endpoint for “cancel buys” etc..                                                                         |
| **Close position (full/side)**                                      | **Yes (client-side)**                      | Query `positions`, compute needed opposite qty, place `MARKET`/`LIMIT` to flatten.                                                                                                                                                                     |
| **Scale orders (ladder across prices)**                             | **Yes, with limits**                       | Place N `LIMIT` orders between two prices. Respect blocking on far-from-LTP for options and per-minute/day order caps; enable `autoslice` for large qty.                                                                                               |
| **Chase order** (continuously modify the resting limit towards LTP) | **Yes, with rate-limit discipline**        | Start with a `LIMIT`, then `PUT /orders/regular/:id` to bump price until filled or max distance/time. Obey 10 req/s overall and **≤25 modifications per order** hard limit.                                                                            |
| **Swarm order** (burst of many children)                            | **Yes, with rate caps**                    | Place many small orders quickly; throttle to 10 orders/s and 200/min, 3000/day.                                                                                                                                                                        |
| **TWAP/VWAP execution**                                             | **Yes (client-side algo)**                 | Slice parent into time buckets and place child orders; rely on modify/cancel APIs and Ticker stream for feedback.                                                                                                                                      |
| **Hotkeys**                                                         | **Yes (local)**                            | Pure CLI concern; bind to command strings (Insilico does this via CLI as well).                                                                                                                                                                        |
| **UI control**                                                      | **N/A (local)**                            | Insilico’s “ui control” is about their DOM; for a TUI/terminal app, provide local panels and focus/toggling (no broker dependency).                                                                                                                    |
| **Balances/Max size**                                               | **Yes**                                    | Use funds/margins/basket margins endpoints to compute max feasible qty and display `max` like Insilico.                                                                                                                                                |
| **Server-side OCO with long validity**                              | **Yes (GTT)**                              | Create **GTT two-leg** for CNC exposure; note: it places **LIMIT** child orders on trigger (no SL-M), and is not intraday “algo” at the exchange.                                                                                                      |
| **Bracket order (entry + linked TP/SL with trailing, intraday)**    | **No**                                     | Zerodha has **stopped BO**; cannot replicate as a single atomic order via API. Build a client-side surrogate (entry then place/manage two linked exits).                                                                                               |

### Operational constraints you must design around

* **Throughput caps:** 10 req/s general; **orders 10/s, 200/min, 3000/day;** modifications ≤25/order.
* **Market protection & auto-slicing:** respect market-protection for `MARKET`/`SL-M`; enable autoslice to cross exchange freeze limits.
* **Option LTP guardrails:** Zerodha rejects extreme limits (e.g., >150% above or <50% below LTP); for far targets use **GTT** instead.
* **Latency profile:** Kite Connect is explicitly **not for HFT/latency-critical** execution; design chase/swarm with modest cadence and backoffs.
* **Streaming:** use one Ticker connection for quotes/order updates; subscribe/unsubscribe as needed.

---

## Bottom line

* A **command-driven trading CLI with Insilico-like ergonomics is very feasible** on Kite Connect for NSE/BSE/NFO/CDS/MCX, **except**: (1) **true atomic BO** is unavailable, and (2) some Insilico behaviors (e.g., “reduce-only” flags, exchange-level algos) must be emulated client-side.
* **Chase/Scale/Swarm** are implementable as **client algos** using place/modify/cancel, **if** you throttle and stop before the 25-modification cap per order.
* **GTT single/two-leg** gives you durable server-side triggers (LIMIT orders only), useful for CNC and swing OCOs.

---

## Architecture & command mapping (recommended)

* **Core modules:**

  1. **Order Router** (place/modify/cancel, autoslice toggle, market-protection), 2) **Position Manager** (flatten/close-side), 3) **Algo Executors** (chase/scale/swarm/twap), 4) **GTT Manager** (single/OCO), 5) **Ticker** (WS feed + order updates), 6) **Rate-Limiter** (global 10 rps; orders 200/min; per-order mod ≤25), 7) **Risk** (max qty from margins/funds; LTP band checks).
* **CLI grammar:** mirror Insilico verbs, but implement locally:

  * `buy <size> [at <price>|best] [product MIS|CNC|NRML]` → POST order.
  * `sell ...` (same).
  * `stop <side> <size> at <trigger> [limit <price>|market]` → SL/SL-M.
  * `cancel [all|buys|sells|top N|bottom N|first N]` → list + selective DELETE.
  * `close [all|long|short] [best|limit <p>]` → compute from Positions + place order.
  * `scale <side> <size> into <count> from <p1> to <p2>` → M limit orders (throttled).
  * `chase <side> <size> [to <price|%|₹>]` → place then modify loop up to cap.
  * `swarm <side> <size> into <count> [irregular]` → burst N orders with pacing.
  * `gtt oco <symbol> up <p> down <p> qty <q>` → create two-leg GTT.
  * `max <symbol> [product]` → use margin/basket APis.
  * `bind ...` (hotkeys) → local config.

---

## Known gaps vs. Insilico

* **No BO / reduce-only flag / exchange-level algos.** Emulate with local logic + linked orders. BO remains discontinued.
* **GTT children are LIMIT only** (no SL-M). For guaranteed exit, fall back to regular SL-M instead of GTT when needed.
* **Option price-band checks** may block wide scale ladders; CLI should warn and suggest GTT for remote targets.
* **Throughput limits** constrain very fast swarms/chases; include back-offs and batching.

---

# Natural-language build prompt (for your application-builder AI)

> **Title:** Build “Kite CLI” — an Insilico-style trading terminal for Zerodha
> **Goal:** A cross-platform terminal CLI that replicates Insilico Terminal’s command ergonomics (simple order, stops, cancel, close, scale, chase, swarm, hotkeys) on **Zerodha Kite Connect** for NSE/BSE/NFO/CDS/MCX.
> **APIs:** Use official **Kite Connect v3** REST + WebSocket (**Kite Ticker**) for live quotes/order updates; **GTT** endpoints for single & OCO triggers.
> **Key requirements:**
>
> 1. **Order layer:** Support `MARKET`, `LIMIT`, `SL`, `SL-M`; products `CNC/MIS/NRML/MTF`; validities `DAY/IOC/TTL`; optional `market_protection` and `autoslice` flags. Return order_id and full order/trade history queries.
> 2. **Commands:**
>
>    * `buy|sell <size> [at <price>|best] [product ...]`
>    * `stop <side> <size> at <trigger> [limit <price>|market]`
>    * `cancel [all|buys|sells|top N|bottom N|first N]`
>    * `close [all|long|short] [best|limit <p>]`
>    * `scale <side> <size> into <count> from <p1> to <p2>`
>    * `chase <side> <size> [to <p|%|₹>]` (modify loop until filled/cancel/limit reached; **≤25 mods/order**)
>    * `swarm <side> <size> into <count> [irregular]`
>    * `gtt single <symbol> trigger <p> place <LIMIT ...>`; `gtt oco <symbol> up <p> down <p> place <LIMIT ...>`
>    * `max <symbol> [product]` (compute max qty via margins/basket)
>    * `bind` (hotkeys) and `config` (throttle, autoslice default, market-protection default).
> 3. **Ticker:** One WebSocket connection by default, reconnect logic, dynamic subscribe/unsubscribe, `full` mode for key symbols.
> 4. **Rate-limiting:** Global 10 req/s; **orders 10/s, 200/min, 3000/day**; quotes 1/s; historical 3/s; per-order modification ≤25. Implement token-bucket + back-off. On approaching caps, delay and show CLI warnings.
> 5. **Risk/Compliance:**
>
>    * Validate option **LTP bands**; if requested price violates, auto-offer **GTT** pathway (LIMIT only) or adjust ladder spacing.
>    * Warn that **BO is unavailable**; emulate with linked exit orders after entry.
>    * Respect **market-protection** for MARKET/SL-M exits.
> 6. **State & idempotency:** Maintain an order registry (tags) to correlate child orders/chases; resume safely after restart (re-pull orders/positions).
> 7. **UX:** Instant feedback with live P&L per instrument (from Positions), command hints, and dry-run mode (margin check + estimated charges).
> 8. **Tests:** Unit tests for parsers, simulators for chase/scale respecting caps; integration tests against Kite sandbox creds.
> 9. **Security:** OAuth handshake server, encrypted token storage, no secrets in CLI flags.
>    **Non-goals / limitations to document in help:** No true BO; GTT exits are LIMIT-only; the tool is not for HFT/ultra-low latency strategies.

---

## Quick callouts to avoid surprises

* **Atomic TP+SL+Entry:** Not possible; design the CLI to place an entry, then immediately place a **pair** of exit orders (TP LIMIT + SL-M/SL). If one fills, **cancel** the sibling.
* **Chase cadence:** Use a **minimum cadence** (e.g., 250–500 ms) and a **hard stop** at 20–22 modifications to avoid hitting the 25-mod cap; otherwise cancel+re-place a fresh order.
* **Large parent orders:** Prefer a single parent with `autoslice=true` to let Kite split across freeze limits automatically.

If you want, I can turn that build prompt into a fully-specified command grammar (BNF) and a skeleton package layout (Python/Go/Rust) with rate-limit middleware and a basic chase executor.

---

### Sources

* Insilico Terminal CLI docs: Simple Ordering; Cancel; Close; Scale; Chase; Swarm; Hotkeys; UI Control.
* Kite Connect: Orders (types/varieties/modify/cancel/auto-slice/market-protection); GTT single/ two-leg OCO; Positions/Portfolio; Margins/Basket; WebSocket streaming.
* Limits & guardrails: rate limits & order caps; far-from-LTP rejection; BO discontinued; Zerodha auto-slicing explainer; latency posture (not for HFT).

If you want me to also produce a minimal reference implementation (e.g., Python + `pykiteconnect`), I can ship a clean skeleton with the command parser and one or two algos (chase/scale) pre-wired.

