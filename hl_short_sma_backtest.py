"""
Hyperliquid Indexed Momentum Short Strategy - Backtest
======================================================

Universe: a user-supplied basket of high-FDV alts (see COIN_LIST below).
The script first queries Hyperliquid's live perp universe and reports which
of those tickers are actually tradeable, skipping the rest automatically.

Strategy:
    - Daily candles.
    - SHORT a coin when its daily close is BELOW its 30-day SMA.
    - CLOSE the short when its daily close is back ABOVE the 30-day SMA.
    - Max 5 concurrent positions.
    - Each position: 20% of current equity as MARGIN at 5x leverage
      => notional per position = 100% of equity
      => 5 positions filled = 5x notional on the whole portfolio.
    - If more than 5 coins signal, rank and take the top 5 (default:
      deepest below its SMA, i.e. strongest downtrend).

Starting equity: $1,000.

RISK NOTE (this is the whole ballgame at 5x):
    With all five slots filled you are 5x notional. A 20% average adverse
    move across positions is a full account wipe. A single coin squeezing
    ~20% liquidates that position and costs the full 20% margin - a fifth
    of the portfolio from one name. Alt short squeezes are correlated: they
    tend to rip together, so the five positions are NOT independent bets.
    Liquidation is modelled below (using each day's HIGH against the entry
    price) precisely so this shows up in the results instead of being
    smoothed away by close-to-close mark-to-market.

METHODOLOGY WARNINGS (read before believing any number):
    1. SELECTION BIAS. This coin list was chosen with hindsight - these are
       names already known for having bled. Backtesting "short these" over
       the period that made them famous will look good almost regardless of
       whether the SMA rule adds anything. That is why the script also
       reports an ALWAYS-SHORT benchmark on the same basket. If the SMA
       timing does not beat always-short, the timing is not doing the work
       and you have just re-discovered that these coins went down.
    2. SHORT HISTORY. Most of these listed recently. The 30-day SMA consumes
       the first 30 days of each coin's life. Per-coin history length is
       printed so you can see what you are actually testing on.
    3. FUNDING IS NOT MODELLED. For a short held over days this matters a
       lot and cuts both ways: shorts receive funding when it is positive
       (common on alt perps in risk-on phases) and pay when negative.
    4. NO SURVIVORSHIP CORRECTION. Delisted/dead tickers that would have
       been in a genuine "high FDV alt" universe at the time are absent.
    5. IN-SAMPLE. The 30-day SMA and the 5-position cap were not validated
       out-of-sample. Split the data before trusting the headline figure.

Usage:
    pip install requests pandas numpy matplotlib

    # just check which tickers Hyperliquid actually lists:
    python hl_short_sma_backtest.py --check-only

    # run the backtest:
    python hl_short_sma_backtest.py --days 365

Outputs:
    short_sma_equity_curve.csv  - daily equity, positions held, drawdown
    short_sma_trades.csv        - every trade with entry/exit/PnL/liquidation
    short_sma_equity.png        - equity curve vs benchmarks
    short_sma_coverage.csv      - which tickers were available + history length
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


# --------------------------------------------------------------------------
# Data
# --------------------------------------------------------------------------

def fetch_perp_universe() -> list:
    """Return the list of perp names currently listed on Hyperliquid."""
    resp = requests.post(HL_INFO_URL, json={"type": "meta"}, timeout=30)
    resp.raise_for_status()
    meta = resp.json()
    return [a["name"] for a in meta.get("universe", [])]


def fetch_candles(coin: str, interval: str, start_ms: int, end_ms: int) -> list:
    """Paginate through candleSnapshot (5000-candle cap per call)."""
    out, cursor = [], start_ms
    while cursor < end_ms:
        body = {
            "type": "candleSnapshot",
            "req": {"coin": coin, "interval": interval,
                    "startTime": cursor, "endTime": end_ms},
        }
        try:
            resp = requests.post(HL_INFO_URL, json=body, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            print(f"  ! {coin}: fetch error ({exc})", file=sys.stderr)
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


def candles_to_df(candles: list) -> pd.DataFrame:
    df = pd.DataFrame(candles)
    df["date"] = pd.to_datetime(df["t"], unit="ms").dt.normalize()
    df = df.rename(columns={"o": "open", "h": "high", "l": "low", "c": "close"})
    for c in ["open", "high", "low", "close"]:
        df[c] = df[c].astype(float)
    df = df.sort_values("date").drop_duplicates("date").reset_index(drop=True)
    return df[["date", "open", "high", "low", "close"]]


# --------------------------------------------------------------------------
# Backtest
# --------------------------------------------------------------------------

class Position:
    __slots__ = ("coin", "entry_price", "notional", "margin", "entry_date")

    def __init__(self, coin, entry_price, notional, margin, entry_date):
        self.coin = coin
        self.entry_price = entry_price
        self.notional = notional
        self.margin = margin
        self.entry_date = entry_date

    def unrealized(self, price: float) -> float:
        """Short PnL in USD."""
        return self.notional * (self.entry_price - price) / self.entry_price


def run_backtest(panel: dict, dates, args):
    """
    panel: {coin: DataFrame indexed by date with close/high/sma columns}
    Returns (equity_df, trades_df).
    """
    cash = args.starting_equity
    positions = {}
    trades = []
    rows = []
    fee_rate = (args.fee_bps + args.slippage_bps) / 10000.0
    liq_move = args.liq_threshold_pct / 100.0
    bankrupt = False

    for date in dates:
        # ---- 1. mark existing positions, check liquidation then exit signal
        for coin in list(positions):
            pos = positions[coin]
            row = panel[coin].get(date)
            if row is None:
                continue
            high, close, sma = row["high"], row["close"], row["sma"]

            # liquidation: adverse (upward) move vs entry, using the day's high
            adverse = (high - pos.entry_price) / pos.entry_price
            if adverse >= liq_move:
                cash -= pos.margin
                trades.append({
                    "coin": coin, "entry_date": pos.entry_date, "exit_date": date,
                    "entry_price": pos.entry_price,
                    "exit_price": pos.entry_price * (1 + liq_move),
                    "notional": pos.notional, "pnl_usd": -pos.margin,
                    "return_on_margin_pct": -100.0, "outcome": "LIQUIDATED",
                })
                del positions[coin]
                continue

            # exit signal: back above the SMA
            if not np.isnan(sma) and close > sma:
                pnl = pos.unrealized(close)
                fee = pos.notional * fee_rate
                cash += pnl - fee
                trades.append({
                    "coin": coin, "entry_date": pos.entry_date, "exit_date": date,
                    "entry_price": pos.entry_price, "exit_price": close,
                    "notional": pos.notional, "pnl_usd": round(pnl - fee, 2),
                    "return_on_margin_pct": round((pnl - fee) / pos.margin * 100, 2),
                    "outcome": "closed",
                })
                del positions[coin]

        # ---- 2. current equity
        unreal = 0.0
        for coin, pos in positions.items():
            row = panel[coin].get(date)
            if row is not None:
                unreal += pos.unrealized(row["close"])
        equity = cash + unreal

        if equity <= 0 and not bankrupt:
            bankrupt = True
            print(f"\n*** ACCOUNT WIPED OUT on {date.date()} ***", file=sys.stderr)

        if bankrupt:
            rows.append({"date": date, "equity": 0.0, "n_positions": 0,
                         "cash": 0.0, "unrealized": 0.0})
            continue

        # ---- 3. new entries
        free_slots = args.max_positions - len(positions)
        if free_slots > 0:
            candidates = []
            for coin, series in panel.items():
                if coin in positions:
                    continue
                row = series.get(date)
                if row is None or np.isnan(row["sma"]):
                    continue
                if row["close"] < row["sma"]:
                    depth = row["close"] / row["sma"] - 1.0  # negative = deeper
                    candidates.append((depth, coin, row["close"]))

            reverse = args.rank == "shallowest"
            candidates.sort(key=lambda x: x[0], reverse=reverse)

            for _, coin, price in candidates[:free_slots]:
                margin = args.margin_pct / 100.0 * equity
                notional = margin * args.leverage
                fee = notional * fee_rate
                cash -= fee
                positions[coin] = Position(coin, price, notional, margin, date)

        rows.append({"date": date, "equity": round(equity, 2),
                     "n_positions": len(positions), "cash": round(cash, 2),
                     "unrealized": round(unreal, 2)})

    eq = pd.DataFrame(rows)
    eq["peak"] = eq["equity"].cummax()
    eq["drawdown_pct"] = (eq["equity"] / eq["peak"] - 1.0) * 100
    return eq, pd.DataFrame(trades)


def always_short_benchmark(panel: dict, dates, args):
    """Equal-weight, always-short the whole basket at 1x notional. Reference only."""
    equity = args.starting_equity
    out = []
    prev = {}
    for date in dates:
        rets = []
        for coin, series in panel.items():
            row = series.get(date)
            if row is None:
                continue
            p = row["close"]
            if coin in prev and prev[coin] > 0:
                rets.append(-(p / prev[coin] - 1.0))
            prev[coin] = p
        if rets:
            equity *= (1.0 + float(np.mean(rets)))
        out.append({"date": date, "always_short_equity": round(max(equity, 0.0), 2)})
    return pd.DataFrame(out)


def equal_weight_long_index(panel: dict, dates, args):
    """Equal-weight long the basket at 1x. The 'index' this is shorting."""
    equity = args.starting_equity
    out = []
    prev = {}
    for date in dates:
        rets = []
        for coin, series in panel.items():
            row = series.get(date)
            if row is None:
                continue
            p = row["close"]
            if coin in prev and prev[coin] > 0:
                rets.append(p / prev[coin] - 1.0)
            prev[coin] = p
        if rets:
            equity *= (1.0 + float(np.mean(rets)))
        out.append({"date": date, "long_index_equity": round(max(equity, 0.0), 2)})
    return pd.DataFrame(out)


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------

def summarise(eq: pd.DataFrame, trades: pd.DataFrame, args):
    final = eq["equity"].iloc[-1]
    total_ret = (final / args.starting_equity - 1.0) * 100
    daily = eq["equity"].pct_change().replace([np.inf, -np.inf], np.nan).dropna()
    sharpe = (daily.mean() / daily.std() * np.sqrt(365)) if daily.std() > 0 else 0.0
    max_dd = eq["drawdown_pct"].min()

    print("\n" + "=" * 62)
    print("STRATEGY RESULTS")
    print("=" * 62)
    print(f"Starting equity      : ${args.starting_equity:,.2f}")
    print(f"Final equity         : ${final:,.2f}")
    print(f"Total return         : {total_ret:+.2f}%")
    print(f"Sharpe (annualised)  : {sharpe:.2f}")
    print(f"Max drawdown         : {max_dd:.2f}%")
    print(f"Avg positions held   : {eq['n_positions'].mean():.2f} / {args.max_positions}")

    if len(trades):
        liqs = (trades["outcome"] == "LIQUIDATED").sum()
        wins = (trades["pnl_usd"] > 0).sum()
        print(f"\nTrades               : {len(trades)}")
        print(f"Winners              : {wins} ({wins / len(trades) * 100:.1f}%)")
        print(f"LIQUIDATIONS         : {liqs}"
              f"{'  <-- each one cost a full 20% of equity' if liqs else ''}")
        by_coin = (trades.groupby("coin")["pnl_usd"].sum()
                   .sort_values(ascending=False))
        print("\nBest 5 coins by PnL:")
        print(by_coin.head(5).to_string())
        print("\nWorst 5 coins by PnL:")
        print(by_coin.tail(5).to_string())
    else:
        print("\nNo trades generated.")


def plot(eq, bench_short, bench_long, out_path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(eq["date"], eq["equity"], label="SMA short strategy (5x)", linewidth=2)
    ax.plot(bench_short["date"], bench_short["always_short_equity"],
            label="Always short basket (1x)", alpha=0.75, linestyle="--")
    ax.plot(bench_long["date"], bench_long["long_index_equity"],
            label="Long basket index (1x)", alpha=0.6, linestyle=":")
    ax.axhline(1000, color="grey", linewidth=0.8, alpha=0.5)
    ax.set_title("Indexed momentum short - strategy vs benchmarks\n"
                 "(if it doesn't beat always-short, the SMA timing isn't the edge)")
    ax.set_xlabel("Date")
    ax.set_ylabel("Equity ($)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_path, dpi=140)
    plt.close(fig)


# --------------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(description="Hyperliquid indexed momentum short backtest")
    p.add_argument("--days", type=int, default=365)
    p.add_argument("--sma", type=int, default=30, help="SMA period in days")
    p.add_argument("--starting-equity", type=float, default=1000.0)
    p.add_argument("--leverage", type=float, default=5.0)
    p.add_argument("--margin-pct", type=float, default=20.0,
                   help="%% of equity used as margin per position")
    p.add_argument("--max-positions", type=int, default=5)
    p.add_argument("--liq-threshold-pct", type=float, default=18.0,
                   help="adverse %% move that liquidates (approx: 1/lev minus maintenance)")
    p.add_argument("--fee-bps", type=float, default=2.5)
    p.add_argument("--slippage-bps", type=float, default=2.0)
    p.add_argument("--rank", choices=["deepest", "shallowest"], default="deepest",
                   help="which signals to take when more than max-positions fire")
    p.add_argument("--check-only", action="store_true",
                   help="just report which tickers Hyperliquid lists, then exit")
    args = p.parse_args()

    # ---- availability check
    print("Querying Hyperliquid perp universe...")
    universe = set(fetch_perp_universe())
    print(f"Hyperliquid currently lists {len(universe)} perps.\n")

    available = [c for c in COIN_LIST if c in universe]
    missing = [c for c in COIN_LIST if c not in universe]

    print(f"AVAILABLE ({len(available)}/{len(COIN_LIST)}):")
    print("  " + ", ".join(available) if available else "  none")
    print(f"\nNOT LISTED ({len(missing)}):")
    print("  " + ", ".join(missing) if missing else "  none")

    if args.check_only:
        pd.DataFrame({"coin": COIN_LIST,
                      "available": [c in universe for c in COIN_LIST]}
                     ).to_csv("short_sma_coverage.csv", index=False)
        print("\nSaved -> short_sma_coverage.csv")
        return

    if not available:
        print("\nNothing tradeable in the list. Exiting.")
        return

    # ---- fetch daily candles
    end_ms = int(time.time() * 1000)
    start_ms = end_ms - args.days * 86400 * 1000
    print(f"\nFetching daily candles ({args.days}d lookback) for {len(available)} coins...")

    panel, coverage = {}, []
    for coin in available:
        candles = fetch_candles(coin, "1d", start_ms, end_ms)
        if not candles:
            coverage.append({"coin": coin, "available": True, "bars": 0, "usable": False})
            continue
        df = candles_to_df(candles)
        df["sma"] = df["close"].rolling(args.sma).mean()
        usable = len(df) > args.sma + 5
        coverage.append({"coin": coin, "available": True, "bars": len(df),
                         "first": df["date"].min().date(), "last": df["date"].max().date(),
                         "usable": usable})
        if usable:
            panel[coin] = {r["date"]: r for _, r in df.iterrows()}
        print(f"  {coin:<7} {len(df):>4} daily bars"
              f"{'' if usable else '   (too short for a 30d SMA - skipped)'}")

    cov_df = pd.DataFrame(coverage)
    for c in missing:
        cov_df = pd.concat([cov_df, pd.DataFrame([{"coin": c, "available": False,
                                                   "bars": 0, "usable": False}])])
    cov_df.to_csv("short_sma_coverage.csv", index=False)

    if not panel:
        print("\nNo coin has enough history for a 30-day SMA. Exiting.")
        return

    all_dates = sorted({d for s in panel.values() for d in s})
    print(f"\nBacktesting {len(panel)} coins over {len(all_dates)} days "
          f"({all_dates[0].date()} -> {all_dates[-1].date()})")

    eq, trades = run_backtest(panel, all_dates, args)
    bench_short = always_short_benchmark(panel, all_dates, args)
    bench_long = equal_weight_long_index(panel, all_dates, args)

    eq.to_csv("short_sma_equity_curve.csv", index=False)
    trades.to_csv("short_sma_trades.csv", index=False)
    plot(eq, bench_short, bench_long, "short_sma_equity.png")

    summarise(eq, trades, args)

    print("\n" + "-" * 62)
    print("BENCHMARKS (the comparison that actually matters)")
    print("-" * 62)
    bs = bench_short["always_short_equity"].iloc[-1]
    bl = bench_long["long_index_equity"].iloc[-1]
    print(f"Always short basket @1x : ${bs:,.2f} "
          f"({(bs / args.starting_equity - 1) * 100:+.2f}%)")
    print(f"Long basket index  @1x  : ${bl:,.2f} "
          f"({(bl / args.starting_equity - 1) * 100:+.2f}%)")
    print("\nIf the strategy doesn't clearly beat always-short after accounting")
    print("for its 5x leverage, the SMA rule is adding nothing - you've only")
    print("confirmed that a hand-picked list of alts went down.")

    print("\nSaved -> short_sma_equity_curve.csv, short_sma_trades.csv, "
          "short_sma_equity.png, short_sma_coverage.csv")


if __name__ == "__main__":
    main()
