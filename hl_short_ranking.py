"""
Hyperliquid Short-SMA Strategy - Per-Coin Ranking & Out-of-Sample Test
======================================================================

Runs the 30-day SMA short strategy three ways:

  1. ISOLATED   - every coin gets its own independent $10,000 account and
                  trades alone. This is the fair apples-to-apples ranking
                  that answers "which coins performed best".

  2. PORTFOLIO  - one $10,000 account trading ALL coins simultaneously,
                  equal-weighted across whatever is signalling that day,
                  with total notional capped at --portfolio-leverage.
                  (Sizing had to be redefined here: 38 coins at 20% margin
                  x5 each would be ~38x notional, i.e. instant liquidation.)

  3. OUT-OF-SAMPLE TEST - the one that actually matters. Ranks coins on the
                  first --split-pct of history, takes the top N, then measures
                  how that exact group performs in the held-out remainder.
                  Also reports the Spearman rank correlation between the two
                  periods' returns.

WHY TEST 3 EXISTS
-----------------
Picking the best 15 of 38 after seeing the results is selecting on the
outcome. Those 15 will look excellent by construction - that is arithmetic,
not evidence. The question is whether being a top performer in one period
predicts being one in the next. If the rank correlation is near zero, "trade
the best 15" is not a strategy, it is curve-fitting to noise, and the top-15
table from test 1 should be treated as a description of the past rather than
a shortlist for the future.

Strategy (unchanged):
    SHORT on daily close below the 30-day SMA.
    CLOSE when daily close returns above the 30-day SMA.
    Isolated sizing: 20% of equity as margin at 5x = 100% notional.
    Liquidation modelled against each day's HIGH vs entry price.

NOT MODELLED: funding (material for multi-day shorts, cuts both ways),
delisted coins (survivorship bias), and borrow/OI limits on thin alts.

Usage:
    pip install requests pandas numpy matplotlib scipy
    python hl_short_ranking.py --days 365 --top-n 15
"""

import argparse
import sys
import time

import numpy as np
import pandas as pd
import requests

HL_INFO_URL = "https://api.hyperliquid.xyz/info"

COIN_LIST = [
    "STBL", "TRUMP", "WLD", "WCT", "PROVE", "GRASS", "ZRO", "LINEA", "BERA",
    "PLUME", "HYPER", "KAITO", "YB", "EIGEN", "AVNT", "MYX", "ARKM", "USUAL",
    "F", "ETHFI", "WAL", "0G", "COAI", "STRK", "WLFI", "XPL", "IP", "DOLO",
    "ZORA", "FF", "ORDER", "JTO", "MERL", "MORPHO", "FIL", "SUI", "VVV", "DOT",
]


# ---------------------------------------------------------------- data

def fetch_perp_universe() -> list:
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


# ------------------------------------------------------- isolated engine

def backtest_single(df, args, start_date=None, end_date=None):
    """One coin, one independent account. Returns metrics dict."""
    d = df
    if start_date is not None:
        d = d[d["date"] >= start_date]
    if end_date is not None:
        d = d[d["date"] < end_date]
    d = d.dropna(subset=["sma"])
    if len(d) < 5:
        return None

    equity = args.starting_equity
    fee_rate = (args.fee_bps + args.slippage_bps) / 10000.0
    liq_move = args.liq_threshold_pct / 100.0

    entry_price = None
    margin = notional = 0.0
    curve, trades, liqs, wins = [], 0, 0, 0

    for _, row in d.iterrows():
        close, high, sma = row["close"], row["high"], row["sma"]

        if entry_price is not None:
            if (high - entry_price) / entry_price >= liq_move:
                equity -= margin
                entry_price = None
                trades += 1
                liqs += 1
            elif close > sma:
                pnl = notional * (entry_price - close) / entry_price
                fee = notional * fee_rate
                equity += pnl - fee
                if pnl - fee > 0:
                    wins += 1
                entry_price = None
                trades += 1

        if equity <= 0:
            equity = 0.0
            curve.append({"date": row["date"], "equity": 0.0})
            continue

        if entry_price is None and close < sma:
            margin = args.margin_pct / 100.0 * equity
            notional = margin * args.leverage
            equity -= notional * fee_rate
            entry_price = close

        mark = equity
        if entry_price is not None:
            mark = equity + notional * (entry_price - close) / entry_price
        curve.append({"date": row["date"], "equity": max(mark, 0.0)})

    cv = pd.DataFrame(curve)
    final = cv["equity"].iloc[-1]
    rets = cv["equity"].pct_change().replace([np.inf, -np.inf], np.nan).dropna()
    sharpe = (rets.mean() / rets.std() * np.sqrt(365)) if rets.std() > 0 else 0.0
    dd = ((cv["equity"] / cv["equity"].cummax()) - 1).min() * 100

    return {
        "final_equity": round(final, 2),
        "return_pct": round((final / args.starting_equity - 1) * 100, 2),
        "sharpe": round(sharpe, 2),
        "max_dd_pct": round(dd, 2),
        "trades": trades,
        "liquidations": liqs,
        "win_rate_pct": round(wins / trades * 100, 1) if trades else 0.0,
        "days": len(cv),
        "_curve": cv,
    }


# ------------------------------------------------------ portfolio engine

def backtest_portfolio(panel, dates, args):
    """One account, all coins at once, equal-weight across active signals."""
    equity = args.starting_equity
    fee_rate = (args.fee_bps + args.slippage_bps) / 10000.0
    liq_move = args.liq_threshold_pct / 100.0
    positions = {}
    rows, trades = [], []

    for date in dates:
        realised = 0.0
        for coin in list(positions):
            row = panel[coin].get(date)
            if row is None:
                continue
            entry, notional, margin = positions[coin]
            if (row["high"] - entry) / entry >= liq_move:
                realised -= margin
                trades.append({"coin": coin, "date": date, "pnl": -margin,
                               "outcome": "LIQUIDATED"})
                del positions[coin]
            elif row["close"] > row["sma"]:
                pnl = notional * (entry - row["close"]) / entry - notional * fee_rate
                realised += pnl
                trades.append({"coin": coin, "date": date, "pnl": round(pnl, 2),
                               "outcome": "closed"})
                del positions[coin]

        equity += realised
        unreal = 0.0
        for coin, (entry, notional, _) in positions.items():
            row = panel[coin].get(date)
            if row is not None:
                unreal += notional * (entry - row["close"]) / entry
        mark = equity + unreal

        if mark <= 0:
            rows.append({"date": date, "equity": 0.0, "n_positions": 0})
            positions.clear()
            equity = 0.0
            continue

        signals = [c for c, s in panel.items()
                   if c not in positions and (r := s.get(date)) is not None
                   and not np.isnan(r["sma"]) and r["close"] < r["sma"]]
        target_n = len(positions) + len(signals)
        if target_n:
            per_notional = (mark * args.portfolio_leverage) / target_n
            for coin in signals:
                price = panel[coin][date]["close"]
                equity -= per_notional * fee_rate
                positions[coin] = (price, per_notional,
                                   per_notional / args.leverage)

        rows.append({"date": date, "equity": round(mark, 2),
                     "n_positions": len(positions)})

    return pd.DataFrame(rows), pd.DataFrame(trades)


# ------------------------------------------------------------- reporting

def spearman(a, b):
    ra = pd.Series(a).rank()
    rb = pd.Series(b).rank()
    if ra.std() == 0 or rb.std() == 0:
        return 0.0
    return float(np.corrcoef(ra, rb)[0, 1])


def plot_all(iso_df, port_eq, out_path, top_n):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10))

    top = iso_df.head(top_n)
    colours = ["tab:green" if v > 0 else "tab:red" for v in top["return_pct"]]
    ax1.barh(top["coin"][::-1], top["return_pct"][::-1], color=colours[::-1])
    ax1.axvline(0, color="grey", linewidth=0.8)
    ax1.set_title(f"Top {top_n} coins - isolated $10k accounts, return %\n"
                  "(selected after the fact - see out-of-sample test before trusting)")
    ax1.set_xlabel("Return %")

    ax2.plot(port_eq["date"], port_eq["equity"], linewidth=2,
             label="All-coin portfolio")
    ax2.axhline(10000, color="grey", linewidth=0.8, alpha=0.6)
    ax2.set_title("Portfolio mode - single $10k account, all coins simultaneously")
    ax2.set_ylabel("Equity ($)")
    ax2.legend()

    fig.tight_layout()
    fig.savefig(out_path, dpi=140)
    plt.close(fig)


# ------------------------------------------------------------------ main

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=365)
    p.add_argument("--sma", type=int, default=30)
    p.add_argument("--starting-equity", type=float, default=10000.0)
    p.add_argument("--leverage", type=float, default=5.0)
    p.add_argument("--margin-pct", type=float, default=20.0)
    p.add_argument("--portfolio-leverage", type=float, default=5.0,
                   help="total notional cap in portfolio mode")
    p.add_argument("--liq-threshold-pct", type=float, default=18.0)
    p.add_argument("--fee-bps", type=float, default=2.5)
    p.add_argument("--slippage-bps", type=float, default=2.0)
    p.add_argument("--top-n", type=int, default=15)
    p.add_argument("--split-pct", type=float, default=60.0,
                   help="%% of history used to rank before out-of-sample test")
    args = p.parse_args()

    print("Querying Hyperliquid perp universe...")
    universe = set(fetch_perp_universe())
    available = [c for c in COIN_LIST if c in universe]
    missing = [c for c in COIN_LIST if c not in universe]
    print(f"Listed on Hyperliquid ({len(available)}/{len(COIN_LIST)}): "
          f"{', '.join(available)}")
    if missing:
        print(f"NOT listed ({len(missing)}): {', '.join(missing)}")

    end_ms = int(time.time() * 1000)
    start_ms = end_ms - args.days * 86400 * 1000
    print(f"\nFetching daily candles for {len(available)} coins...")

    frames = {}
    for coin in available:
        candles = fetch_candles(coin, "1d", start_ms, end_ms)
        if not candles:
            continue
        df = candles_to_df(candles, args.sma)
        if len(df) > args.sma + 10:
            frames[coin] = df
            print(f"  {coin:<7} {len(df):>4} bars")
        else:
            print(f"  {coin:<7} {len(df):>4} bars  (too short - skipped)")

    if not frames:
        print("\nNo usable data. Exiting.")
        return

    # ---- 1. isolated
    print("\nRunning isolated backtests ($10k each, one coin per account)...")
    iso_rows = []
    for coin, df in frames.items():
        res = backtest_single(df, args)
        if res:
            res.pop("_curve")
            iso_rows.append({"coin": coin, **res})
    iso_df = pd.DataFrame(iso_rows).sort_values("return_pct", ascending=False)
    iso_df = iso_df.reset_index(drop=True)
    iso_df.to_csv("ranking_isolated.csv", index=False)

    print("\n" + "=" * 78)
    print(f"TOP {args.top_n} COINS - isolated $10,000 accounts")
    print("=" * 78)
    print(iso_df.head(args.top_n).to_string(index=False))
    print("\nBottom 5:")
    print(iso_df.tail(5).to_string(index=False))

    profitable = (iso_df["return_pct"] > 0).sum()
    print(f"\nProfitable coins: {profitable}/{len(iso_df)}  |  "
          f"Median return: {iso_df['return_pct'].median():+.2f}%  |  "
          f"Total liquidations: {int(iso_df['liquidations'].sum())}")

    # ---- 2. portfolio
    print("\nRunning portfolio backtest (single $10k, all coins)...")
    panel = {c: {r["date"]: r for _, r in df.iterrows()} for c, df in frames.items()}
    all_dates = sorted({d for s in panel.values() for d in s})
    port_eq, port_trades = backtest_portfolio(panel, all_dates, args)
    port_eq.to_csv("portfolio_equity.csv", index=False)
    port_trades.to_csv("portfolio_trades.csv", index=False)

    pf = port_eq["equity"].iloc[-1]
    pdd = ((port_eq["equity"] / port_eq["equity"].cummax()) - 1).min() * 100
    print(f"  Final equity : ${pf:,.2f} "
          f"({(pf / args.starting_equity - 1) * 100:+.2f}%)")
    print(f"  Max drawdown : {pdd:.2f}%")
    if len(port_trades):
        nliq = (port_trades["outcome"] == "LIQUIDATED").sum()
        print(f"  Trades: {len(port_trades)}  |  Liquidations: {nliq}")

    # ---- 3. out-of-sample
    print("\n" + "=" * 78)
    print("OUT-OF-SAMPLE TEST - does past ranking predict future ranking?")
    print("=" * 78)

    split_idx = int(len(all_dates) * args.split_pct / 100.0)
    split_date = all_dates[split_idx]
    print(f"Ranking period : {all_dates[0].date()} -> {split_date.date()}")
    print(f"Test period    : {split_date.date()} -> {all_dates[-1].date()}\n")

    p1, p2 = {}, {}
    for coin, df in frames.items():
        a = backtest_single(df, args, end_date=split_date)
        b = backtest_single(df, args, start_date=split_date)
        if a and b:
            p1[coin] = a["return_pct"]
            p2[coin] = b["return_pct"]

    if len(p1) < 5:
        print("Not enough coins with data in both halves to run this test.")
    else:
        coins = list(p1)
        oos = pd.DataFrame({"coin": coins,
                            "period1_return_pct": [p1[c] for c in coins],
                            "period2_return_pct": [p2[c] for c in coins]})
        oos = oos.sort_values("period1_return_pct", ascending=False).reset_index(drop=True)
        oos["period1_rank"] = oos.index + 1
        oos["period2_rank"] = oos["period2_return_pct"].rank(ascending=False).astype(int)
        oos.to_csv("out_of_sample_test.csv", index=False)

        n = min(args.top_n, len(oos) // 2)
        picked = oos.head(n)
        rest = oos.tail(len(oos) - n)
        rho = spearman(oos["period1_return_pct"], oos["period2_return_pct"])

        print(oos.head(args.top_n).to_string(index=False))
        print(f"\nTop {n} from period 1, how they did in period 2 : "
              f"{picked['period2_return_pct'].mean():+.2f}% avg")
        print(f"Everyone else, period 2                        : "
              f"{rest['period2_return_pct'].mean():+.2f}% avg")
        print(f"Spearman rank correlation between periods      : {rho:+.3f}")

        print("\nVERDICT:")
        if rho > 0.4:
            print("  Reasonably strong persistence. Past winners did tend to keep")
            print("  winning. Worth investigating further - but confirm on more")
            print("  data before sizing up.")
        elif rho > 0.15:
            print("  Weak persistence. Some signal, but not much - well within what")
            print("  a small sample can produce by chance. Do not size on this alone.")
        else:
            print("  Essentially NO persistence. Which coins did best in period 1 told")
            print("  you nothing about period 2. The top-15 table above is a")
            print("  description of what already happened, not a shortlist to trade.")
            print("  Picking coins this way is fitting to noise.")

    plot_all(iso_df, port_eq, "ranking_summary.png", args.top_n)
    print("\nSaved -> ranking_isolated.csv, portfolio_equity.csv, "
          "portfolio_trades.csv,\n         out_of_sample_test.csv, ranking_summary.png")


if __name__ == "__main__":
    main()
