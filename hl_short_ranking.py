"""
Hyperliquid Short-SMA Strategy - Cross Margin, Top-8 Coin Basket
=================================================================

Universe: the 8 best-performing coins from the isolated ranking run
(ZORA, 0G, IP, TRUMP, AVNT, USUAL, WCT, DOT - dropped WLD, the 9th coin
pasted, as the weakest of the group; edit TOP8 below if that's wrong).

Sizing:
    - CROSS MARGIN: one shared equity pool across all positions, not
      isolated margin per position.
    - Each new short: margin = 16% of current equity, leverage = 3x
      => notional = 48% of equity per position.
    - Max 6 concurrent positions => max total notional = 6 x 48% = 288%
      (~2.9x total account leverage when fully loaded).
    - Max positions reached => new signals are simply skipped that day and
      re-checked daily; if a coin is still below its SMA when a slot frees
      up, it enters then. No explicit queue needed - this falls out of
      re-evaluating signals fresh each day. Skipped signals are logged.

CROSS MARGIN LIQUIDATION (the important bit):
    Under isolated margin, each position lives or dies on its own margin.
    Under cross margin, ALL open positions share one equity pool. The
    account gets liquidated (modelled here as: everything force-closed at
    once) when:

        account_equity  <=  sum(notional_i * maintenance_margin_rate)
                             for every open position i

    This means a single coin can move against you by a large amount and
    the account survives fine if other positions are flat/winning or if
    there's slack in the pool - which is exactly the point you raised:
    a position's own 50% adverse price move is NOT the same as a 50%
    portfolio loss under cross margin. So this script tracks two separate
    numbers per trade instead of collapsing them into one drawdown figure:

    1. price_move_pct       - how far THAT COIN's price moved against you,
                               in isolation. Tells you nothing on its own
                               about portfolio risk.
    2. worst_margin_ratio   - account equity / total maintenance margin
                               required, at the worst point while this
                               trade was open. This is shared across every
                               position simultaneously and is what actually
                               determines liquidation. 1.0 = liquidated.
                               Lower = closer to the edge.

    The account-wide worst moment across the whole backtest is reported
    separately, showing exactly which positions were open at the time.

    maintenance_margin_rate is an approximation (--maintenance-margin-pct,
    default 3% of notional) since Hyperliquid's real cross-margin engine
    does partial/dynamic liquidation, not a single all-or-nothing event.
    Treat this as a reasonable stress model, not an exact replica.

NOT MODELLED: funding, delisted-coin survivorship, partial liquidation.

Usage:
    pip install requests pandas numpy matplotlib
    python hl_short_top8_crossmargin.py --days 365
"""

import argparse
import sys
import time

import numpy as np
import pandas as pd
import requests

HL_INFO_URL = "https://api.hyperliquid.xyz/info"

# Top 8 by return from the isolated ranking run (WLD dropped as 9th/weakest)
TOP8 = ["ZORA", "0G", "IP", "TRUMP", "AVNT", "USUAL", "WCT", "DOT"]


# ---------------------------------------------------------------- data

def fetch_perp_universe():
    r = requests.post(HL_INFO_URL, json={"type": "meta"}, timeout=30)
    r.raise_for_status()
    return [a["name"] for a in r.json().get("universe", [])]


def fetch_candles(coin, interval, start_ms, end_ms):
    out, cursor = [], start_ms
    while cursor < end_ms:
        body = {"type": "candleSnapshot",
                "req": {"coin": coin, "interval": interval,
                        "startTime": cursor, "endTime": end_ms}}
        try:
            r = requests.post(HL_INFO_URL, json=body, timeout=30)
            r.raise_for_status()
            data = r.json()
        except Exception as exc:
            print(f"  ! {coin}: {exc}", file=sys.stderr)
            break
        if not data:
            break
        out.extend(data)
        last_t = data[-1]["t"]
        if last_t <= cursor or len(data) < 2:
            break
        cursor = last_t + 1
        time.sleep(0.12)
    return out


def candles_to_df(candles, sma_period):
    df = pd.DataFrame(candles)
    df["date"] = pd.to_datetime(df["t"], unit="ms").dt.normalize()
    df = df.rename(columns={"o": "open", "h": "high", "l": "low", "c": "close"})
    for c in ["open", "high", "low", "close"]:
        df[c] = df[c].astype(float)
    df = df.sort_values("date").drop_duplicates("date").reset_index(drop=True)
    df["sma"] = df["close"].rolling(sma_period).mean()
    return df[["date", "high", "low", "close", "sma"]]


# ------------------------------------------------------- cross-margin engine

class Pos:
    __slots__ = ("coin", "entry_price", "notional", "margin", "entry_date",
                 "worst_price_move_pct", "worst_margin_ratio")

    def __init__(self, coin, entry_price, notional, margin, entry_date):
        self.coin = coin
        self.entry_price = entry_price
        self.notional = notional
        self.margin = margin
        self.entry_date = entry_date
        self.worst_price_move_pct = 0.0   # largest adverse move seen (price only)
        self.worst_margin_ratio = np.inf  # lowest account margin ratio seen while open

    def unrealized(self, price):
        return self.notional * (self.entry_price - price) / self.entry_price


def run_cross_margin(panel, dates, args):
    cash = args.starting_equity
    positions = {}
    fee_rate = (args.fee_bps + args.slippage_bps) / 10000.0
    maint_rate = args.maintenance_margin_pct / 100.0

    rows, trades, skipped_log = [], [], []
    liquidation_events = []
    global_worst_ratio = np.inf
    global_worst_date = None
    global_worst_snapshot = None

    for date in dates:
        # ---- worst-case (intraday high) equity check for liquidation ----
        if positions:
            worst_unreal = sum(
                pos.notional * (pos.entry_price - panel[c][date]["high"]) / pos.entry_price
                for c, pos in positions.items() if date in panel[c]
            )
            worst_equity = cash + worst_unreal
            required_maint = sum(pos.notional * maint_rate for pos in positions.values())
            margin_ratio = worst_equity / required_maint if required_maint > 0 else np.inf

            if margin_ratio < global_worst_ratio:
                global_worst_ratio = margin_ratio
                global_worst_date = date
                global_worst_snapshot = [
                    {"coin": c,
                     "price_move_pct": round((panel[c][date]["high"] / pos.entry_price - 1) * 100, 2),
                     "notional": round(pos.notional, 2)}
                    for c, pos in positions.items() if date in panel[c]
                ]

            for c, pos in positions.items():
                if date not in panel[c]:
                    continue
                move = (panel[c][date]["high"] / pos.entry_price - 1) * 100
                pos.worst_price_move_pct = max(pos.worst_price_move_pct, move)
                pos.worst_margin_ratio = min(pos.worst_margin_ratio, margin_ratio)

            if margin_ratio <= 1.0:
                # account-wide liquidation: force-close everything at the worst mark
                for c, pos in positions.items():
                    exit_price = panel[c][date]["high"] if date in panel[c] else pos.entry_price
                    trades.append({
                        "coin": c, "entry_date": pos.entry_date, "exit_date": date,
                        "entry_price": pos.entry_price, "exit_price": exit_price,
                        "notional": round(pos.notional, 2),
                        "price_move_pct": round(pos.worst_price_move_pct, 2),
                        "worst_margin_ratio": round(pos.worst_margin_ratio, 3),
                        "outcome": "LIQUIDATED (account-wide)",
                    })
                liquidation_events.append({"date": date, "margin_ratio": round(margin_ratio, 3),
                                           "n_positions": len(positions)})
                cash = max(worst_equity, 0.0)
                positions = {}
                rows.append({"date": date, "equity": round(cash, 2), "n_positions": 0,
                            "margin_ratio": round(margin_ratio, 3)})
                continue

        # ---- normal exits (close back above SMA) ----
        for c in list(positions):
            row = panel[c].get(date)
            if row is None:
                continue
            pos = positions[c]
            if not np.isnan(row["sma"]) and row["close"] > row["sma"]:
                pnl = pos.unrealized(row["close"])
                fee = pos.notional * fee_rate
                cash += pnl - fee
                trades.append({
                    "coin": c, "entry_date": pos.entry_date, "exit_date": date,
                    "entry_price": pos.entry_price, "exit_price": row["close"],
                    "notional": round(pos.notional, 2), "pnl_usd": round(pnl - fee, 2),
                    "price_move_pct": round(pos.worst_price_move_pct, 2),
                    "worst_margin_ratio": round(pos.worst_margin_ratio, 3),
                    "outcome": "closed",
                })
                del positions[c]

        # ---- current mark ----
        unreal = sum(pos.unrealized(panel[c][date]["close"])
                    for c, pos in positions.items() if date in panel[c])
        equity = cash + unreal
        required_maint = sum(pos.notional * maint_rate for pos in positions.values())
        margin_ratio = equity / required_maint if required_maint > 0 else np.inf

        # ---- new entries (respecting the 6-position cap; skip & log if full) ----
        free_slots = args.max_positions - len(positions)
        if free_slots > 0:
            candidates = []
            for c, series in panel.items():
                if c in positions:
                    continue
                row = series.get(date)
                if row is None or np.isnan(row["sma"]):
                    continue
                if row["close"] < row["sma"]:
                    depth = row["close"] / row["sma"] - 1.0
                    candidates.append((depth, c, row["close"]))
            candidates.sort(key=lambda x: x[0])  # deepest below SMA first

            for depth, c, price in candidates[:free_slots]:
                margin = args.margin_pct / 100.0 * equity
                notional = margin * args.leverage
                cash -= notional * fee_rate
                positions[c] = Pos(c, price, notional, margin, date)

            turned_away = candidates[free_slots:]
            for depth, c, price in turned_away:
                skipped_log.append({"date": date, "coin": c,
                                    "reason": "max positions reached"})

        rows.append({"date": date, "equity": round(equity, 2),
                     "n_positions": len(positions),
                     "margin_ratio": round(margin_ratio, 3) if np.isfinite(margin_ratio) else None})

    eq = pd.DataFrame(rows)
    eq["peak"] = eq["equity"].cummax()
    eq["drawdown_pct"] = (eq["equity"] / eq["peak"] - 1.0) * 100
    return (eq, pd.DataFrame(trades), pd.DataFrame(skipped_log),
            pd.DataFrame(liquidation_events),
            {"ratio": global_worst_ratio, "date": global_worst_date,
             "snapshot": global_worst_snapshot})


# ------------------------------------------------------------- reporting

def plot(eq, out_path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 9), sharex=True)
    ax1.plot(eq["date"], eq["equity"], linewidth=2, color="tab:blue")
    ax1.axhline(eq["equity"].iloc[0], color="grey", linewidth=0.8, alpha=0.5)
    ax1.set_title("Cross-margin equity - top 8 basket, 6 max positions, 3x/16% sizing")
    ax1.set_ylabel("Equity ($)")

    mr = eq["margin_ratio"].astype(float)
    ax2.plot(eq["date"], mr, linewidth=1.5, color="tab:red")
    ax2.axhline(1.0, color="black", linewidth=1, linestyle="--", label="Liquidation")
    ax2.set_title("Account margin ratio (equity / maintenance required) - closer to 1.0 = closer to liquidation")
    ax2.set_ylabel("Margin ratio")
    ax2.set_xlabel("Date")
    ax2.legend()

    fig.tight_layout()
    fig.savefig(out_path, dpi=140)
    plt.close(fig)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=365)
    p.add_argument("--sma", type=int, default=30)
    p.add_argument("--starting-equity", type=float, default=10000.0)
    p.add_argument("--leverage", type=float, default=3.0)
    p.add_argument("--margin-pct", type=float, default=16.0)
    p.add_argument("--max-positions", type=int, default=6)
    p.add_argument("--maintenance-margin-pct", type=float, default=3.0,
                   help="approx maintenance margin as %% of notional per position")
    p.add_argument("--fee-bps", type=float, default=2.5)
    p.add_argument("--slippage-bps", type=float, default=2.0)
    args = p.parse_args()

    notional_per_pos = args.margin_pct / 100 * args.leverage * 100
    max_total_notional = notional_per_pos * args.max_positions
    print(f"Sizing: {args.margin_pct}% margin x {args.leverage}x = "
          f"{notional_per_pos:.0f}% notional per position")
    print(f"Max {args.max_positions} positions => up to {max_total_notional:.0f}% "
          f"total notional (~{max_total_notional/100:.2f}x account leverage when full)\n")

    print("Querying Hyperliquid perp universe...")
    universe = set(fetch_perp_universe())
    available = [c for c in TOP8 if c in universe]
    missing = [c for c in TOP8 if c not in universe]
    print(f"Available ({len(available)}/{len(TOP8)}): {', '.join(available)}")
    if missing:
        print(f"NOT listed: {', '.join(missing)}")

    end_ms = int(time.time() * 1000)
    start_ms = end_ms - args.days * 86400 * 1000
    print(f"\nFetching daily candles for {len(available)} coins...")

    frames = {}
    for c in available:
        candles = fetch_candles(c, "1d", start_ms, end_ms)
        if not candles:
            continue
        df = candles_to_df(candles, args.sma)
        if len(df) > args.sma + 5:
            frames[c] = df
            print(f"  {c:<6} {len(df):>4} bars")

    if not frames:
        print("No usable data. Exiting.")
        return

    panel = {c: {r["date"]: r for _, r in df.iterrows()} for c, df in frames.items()}
    all_dates = sorted({d for s in panel.values() for d in s})
    print(f"\nBacktesting {len(panel)} coins, {len(all_dates)} days "
          f"({all_dates[0].date()} -> {all_dates[-1].date()})\n")

    eq, trades, skipped, liqs, worst = run_cross_margin(panel, all_dates, args)

    eq.to_csv("crossmargin_equity.csv", index=False)
    trades.to_csv("crossmargin_trades.csv", index=False)
    skipped.to_csv("crossmargin_skipped_signals.csv", index=False)
    liqs.to_csv("crossmargin_liquidation_events.csv", index=False)
    plot(eq, "crossmargin_summary.png")

    final = eq["equity"].iloc[-1]
    total_ret = (final / args.starting_equity - 1) * 100
    daily = eq["equity"].pct_change().replace([np.inf, -np.inf], np.nan).dropna()
    sharpe = (daily.mean() / daily.std() * np.sqrt(365)) if daily.std() > 0 else 0.0

    print("=" * 70)
    print("CROSS-MARGIN PORTFOLIO RESULTS - top 8 basket")
    print("=" * 70)
    print(f"Starting equity : ${args.starting_equity:,.2f}")
    print(f"Final equity    : ${final:,.2f}")
    print(f"Total return    : {total_ret:+.2f}%")
    print(f"Sharpe          : {sharpe:.2f}")
    print(f"Account liquidation events: {len(liqs)}")
    if len(skipped):
        print(f"Signals turned away (max positions full): {len(skipped)} "
              f"across {skipped['date'].nunique()} days")

    if len(trades):
        closed = trades[trades["outcome"] == "closed"]
        print(f"\nTrades closed normally: {len(closed)}")
        if len(closed) and "pnl_usd" in closed:
            wins = (closed["pnl_usd"] > 0).sum()
            print(f"Win rate: {wins}/{len(closed)} ({wins/len(closed)*100:.1f}%)")

    print("\n" + "-" * 70)
    print("CLOSEST CALL - the account's single worst margin ratio in the backtest")
    print("-" * 70)
    if worst["date"] is not None:
        print(f"Date: {worst['date'].date()}   Margin ratio: {worst['ratio']:.3f}  "
              f"(1.0 = liquidation)")
        print("Positions open at that moment:")
        for s in worst["snapshot"]:
            print(f"  {s['coin']:<6} price moved {s['price_move_pct']:+.2f}% against entry, "
                  f"notional ${s['notional']:,.0f}")
        print("\nNote: no single coin's own price move above equals the portfolio's")
        print("loss - the margin ratio is what determines liquidation, and it reflects")
        print("the combined position, not any one coin in isolation.")
    else:
        print("Account never came close to liquidation (no positions ever opened, or "
              "margin ratio stayed comfortably above 1.0 throughout).")

    if len(trades):
        print("\n" + "-" * 70)
        print("TOP 10 TRADES BY CLOSEST BRUSH WITH LIQUIDATION (lowest margin ratio)")
        print("-" * 70)
        cols = ["coin", "entry_date", "exit_date", "price_move_pct",
                "worst_margin_ratio", "outcome"]
        print(trades.sort_values("worst_margin_ratio").head(10)[cols].to_string(index=False))

    print("\nSaved -> crossmargin_equity.csv, crossmargin_trades.csv, "
          "crossmargin_skipped_signals.csv,\n         crossmargin_liquidation_events.csv, "
          "crossmargin_summary.png")


if __name__ == "__main__":
    main()
