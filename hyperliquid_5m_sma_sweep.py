"""
Hyperliquid 15-Minute SMA Flip Strategy Backtester
===================================================

Same logic as the daily sma-bot, but on 15-minute candles, 1x long / 1x short,
sweeping SMA periods 40-140 to find where (if anywhere) an edge exists at
this timeframe.

Strategy:
    - price > SMA(period)  -> long at `long_lev`x
    - price < SMA(period)  -> short at `short_lev`x
    - position flips instantly on cross (no confirmation delay)

Data source: Hyperliquid public info API (no auth required for candles).
    POST https://api.hyperliquid.xyz/info
    {"type": "candleSnapshot", "req": {"coin": "BTC", "interval": "15m",
     "startTime": ms, "endTime": ms}}

Usage:
    pip install requests pandas numpy matplotlib
    python hyperliquid_5m_sma_sweep.py --days 180 --min-period 40 --max-period 140 --step 5

Output:
    sma_sweep_results.csv   - every period tested, ranked by Sharpe
    sma_sweep_curve.png     - return/Sharpe vs SMA period
    best_equity_curve.png   - equity curve of the top-ranked period vs buy & hold

IMPORTANT CAVEATS (read before trusting any number this spits out):
    - Funding rates are NOT included.
    - This is an in-sample sweep. Whatever period "wins" is, by construction,
      the period that was luckiest/best-fit on THIS exact data window.
      Split the data (e.g. first 70% to pick a period, last 30% to confirm
      it still works) before trusting any single number.
    - Fees/slippage are a flat per-flip cost in bps - tune --fee-bps to
      match your actual Hyperliquid taker fee tier + realistic slippage.
    - CHECK THE ACTUAL DATE RANGE PRINTED AT RUNTIME. Hyperliquid's public
      candleSnapshot endpoint does not necessarily retain --days worth of
      history at fine intervals; it will silently return less than requested
      rather than erroring. A short actual range vs. what you asked for means
      you're backtesting on far less data (and a narrower market regime) than
      you think.
"""

import argparse
import time
import sys
import requests
import pandas as pd
import numpy as np

HL_INFO_URL = "https://api.hyperliquid.xyz/info"


def bars_per_year(interval: str) -> float:
    """Annualization factor for Sharpe, based on candle interval."""
    unit = interval[-1]
    n = int(interval[:-1])
    minutes = n if unit == "m" else n * 60 if unit == "h" else n * 60 * 24
    return 365 * 24 * 60 / minutes


def fetch_candles(coin: str, interval: str, start_ms: int, end_ms: int) -> list:
    """Paginate through Hyperliquid's candleSnapshot endpoint (5000-candle cap per call)."""
    all_candles = []
    cursor = start_ms
    while cursor < end_ms:
        body = {
            "type": "candleSnapshot",
            "req": {"coin": coin, "interval": interval, "startTime": cursor, "endTime": end_ms},
        }
        resp = requests.post(HL_INFO_URL, json=body, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if not data:
            break
        all_candles.extend(data)
        last_t = data[-1]["t"]
        if last_t <= cursor:
            break
        cursor = last_t + 1
        time.sleep(0.15)  # be polite to the public endpoint
        if len(data) < 2:
            break
    return all_candles


def candles_to_df(candles: list) -> pd.DataFrame:
    if not candles:
        raise RuntimeError("No candles returned - check coin/interval/date range.")
    df = pd.DataFrame(candles)
    df["timestamp"] = pd.to_datetime(df["t"], unit="ms")
    df = df.rename(columns={"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"})
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].astype(float)
    df = df.sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)
    return df[["timestamp", "open", "high", "low", "close", "volume"]]


def backtest_sma(df: pd.DataFrame, period: int, interval: str, long_lev: float = 1.0,
                  short_lev: float = 1.0, fee_bps: float = 2.5,
                  slippage_bps: float = 1.0):
    close = df["close"].values
    n = len(close)
    sma = pd.Series(close).rolling(period).mean().values

    position = np.zeros(n)
    for i in range(period, n):
        position[i] = long_lev if close[i] > sma[i] else -short_lev

    cost = (fee_bps + slippage_bps) / 10000.0
    ret = np.zeros(n)
    equity = np.ones(n)
    trades = 0

    for i in range(period + 1, n):
        bar_ret = (close[i] / close[i - 1] - 1.0) * position[i - 1]
        if position[i - 1] != position[i - 2]:
            bar_ret -= cost
            trades += 1
        equity[i] = equity[i - 1] * (1.0 + bar_ret)
        ret[i] = bar_ret

    rets = pd.Series(ret[period + 1:])
    total_return_pct = (equity[-1] - 1.0) * 100
    sharpe = 0.0
    if rets.std() > 0:
        sharpe = (rets.mean() / rets.std()) * np.sqrt(bars_per_year(interval))
    running_max = np.maximum.accumulate(equity)
    drawdown = (equity - running_max) / running_max
    max_dd_pct = drawdown.min() * 100
    win_rate_pct = (rets > 0).mean() * 100 if len(rets) else 0.0

    result = {
        "period": period,
        "total_return_pct": round(total_return_pct, 2),
        "sharpe": round(sharpe, 3),
        "max_dd_pct": round(max_dd_pct, 2),
        "trades": trades,
        "win_rate_pct": round(win_rate_pct, 2),
        "final_equity": round(equity[-1], 4),
    }
    return result, equity


def buy_and_hold(df: pd.DataFrame) -> float:
    close = df["close"].values
    return (close[-1] / close[0] - 1.0) * 100


def sweep(df: pd.DataFrame, periods, interval: str, **kwargs):
    results = []
    equities = {}
    total = len(periods)
    for idx, p in enumerate(periods, 1):
        if p >= len(df) - 5:
            continue
        res, eq = backtest_sma(df, p, interval, **kwargs)
        results.append(res)
        equities[p] = eq
        if idx % 20 == 0 or idx == total:
            print(f"  tested {idx}/{total} periods...", file=sys.stderr)
    res_df = pd.DataFrame(results).sort_values("sharpe", ascending=False).reset_index(drop=True)
    return res_df, equities


def plot_results(res_df: pd.DataFrame, out_path: str):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax1 = plt.subplots(figsize=(11, 5))
    ax1.plot(res_df["period"], res_df["total_return_pct"], color="tab:blue", label="Return %")
    ax1.set_xlabel("SMA period (bars)")
    ax1.set_ylabel("Total return %", color="tab:blue")
    ax1.tick_params(axis="y", labelcolor="tab:blue")

    ax2 = ax1.twinx()
    ax2.plot(res_df["period"], res_df["sharpe"], color="tab:orange", alpha=0.6, label="Sharpe")
    ax2.set_ylabel("Sharpe (annualized)", color="tab:orange")
    ax2.tick_params(axis="y", labelcolor="tab:orange")

    plt.title("Return & Sharpe vs SMA period - flat/noisy = no real edge at this timeframe")
    fig.tight_layout()
    fig.savefig(out_path, dpi=140)
    plt.close(fig)


def plot_best_equity(df: pd.DataFrame, equities: dict, best_period: int, out_path: str):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    eq = equities[best_period]
    bh = df["close"].values / df["close"].values[0]

    plt.figure(figsize=(11, 5))
    plt.plot(df["timestamp"], eq, label=f"SMA({best_period}) strategy")
    plt.plot(df["timestamp"], bh, label="Buy & hold", alpha=0.7)
    plt.title(f"Equity curve - best SMA period ({best_period})")
    plt.xlabel("Time")
    plt.ylabel("Equity (starting = 1.0)")
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_path, dpi=140)
    plt.close()


def main():
    parser = argparse.ArgumentParser(description="Sweep SMA periods on Hyperliquid candles")
    parser.add_argument("--coin", default="BTC")
    parser.add_argument("--interval", default="15m")
    parser.add_argument("--days", type=int, default=180, help="lookback window in days")
    parser.add_argument("--min-period", type=int, default=40)
    parser.add_argument("--max-period", type=int, default=140)
    parser.add_argument("--step", type=int, default=5)
    parser.add_argument("--long-lev", type=float, default=1.0)
    parser.add_argument("--short-lev", type=float, default=1.0)
    parser.add_argument("--fee-bps", type=float, default=2.5, help="taker fee in bps per flip")
    parser.add_argument("--slippage-bps", type=float, default=1.0)
    parser.add_argument("--out-csv", default="sma_sweep_results.csv")
    parser.add_argument("--out-curve-png", default="sma_sweep_curve.png")
    parser.add_argument("--out-equity-png", default="best_equity_curve.png")
    args = parser.parse_args()

    end_ms = int(time.time() * 1000)
    start_ms = end_ms - args.days * 24 * 60 * 60 * 1000

    print(f"Fetching {args.coin} {args.interval} candles for the last {args.days} days...")
    candles = fetch_candles(args.coin, args.interval, start_ms, end_ms)
    df = candles_to_df(candles)
    actual_days = (df["timestamp"].max() - df["timestamp"].min()).total_seconds() / 86400
    print(f"Got {len(df)} candles: {df['timestamp'].min()} -> {df['timestamp'].max()}")
    if actual_days < args.days * 0.9:
        print(f"WARNING: requested {args.days} days but only got ~{actual_days:.1f} days of "
              f"history. Hyperliquid's public endpoint may not retain this interval that far "
              f"back - results below are based on a much smaller/narrower sample than requested.",
              file=sys.stderr)

    periods = list(range(args.min_period, args.max_period + 1, args.step))
    print(f"Sweeping {len(periods)} SMA periods from {args.min_period} to {args.max_period} "
          f"(step {args.step})...")

    res_df, equities = sweep(
        df, periods, args.interval,
        long_lev=args.long_lev, short_lev=args.short_lev,
        fee_bps=args.fee_bps, slippage_bps=args.slippage_bps,
    )
    res_df.to_csv(args.out_csv, index=False)

    bh_pct = buy_and_hold(df)
    print(f"\nBuy & hold over period: {bh_pct:.2f}%")
    print(f"Saved full sweep results -> {args.out_csv}")
    print("\nTop 10 by Sharpe:")
    print(res_df.head(10).to_string(index=False))

    if len(res_df):
        best_period = int(res_df.iloc[0]["period"])
        plot_results(res_df, args.out_curve_png)
        plot_best_equity(df, equities, best_period, args.out_equity_png)
        print(f"\nSaved sweep chart -> {args.out_curve_png}")
        print(f"Saved best-period equity curve -> {args.out_equity_png}")
        print(f"\nBest period by Sharpe: {best_period} "
              f"(remember: pick this via walk-forward, not just this single top row)")


if __name__ == "__main__":
    main()
