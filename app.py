"""
Day-Trading Decision Dashboard  —  PAPER MODE ONLY
==================================================
Decision support, risk management, and a SIMULATED (paper) trade journal.

This app does NOT connect to any brokerage, does NOT place live orders, and
CANNOT guarantee profits. All trades here are paper (pretend) trades for
practice and discipline. Free market data is typically delayed (~15 min).
Educational tool — not financial advice.

Run:  streamlit run app.py
"""

import re
import math
import datetime as dt
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    HAS_MPL = True
except Exception:
    HAS_MPL = False

try:
    import yfinance as yf
except Exception:  # pragma: no cover
    yf = None

# Canonical IANA timezone (US/Eastern is a deprecated alias that fails under
# Python 3.14 / pandas 3.x zoneinfo on minimal hosts like Streamlit Cloud).
# The `tzdata` package (see requirements.txt) provides the IANA database so this
# resolves everywhere, not just on machines with a system tz database.
ET = "America/New_York"

# --------------------------------------------------------------------------- #
# Local journal persistence (auto-saved to ./trades.csv)
# --------------------------------------------------------------------------- #
JOURNAL_PATH = Path("trades.csv")   # created in the folder you run the app from

JOURNAL_COLUMNS = [
    "exit_date", "ticker", "side", "shares", "entry", "stop", "target",
    "exit", "pnl", "R", "reason", "mistakes", "rules_broken",
    "red_override_reason", "soft_explanations", "score_at_open", "bias_at_open",
    "setup_type", "relvol_at_open", "atr_pct_at_open", "news_at_open",
    "check_entry", "check_stop", "check_target", "check_risk",
    "check_revenge", "check_red", "check_setup",
    "open_time", "exit_time",
]

# Curated columns for the on-screen journal table (CSV export keeps all of them)
DISPLAY_COLUMNS = [
    "exit_date", "ticker", "side", "shares", "entry", "stop", "target",
    "exit", "pnl", "R", "reason", "setup_type", "mistakes", "rules_broken",
    "red_override_reason", "soft_explanations", "score_at_open", "bias_at_open",
]

SETUP_TYPES = [
    "VWAP reclaim", "VWAP rejection", "Trend pullback", "Breakout",
    "Breakdown", "Reversal", "Range fade", "Opening-range breakout", "Other",
]

CHECKLIST_ITEMS = [
    ("check_entry", "I know my entry"),
    ("check_stop", "I know my stop loss"),
    ("check_target", "I know my target"),
    ("check_risk", "My risk is within limit"),
    ("check_revenge", "I am not revenge trading"),
    ("check_red", "I am not trading during a Red score unless I explain why"),
    ("check_setup", "This trade matches my written setup"),
]

MISTAKE_TAGS = [
    "revenge trade", "chased entry", "ignored red score",
    "moved stop", "oversized position", "no clear setup",
]


def load_journal() -> list:
    """Load closed paper trades from trades.csv (empty list if none/unreadable)."""
    if not JOURNAL_PATH.exists():
        return []
    try:
        df = pd.read_csv(JOURNAL_PATH)
    except Exception:
        return []
    if df.empty:
        return []
    for col in ("pnl", "R", "entry", "stop", "target", "exit"):
        if col in df:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "shares" in df:
        df["shares"] = pd.to_numeric(df["shares"], errors="coerce").fillna(0).astype(int)
    df = df.astype(object).where(pd.notna(df), "")
    return df.to_dict("records")


def save_journal(journal: list):
    """Write the full journal to trades.csv (or delete the file when empty)."""
    try:
        if journal:
            (pd.DataFrame(journal)
               .reindex(columns=JOURNAL_COLUMNS)
               .to_csv(JOURNAL_PATH, index=False))
        elif JOURNAL_PATH.exists():
            JOURNAL_PATH.unlink()
    except Exception as e:  # pragma: no cover
        st.warning(f"Could not save journal to {JOURNAL_PATH}: {e}")


def daily_stats(rows: list) -> dict | None:
    """Compute today's summary stats from a list of closed-trade dicts."""
    if not rows:
        return None
    pnls = [float(r["pnl"]) for r in rows]
    Rs = [float(r["R"]) for r in rows]
    wins = sum(1 for p in pnls if p > 0)
    n = len(rows)
    return {
        "trades": n,
        "win_rate": wins / n * 100,
        "total_pnl": sum(pnls),
        "avg_R": sum(Rs) / n,
        "biggest_win": max(pnls),
        "biggest_loss": min(pnls),
    }


# --------------------------------------------------------------------------- #
# Strategy-review analytics (pure functions over the journal)
# --------------------------------------------------------------------------- #
_STOPWORDS = {
    "the", "and", "for", "with", "into", "over", "under", "near", "off", "out",
    "was", "are", "had", "has", "but", "not", "this", "that", "then", "than",
    "above", "below", "after", "before", "high", "low", "from", "onto", "very",
    "trade", "long", "short", "entry", "exit", "stop", "target", "price",
}


def journal_df(journal: list) -> pd.DataFrame:
    """Normalize the journal into a DataFrame with helper columns."""
    if not journal:
        return pd.DataFrame()
    df = pd.DataFrame(journal).copy()
    for c in ["mistakes", "reason", "score_at_open", "ticker", "open_time",
              "exit_date", "rules_broken", "setup_type", "news_at_open",
              "bias_at_open"]:
        if c not in df.columns:
            df[c] = ""
        df[c] = df[c].fillna("").astype(str)
    for c in ["pnl", "R", "relvol_at_open", "atr_pct_at_open"]:
        if c not in df.columns:
            df[c] = np.nan if c.endswith("_open") else 0.0
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["pnl"] = df["pnl"].fillna(0.0)
    df["R"] = df["R"].fillna(0.0)
    df["win"] = df["pnl"] > 0
    df["mistakes_list"] = df["mistakes"].apply(
        lambda s: [t.strip() for t in str(s).split(";") if t.strip()])
    df["rules_list"] = df["rules_broken"].apply(
        lambda s: [t.strip() for t in str(s).split(";") if t.strip()])

    def _hour(x):
        try:
            return int(pd.to_datetime(x).hour)
        except Exception:
            return np.nan

    def _week(d):
        try:
            iso = pd.to_datetime(d).isocalendar()
            return f"{int(iso[0])}-W{int(iso[1]):02d}"
        except Exception:
            return "—"

    df["entry_hour"] = df["open_time"].apply(_hour)
    df["iso_week"] = df["exit_date"].apply(_week)
    return df


def by_score(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    g = df.groupby("score_at_open").agg(
        trades=("pnl", "size"), win_rate=("win", "mean"),
        avg_R=("R", "mean"), total_pnl=("pnl", "sum"))
    g["win_rate"] *= 100
    order = [s for s in ["Green", "Yellow", "Red"] if s in g.index]
    return g.reindex(order)


def by_mistake_tag(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    recs = []
    for _, row in df.iterrows():
        for t in row["mistakes_list"]:
            recs.append({"tag": t, "pnl": row["pnl"], "R": row["R"],
                         "win": row["win"]})
    if not recs:
        return pd.DataFrame()
    ex = pd.DataFrame(recs)
    g = ex.groupby("tag").agg(
        trades=("pnl", "size"), win_rate=("win", "mean"),
        avg_R=("R", "mean"), total_pnl=("pnl", "sum"))
    g["win_rate"] *= 100
    return g.sort_values("total_pnl")


def by_rules_broken(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    recs = []
    for _, row in df.iterrows():
        for t in row["rules_list"]:
            recs.append({"rule": t, "pnl": row["pnl"], "R": row["R"],
                         "win": row["win"]})
    if not recs:
        return pd.DataFrame()
    ex = pd.DataFrame(recs)
    g = ex.groupby("rule").agg(
        trades=("pnl", "size"), win_rate=("win", "mean"),
        avg_R=("R", "mean"), total_pnl=("pnl", "sum"))
    g["win_rate"] *= 100
    return g.sort_values("total_pnl")


def pnl_by_hour(df: pd.DataFrame) -> pd.Series:
    if df.empty:
        return pd.Series(dtype=float)
    return df.dropna(subset=["entry_hour"]).groupby("entry_hour")["pnl"].sum()


def best_worst_ticker(df: pd.DataFrame):
    if df.empty:
        return None
    g = df.groupby("ticker")["pnl"].sum().sort_values()
    return {"best": (g.index[-1], float(g.iloc[-1])),
            "worst": (g.index[0], float(g.iloc[0])), "series": g}


def reason_keyword_stats(df: pd.DataFrame, min_count: int = 2) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    recs = []
    for _, row in df.iterrows():
        words = set(w for w in re.findall(r"[a-zA-Z]+", str(row["reason"]).lower())
                    if len(w) > 2 and w not in _STOPWORDS)
        for w in words:
            recs.append({"kw": w, "pnl": row["pnl"], "win": row["win"]})
    if not recs:
        return pd.DataFrame()
    ex = pd.DataFrame(recs)
    g = ex.groupby("kw").agg(
        count=("pnl", "size"), total_pnl=("pnl", "sum"),
        avg_pnl=("pnl", "mean"), win_rate=("win", "mean"))
    g["win_rate"] *= 100
    g = g[g["count"] >= min_count]
    return g.sort_values("total_pnl")


def weekly_summary(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    rows = []
    for wk, sub in df.groupby("iso_week"):
        tags = [t for lst in sub["mistakes_list"] for t in lst]
        top = Counter(tags).most_common(1)[0][0] if tags else "—"
        rows.append({
            "week": wk, "trades": len(sub),
            "win_rate": round(sub["win"].mean() * 100, 1),
            "total_pnl": round(sub["pnl"].sum(), 2),
            "avg_R": round(sub["R"].mean(), 3),
            "top_mistake": top,
        })
    return pd.DataFrame(rows).sort_values("week").reset_index(drop=True)


def equity_curve(df: pd.DataFrame) -> pd.DataFrame:
    """Chronological cumulative P&L / R with running peak and drawdown.

    A leading 0 point is prepended so a first losing trade registers as a
    drawdown from the starting (flat) equity.
    """
    if df.empty:
        return pd.DataFrame()
    d = df.copy()
    if "exit_time" in d.columns:
        d["_t"] = pd.to_datetime(d["exit_time"], errors="coerce")
        d = d.sort_values("_t", kind="stable")
    d = d.reset_index(drop=True)
    n = len(d)
    cum_pnl = [0.0] + d["pnl"].cumsum().tolist()
    cum_R = [0.0] + d["R"].cumsum().tolist()
    eq = pd.DataFrame({"trade": list(range(0, n + 1)),
                       "cum_pnl": cum_pnl, "cum_R": cum_R})
    eq["peak"] = eq["cum_pnl"].cummax()
    eq["drawdown"] = eq["cum_pnl"] - eq["peak"]
    eq["peak_R"] = eq["cum_R"].cummax()
    eq["drawdown_R"] = eq["cum_R"] - eq["peak_R"]
    return eq


def max_drawdown(eq: pd.DataFrame) -> dict:
    """Largest peak-to-trough decline in $ and R from an equity curve."""
    if eq.empty or len(eq) < 2:
        return {"mdd": 0.0, "mdd_R": 0.0, "trough": 0, "peak_at": 0.0}
    idx = int(eq["drawdown"].idxmin())
    return {"mdd": float(eq["drawdown"].min()),
            "mdd_R": float(eq["drawdown_R"].min()),
            "trough": idx,
            "peak_at": float(eq.loc[idx, "peak"])}


def relvol_bucket(v) -> str:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "Unknown"
    if pd.isna(v):
        return "Unknown"
    if v < 0.8:
        return "Low"
    if v >= 1.2:
        return "High"
    return "Normal"


def atr_bucket(p, low: float, high: float) -> str:
    try:
        p = float(p)
    except (TypeError, ValueError):
        return "Unknown"
    if pd.isna(p):
        return "Unknown"
    if p < low:
        return "Low"
    if p > high:
        return "High"
    return "Normal"


def session_bucket(h) -> str:
    try:
        h = int(h)
    except (TypeError, ValueError):
        return "Unknown"
    if 9 <= h < 10:
        return "Open (9-10)"
    if 10 <= h < 12:
        return "Morning (10-12)"
    if 12 <= h < 14:
        return "Midday (12-14)"
    if 14 <= h < 16:
        return "Power hour (14-16)"
    return "Other"


def wilson_interval(wins: int, n: int, z: float = 1.96):
    """95% Wilson confidence interval for a win rate (robust at small n)."""
    if n == 0:
        return (0.0, 0.0)
    p = wins / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    margin = (z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)) / denom
    return (max(0.0, center - margin), min(1.0, center + margin))


def reliability_label(n: int) -> str:
    if n < 5:
        return "Very low — treat as noise"
    if n < 15:
        return "Low"
    if n < 30:
        return "Moderate"
    return "Reasonable"


def add_estimator_cols(df: pd.DataFrame, atr_low: float, atr_high: float) -> pd.DataFrame:
    if df.empty:
        return df
    d = df.copy()
    d["relvol_bucket"] = d["relvol_at_open"].apply(relvol_bucket)
    d["atr_bucket"] = d["atr_pct_at_open"].apply(lambda p: atr_bucket(p, atr_low, atr_high))
    d["session"] = d["entry_hour"].apply(session_bucket)
    if "setup_type" not in d:
        d["setup_type"] = ""
    if "news_at_open" not in d:
        d["news_at_open"] = ""
    return d


def _filter_match(d: pd.DataFrame, filters: dict) -> pd.DataFrame:
    m = pd.Series(True, index=d.index)
    for k, v in filters.items():
        if v not in (None, "Any", "") and k in d.columns:
            m &= (d[k] == v)
    return d[m]


def _level_stats(sub: pd.DataFrame) -> dict:
    n = len(sub)
    if n == 0:
        return {"n": 0, "win_rate": None, "ci_low": None, "ci_high": None,
                "avg_R": None, "total_pnl": None}
    wins = int((sub["pnl"] > 0).sum())
    lo, hi = wilson_interval(wins, n)
    return {"n": n, "win_rate": wins / n * 100,
            "ci_low": lo * 100, "ci_high": hi * 100,
            "avg_R": float(sub["R"].mean()),
            "total_pnl": float(sub["pnl"].sum())}


def estimate_levels(d: pd.DataFrame, filters: dict) -> list:
    """Graded conditional estimate, from most specific to baseline."""
    core = {k: filters.get(k) for k in
            ["score_at_open", "bias_at_open", "setup_type"]}
    no_ticker = {k: v for k, v in filters.items() if k != "ticker"}
    levels = [
        ("Exact match (all selected conditions)", filters),
        ("Same conditions · any ticker", no_ticker),
        ("Core setup (score · bias · setup type)", core),
        ("Baseline · all trades", {}),
    ]
    out = []
    seen = set()
    for name, f in levels:
        sub = _filter_match(d, f)
        key = (len(sub), tuple(sorted((k, str(v)) for k, v in f.items()
                                      if v not in (None, "Any", ""))))
        s = _level_stats(sub)
        s["level"] = name
        out.append(s)
        seen.add(key)
    return out


def discipline_grade(df: pd.DataFrame):
    """Return (letter, score 0-100, breakdown list of (label, count, points))."""
    breakdown = []
    score = 100
    if df.empty:
        return "—", 0, [("No trades yet", 0, 0)]

    red = int((df["score_at_open"] == "Red").sum())
    pen = 8 * red
    score -= pen
    breakdown.append(("Trades taken on a RED score", red, -pen))

    def tag_count(tag):
        return int(df["mistakes_list"].apply(lambda l: tag in l).sum())

    revenge = tag_count("revenge trade")
    pen = 12 * revenge
    score -= pen
    breakdown.append(("'Revenge trade' tags", revenge, -pen))

    oversize = tag_count("oversized position")
    pen = 8 * oversize
    score -= pen
    breakdown.append(("'Oversized position' tags", oversize, -pen))

    # Daily rules respected: any day with > 3 trades is a break of the 3/day cap
    per_day = df.groupby("exit_date").size()
    over_days = int((per_day > 3).sum())
    pen = 10 * over_days
    score -= pen
    breakdown.append(("Days exceeding the 3-trade limit", over_days, -pen))

    score = max(0, min(100, score))
    letter = ("A" if score >= 90 else "B" if score >= 80 else
              "C" if score >= 70 else "D" if score >= 60 else "F")
    return letter, score, breakdown


def by_setup(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "setup_type" not in df.columns:
        return pd.DataFrame()
    d = df[df["setup_type"].astype(str).str.strip() != ""]
    if d.empty:
        return pd.DataFrame()
    g = d.groupby("setup_type").agg(
        trades=("pnl", "size"), win_rate=("win", "mean"),
        avg_R=("R", "mean"), total_pnl=("pnl", "sum"))
    g["win_rate"] *= 100
    return g


def pnl_by_session(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "session" not in df.columns:
        return pd.DataFrame()
    d = df[df["session"] != "Unknown"]
    if d.empty:
        return pd.DataFrame()
    g = d.groupby("session").agg(
        trades=("pnl", "size"), win_rate=("win", "mean"),
        avg_R=("R", "mean"), total_pnl=("pnl", "sum"))
    g["win_rate"] *= 100
    return g


# Map a discipline issue to a concrete, behavioural rule (no prediction)
LEAK_TO_RULE = {
    "Opened during lunch chop": "Don't open new trades during the lunch window "
        "(roughly 11:30–13:30 ET).",
    "Opened during first 5 minutes": "Wait at least 5 minutes after the open "
        "before entering.",
    "Opened during news blackout": "Stand aside in the minutes before scheduled "
        "news.",
    "Opened with Yellow score": "Take Yellow-score trades at reduced size, or "
        "skip them.",
    "Opened with low relative volume": "Require relative volume at or above "
        "average before entering.",
    "Opened against trend bias": "Trade only in the direction of the VWAP/EMA "
        "trend.",
    "Opened without 2R target-to-risk": "Require at least a 2R target before "
        "entering.",
    "Traded on RED score": "Do not take RED-score trades.",
    "Overrode 3-trade limit": "Stop after 3 trades in a day.",
    "revenge trade": "After a loss, wait out the full cooldown before trading "
        "again.",
    "chased entry": "Enter at your planned level; if price has left it, let the "
        "trade go.",
    "ignored red score": "Respect the RED score and stand aside.",
    "moved stop": "Set your stop once and do not widen it.",
    "oversized position": "Size every trade within your risk limit.",
    "no clear setup": "Only enter when the trade matches a defined setup.",
}


def _money(x) -> str:
    return f"${x:,.2f}"


def coach_report(df_raw: pd.DataFrame, atr_low: float, atr_high: float,
                 today_iso: str) -> list:
    """Deterministic, data-only coaching summary. Returns ordered sections.

    Each section: {"title": str, "body": [str], "note": str|None}.
    Descriptive past-tense only; flags small samples explicitly.
    """
    MIN_TOTAL = 5      # below this, the whole journal is 'too small'
    MIN_BUCKET = 3     # below this, a single bucket isn't named as best/worst
    sections = []
    if df_raw.empty:
        return [{"title": "No data", "body": ["No closed trades logged yet."],
                 "note": None}]
    df = add_estimator_cols(df_raw, atr_low, atr_high)
    n_total = len(df)
    small = n_total < MIN_TOTAL

    # ---- Daily review ------------------------------------------------------
    tr = df[df["exit_date"].astype(str) == today_iso]
    if len(tr) == 0:
        body = ["No trades were closed today."]
        note = None
    else:
        n = len(tr)
        wins = int((tr["pnl"] > 0).sum())
        body = [
            f"Closed {n} trade(s): {wins} winner(s), {n - wins} loser(s) "
            f"({wins / n * 100:.0f}% win rate).",
            f"Realized P&L {_money(tr['pnl'].sum())}, average "
            f"{tr['R'].mean():+.2f}R.",
            f"Biggest win {_money(tr['pnl'].max())}, biggest loss "
            f"{_money(tr['pnl'].min())}.",
        ]
        rb = sorted({r for lst in tr["rules_list"] for r in lst})
        if rb:
            body.append("Rules broken today: " + ", ".join(rb) + ".")
        mk = sorted({m for lst in tr["mistakes_list"] for m in lst})
        if mk:
            body.append("Mistake tags today: " + ", ".join(mk) + ".")
        note = ("Only a few trades — read this as a log of today, not a trend."
                if n < MIN_BUCKET else None)
    sections.append({"title": "Daily review", "body": body, "note": note})

    # ---- Weekly review -----------------------------------------------------
    ws = weekly_summary(df)
    if ws.empty:
        sections.append({"title": "Weekly review",
                         "body": ["No trades logged yet."], "note": None})
    else:
        last = ws.iloc[-1]
        body = [
            f"Week {last['week']}: {int(last['trades'])} trade(s), "
            f"{last['win_rate']:.0f}% win rate, P&L "
            f"{_money(last['total_pnl'])}, average {last['avg_R']:+.2f}R.",
            f"Most common mistake tag this week: {last['top_mistake']}.",
        ]
        note = (f"{int(last['trades'])} trades is a small sample; treat as "
                "tentative." if last["trades"] < MIN_TOTAL else None)
        sections.append({"title": "Weekly review", "body": body, "note": note})

    bs = by_setup(df)
    qual = bs[bs["trades"] >= MIN_BUCKET] if not bs.empty else bs

    # ---- Best setup --------------------------------------------------------
    if qual is None or qual.empty:
        sections.append({"title": "Best setup",
                         "body": ["Not enough data: no setup type has at least "
                                  f"{MIN_BUCKET} logged trades yet."],
                         "note": None})
    else:
        top = qual.sort_values("total_pnl", ascending=False).iloc[0]
        sections.append({"title": "Best setup (by total P&L)", "body": [
            f"{top.name}: {int(top['trades'])} trades, {top['win_rate']:.0f}% "
            f"win rate, average {top['avg_R']:+.2f}R, total "
            f"{_money(top['total_pnl'])}.",
            f"Reliability: {reliability_label(int(top['trades']))}.",
        ], "note": None})

    # ---- Worst setup -------------------------------------------------------
    if qual is None or qual.empty:
        sections.append({"title": "Worst setup",
                         "body": ["Not enough data yet."], "note": None})
    else:
        bot = qual.sort_values("total_pnl", ascending=True).iloc[0]
        sections.append({"title": "Worst setup (by total P&L)", "body": [
            f"{bot.name}: {int(bot['trades'])} trades, {bot['win_rate']:.0f}% "
            f"win rate, average {bot['avg_R']:+.2f}R, total "
            f"{_money(bot['total_pnl'])}.",
            f"Reliability: {reliability_label(int(bot['trades']))}.",
        ], "note": None})

    # ---- Highest-expectancy setup -----------------------------------------
    if qual is None or qual.empty:
        sections.append({"title": "Highest-expectancy setup",
                         "body": ["Not enough data yet."], "note": None})
    else:
        exp = qual.sort_values("avg_R", ascending=False).iloc[0]
        sections.append({"title": "Highest-expectancy setup (by average R)",
                         "body": [
            f"{exp.name}: average {exp['avg_R']:+.2f}R over {int(exp['trades'])} "
            f"trades ({exp['win_rate']:.0f}% win rate).",
            "Expectancy is average R per trade — it already blends win rate and "
            "win/loss size.",
            f"Reliability: {reliability_label(int(exp['trades']))}.",
        ], "note": None})

    # ---- Biggest discipline leak ------------------------------------------
    pool = []  # (label, trades, total_pnl)
    br = by_rules_broken(df)
    for idx, row in (br.iterrows() if not br.empty else []):
        pool.append((idx, int(row["trades"]), float(row["total_pnl"])))
    bm = by_mistake_tag(df)
    for idx, row in (bm.iterrows() if not bm.empty else []):
        pool.append((idx, int(row["trades"]), float(row["total_pnl"])))
    cand = [p for p in pool if p[1] >= 2]
    leak_label = None
    if not cand:
        sections.append({"title": "Biggest discipline leak", "body": [
            "No recurring discipline issue recorded (either you've been "
            "disciplined, or there isn't enough data yet)."], "note": None})
    else:
        costliest = min(cand, key=lambda p: p[2])
        if costliest[2] < 0:
            leak_label = costliest[0]
            sections.append({"title": "Biggest discipline leak", "body": [
                f"'{leak_label}' shows up in {costliest[1]} trades and is "
                f"associated with {_money(costliest[2])} of P&L.",
                "This is a correlation in your own log, not a proven cause.",
            ], "note": None})
        else:
            most_freq = max(cand, key=lambda p: p[1])
            leak_label = most_freq[0]
            sections.append({"title": "Biggest discipline leak", "body": [
                f"Your most frequent flag is '{leak_label}' ({most_freq[1]} "
                f"trades), but it hasn't cost money so far "
                f"({_money(most_freq[2])}).",
            ], "note": None})

    # ---- Best / worst trading window --------------------------------------
    ps = pnl_by_session(df)
    pq = ps[ps["trades"] >= MIN_BUCKET] if not ps.empty else ps
    if pq is None or pq.empty:
        sections.append({"title": "Most profitable trading window",
                         "body": ["Not enough data: no time-of-day window has "
                                  f"at least {MIN_BUCKET} trades yet."],
                         "note": None})
        sections.append({"title": "Worst trading window",
                         "body": ["Not enough data yet."], "note": None})
    else:
        bw = pq.sort_values("total_pnl", ascending=False).iloc[0]
        ww = pq.sort_values("total_pnl", ascending=True).iloc[0]
        sections.append({"title": "Most profitable trading window", "body": [
            f"{bw.name}: {int(bw['trades'])} trades, total {_money(bw['total_pnl'])} "
            f"({bw['win_rate']:.0f}% win rate, {bw['avg_R']:+.2f}R).",
            f"Reliability: {reliability_label(int(bw['trades']))}.",
        ], "note": None})
        sections.append({"title": "Worst trading window", "body": [
            f"{ww.name}: {int(ww['trades'])} trades, total {_money(ww['total_pnl'])} "
            f"({ww['win_rate']:.0f}% win rate, {ww['avg_R']:+.2f}R).",
            f"Reliability: {reliability_label(int(ww['trades']))}.",
        ], "note": None})

    # ---- One rule to focus on tomorrow ------------------------------------
    if leak_label and leak_label in LEAK_TO_RULE:
        focus = LEAK_TO_RULE[leak_label]
        body = [focus, f"Chosen because '{leak_label}' is the clearest "
                       "discipline issue in your log right now."]
    else:
        # fall back to the grade's largest deduction
        _, _, breakdown = discipline_grade(df)
        hits = [b for b in breakdown if b[1] > 0]
        if hits:
            worst = max(hits, key=lambda b: -b[2])  # biggest point loss
            label = worst[0]
            mapping = {
                "Trades taken on a RED score": "Do not take RED-score trades.",
                "'Revenge trade' tags": "After a loss, wait out the cooldown "
                    "before trading again.",
                "'Oversized position' tags": "Size every trade within your risk "
                    "limit.",
                "Days exceeding the 3-trade limit": "Stop after 3 trades in a "
                    "day.",
            }
            body = [mapping.get(label, "Keep following your written rules."),
                    f"Chosen from your discipline grade ({label})."]
        else:
            body = ["Keep doing what's working: size within your risk limit and "
                    "trade with the trend.",
                    "No recurring rule break stood out in the data."]
    if small:
        body.append("With fewer than %d closed trades, treat this as a "
                    "starting point, not a verdict." % MIN_TOTAL)
    sections.append({"title": "One rule to focus on tomorrow", "body": body,
                     "note": None})

    return sections


def render_bar(labels, values, title, ylabel, colors=None):
    """Bar chart via matplotlib (fallback to st.bar_chart)."""
    labels = [str(l) for l in labels]
    if HAS_MPL:
        fig, ax = plt.subplots(figsize=(5, 3.2))
        ax.bar(labels, values, color=colors)
        ax.axhline(0, color="#999", lw=0.8)
        ax.set_title(title, fontsize=11)
        ax.set_ylabel(ylabel, fontsize=9)
        ax.tick_params(labelsize=9)
        fig.tight_layout()
        st.pyplot(fig)
        plt.close(fig)
    else:
        st.bar_chart(pd.DataFrame({ylabel: values}, index=labels))
        st.caption(title)


def render_equity(eq: pd.DataFrame):
    """Equity curve with peak line + an underwater drawdown panel."""
    if eq.empty:
        return
    x = eq["trade"].tolist()
    if HAS_MPL:
        fig, (ax1, ax2) = plt.subplots(
            2, 1, figsize=(7, 5), sharex=True,
            gridspec_kw={"height_ratios": [3, 1]})
        ax1.plot(x, eq["cum_pnl"], color="#1565c0", lw=1.7, label="Equity ($)")
        ax1.plot(x, eq["peak"], color="#9e9e9e", lw=0.9, ls="--", label="Peak")
        ax1.fill_between(x, eq["cum_pnl"], eq["peak"],
                         where=(eq["cum_pnl"] < eq["peak"]),
                         color="#ef9a9a", alpha=0.45)
        ax1.axhline(0, color="#888", lw=0.8)
        ax1.set_ylabel("Cumulative P&L ($)", fontsize=9)
        ax1.set_title("Equity curve", fontsize=11)
        ax1.legend(fontsize=8)
        ax2.fill_between(x, eq["drawdown"], 0, color="#c62828", alpha=0.5)
        ax2.set_ylabel("Drawdown ($)", fontsize=9)
        ax2.set_xlabel("Trade #", fontsize=9)
        fig.tight_layout()
        st.pyplot(fig)
        plt.close(fig)
    else:
        st.line_chart(eq.set_index("trade")[["cum_pnl", "peak"]])
        st.area_chart(eq.set_index("trade")[["drawdown"]])


# --------------------------------------------------------------------------- #
# Plain-English explanations (shown in "What does this mean?" expanders)
# --------------------------------------------------------------------------- #
EXPLAIN = {
    "vwap": "VWAP (Volume-Weighted Average Price) is the average price paid "
            "today, weighted by volume. Price **above** VWAP = buyers in "
            "control (bullish). **Below** = sellers in control (bearish). Many "
            "traders only go long above VWAP and short below it.",
    "ema9": "EMA 9 is a fast 9-period average of price. It hugs price closely "
            "and shows the very short-term direction.",
    "ema20": "EMA 20 is a medium-speed average. EMA 9 above EMA 20 = short-term "
             "momentum up; below = down.",
    "ema200": "EMA 200 is the slow, big-picture trend line. Price and faster "
              "EMAs above it = overall uptrend; below = downtrend. It's your "
              "'which way is the river flowing' reference.",
    "stack": "When the EMAs line up in order (9 > 20 > 200 for up, or "
             "9 < 20 < 200 for down) the trend is 'stacked' — the cleanest, "
             "most reliable direction. Tangled EMAs = chop, where beginners "
             "lose money.",
    "atr": "ATR (Average True Range) measures how much price typically moves "
           "per bar — volatility. Too **low** = quiet/choppy. Too **high** = "
           "fast and risky. You want the healthy middle. ATR also sets "
           "sensible stop distances.",
    "relvol": "Relative volume compares right-now volume to the recent average. "
              "1.0× = normal. Above ~1.2× = strong participation (moves more "
              "trustworthy). Below ~0.7× = thin, fakeout-prone.",
    "open_5min": "The first ~5 minutes after the 9:30 ET open are wild: huge "
                 "spreads, fast reversals, bad fills. Most pros wait for it to "
                 "settle.",
    "lunch_chop": "Midday (~11:30–13:30 ET) volume dries up. Price drifts "
                  "sideways and 'chops,' creating fakeouts. Many traders skip "
                  "this window.",
    "low_volume": "Low volume = few participants. Moves fake out and reverse "
                  "easily. Real moves usually need volume behind them.",
    "pre_news": "Right before scheduled news (CPI, FOMC, earnings) price can "
                "gap violently and stops may not hold. Standing aside until it "
                "passes is a common rule.",
    "low_liquidity": "Low liquidity / wide spread means a big gap between buy "
                     "and sell prices, so you 'pay up' to get in and out. It "
                     "quietly eats profits.",
    "green": "GREEN = conditions look favorable: clear trend, decent volume, "
             "healthy volatility, no danger windows. It is **not** a buy signal "
             "or guarantee — it means 'if you have a setup, conditions support "
             "taking it.'",
    "yellow": "YELLOW = caution. Something is mixed (unclear trend, soft volume, "
              "or a chop window). Smaller size, or sit out.",
    "red": "RED = stand aside. A danger window or conditions too poor to trade. "
           "The best trade is often no trade.",
    "sizing": "Position sizing decides how many shares to buy so that if your "
              "stop is hit, you lose only your chosen risk amount (e.g. 1% of "
              "the account). Shares = (account × risk%) ÷ (entry − stop). This "
              "is the single most important habit in trading.",
    "lockout": "A daily lockout stops you trading once you hit your loss limit "
               "or max number of losses. It stops a bad day from becoming a "
               "catastrophic one. Walk away — the market reopens tomorrow.",
    "paper": "Paper trading = practicing with fake money at real prices. You "
             "build skill and test discipline with zero financial risk. Nothing "
             "here touches a real account or broker.",
    "backtest": "Backtesting replays the rules over past data to see how the "
                "decision filter would have behaved. Results are in R-multiples "
                "(1R = your risk per trade). It ignores fees and slippage and "
                "never guarantees the future.",
}


def explain(key: str):
    txt = EXPLAIN.get(key)
    if txt:
        with st.expander("ℹ️ What does this mean? (beginner)"):
            st.write(txt)


# --------------------------------------------------------------------------- #
# Data
# --------------------------------------------------------------------------- #
@st.cache_data(ttl=120, show_spinner=False)
def fetch(ticker: str, period: str, interval: str) -> pd.DataFrame:
    if yf is None:
        raise RuntimeError("yfinance is not installed. Run: pip install yfinance")
    df = yf.Ticker(ticker).history(period=period, interval=interval,
                                   prepost=False, actions=False)
    if df is None or df.empty:
        return pd.DataFrame()
    df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
    if df.index.tz is not None:
        # Yahoo already returns intraday timestamps in the exchange's local zone.
        # Convert to ET when possible; if the tz database is unavailable, keep the
        # original tz-aware index rather than crashing the app.
        try:
            df.index = df.index.tz_convert(ET)
        except Exception:
            pass
    return df.dropna(subset=["Close"])


# --------------------------------------------------------------------------- #
# Indicators
# --------------------------------------------------------------------------- #
def add_indicators(df: pd.DataFrame, atr_period: int = 14,
                   vol_lookback: int = 20) -> pd.DataFrame:
    df = df.copy()
    df["EMA9"] = df["Close"].ewm(span=9, adjust=False).mean()
    df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()
    df["EMA200"] = df["Close"].ewm(span=200, adjust=False).mean()

    tp = (df["High"] + df["Low"] + df["Close"]) / 3.0
    day_key = df.index.date
    df["VWAP"] = ((tp * df["Volume"]).groupby(day_key).cumsum()
                  / df["Volume"].groupby(day_key).cumsum().replace(0, np.nan))

    prev = df["Close"].shift(1)
    tr = pd.concat([df["High"] - df["Low"],
                    (df["High"] - prev).abs(),
                    (df["Low"] - prev).abs()], axis=1).max(axis=1)
    df["ATR"] = tr.ewm(alpha=1.0 / atr_period, adjust=False).mean()
    df["ATR_pct"] = df["ATR"] / df["Close"]

    df["AvgVol"] = df["Volume"].rolling(vol_lookback, min_periods=5).mean()
    df["RelVol"] = df["Volume"] / df["AvgVol"].replace(0, np.nan)
    df["Range_pct"] = (df["High"] - df["Low"]) / df["Close"]
    return df


# --------------------------------------------------------------------------- #
# Conditions / scoring
# --------------------------------------------------------------------------- #
@dataclass
class Config:
    lunch_start: dt.time = dt.time(11, 30)
    lunch_end: dt.time = dt.time(13, 30)
    relvol_low: float = 0.7
    relvol_floor: float = 0.5
    atr_low: float = 0.0008
    atr_high: float = 0.010
    pre_news_minutes: int = 5
    news_windows: list = field(default_factory=list)


def detect_flags(ts: pd.Timestamp, row: pd.Series, cfg: Config) -> dict:
    intraday = ts.tzinfo is not None
    t = ts.time() if intraday else None
    f = {}
    f["open_5min"] = bool(intraday and dt.time(9, 30) <= t < dt.time(9, 35))
    f["lunch_chop"] = bool(intraday and cfg.lunch_start <= t < cfg.lunch_end)
    rv = row.get("RelVol", np.nan)
    f["low_volume"] = bool(pd.notna(rv) and rv < cfg.relvol_low)
    pre = False
    if intraday and cfg.news_windows:
        for nt in cfg.news_windows:
            if nt.tzinfo is None:
                continue
            d = (nt - ts).total_seconds()
            if 0 <= d <= cfg.pre_news_minutes * 60:
                pre = True
                break
    f["pre_news"] = pre
    rng, ap = row.get("Range_pct", np.nan), row.get("ATR_pct", np.nan)
    wide = bool(pd.notna(rng) and pd.notna(ap) and rng > 1.8 * ap)
    f["low_liquidity"] = bool(pd.notna(rv) and rv < cfg.relvol_floor and wide)
    return f


def trend_bias(row: pd.Series) -> str:
    c, v = row["Close"], row["VWAP"]
    e9, e20, e200 = row["EMA9"], row["EMA20"], row["EMA200"]
    if pd.isna([c, v, e9, e20, e200]).any():
        return "none"
    if c > v and e9 > e20 > e200:
        return "long"
    if c < v and e9 < e20 < e200:
        return "short"
    return "none"


def score_bar(row: pd.Series, flags: dict, cfg: Config):
    bias = trend_bias(row)
    hard = []
    if flags.get("open_5min"):
        hard.append("First 5 min after open — erratic, wide spreads")
    if flags.get("pre_news"):
        hard.append("Inside pre-news / event blackout window")
    if flags.get("low_liquidity"):
        hard.append("Low liquidity / wide spread")
    if hard:
        return "Red", bias, hard

    pts, reasons = 0, []
    if bias in ("long", "short"):
        pts += 2
        reasons.append(f"Trend aligned ({'bullish' if bias=='long' else 'bearish'}): "
                       "price vs VWAP and the EMA stack agree")
    else:
        pts -= 1
        reasons.append("Mixed trend: price/VWAP/EMAs disagree (chop risk)")

    rv = row.get("RelVol", np.nan)
    if pd.notna(rv):
        if rv >= 1.2:
            pts += 1
            reasons.append(f"Good participation (RelVol {rv:.2f}×)")
        elif rv < cfg.relvol_low:
            pts -= 1
            reasons.append(f"Low volume (RelVol {rv:.2f}×)")
        else:
            reasons.append(f"Average volume (RelVol {rv:.2f}×)")

    a = row.get("ATR_pct", np.nan)
    if pd.notna(a):
        if a < cfg.atr_low:
            pts -= 1
            reasons.append(f"Volatility very low (ATR {a*100:.2f}%) — choppy")
        elif a > cfg.atr_high:
            pts -= 1
            reasons.append(f"Volatility very high (ATR {a*100:.2f}%) — risky")
        else:
            pts += 1
            reasons.append(f"Healthy volatility (ATR {a*100:.2f}%)")

    if flags.get("lunch_chop"):
        pts -= 1
        reasons.append("Lunch chop window (low-conviction moves)")

    if pts >= 3 and bias in ("long", "short") and not flags.get("lunch_chop"):
        label = "Green"
    elif pts <= 0:
        label = "Red"
    else:
        label = "Yellow"
    return label, bias, reasons


# --------------------------------------------------------------------------- #
# Pure helpers (paper-trade math)
# --------------------------------------------------------------------------- #
def position_size(account, risk_pct, entry, stop):
    per_share = abs(entry - stop)
    max_loss = account * risk_pct / 100.0
    shares = int(max_loss // per_share) if per_share > 0 else 0
    return shares, max_loss, per_share


def trade_pnl(side, entry, price, shares):
    return (price - entry) * shares if side == "long" else (entry - price) * shares


def trade_R(side, entry, stop, exit_price):
    risk = abs(entry - stop)
    if risk == 0:
        return 0.0
    return ((exit_price - entry) / risk) if side == "long" \
        else ((entry - exit_price) / risk)


def safe_price(x, fallback=1.0, min_value=0.0):
    """Return a finite value >= min_value, safe to pass as a number_input
    default. NaN / inf / None / non-numeric -> fallback (also clamped), and any
    negative result is clamped up to min_value. This prevents
    StreamlitValueBelowMinError when a computed entry/stop/target goes negative
    or invalid (e.g. a short target priced below zero)."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        v = float("nan")
    if not math.isfinite(v):
        try:
            v = float(fallback)
        except (TypeError, ValueError):
            v = min_value
        if not math.isfinite(v):
            v = min_value
    return max(min_value, v)


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(s).lower()).strip("_")


def detect_soft_rules(trade: dict, flags: dict, label: str, bias: str) -> list:
    """Return the stable labels of any soft rules a proposed trade triggers."""
    rules = []
    if flags.get("lunch_chop"):
        rules.append("Opened during lunch chop")
    if flags.get("open_5min"):
        rules.append("Opened during first 5 minutes")
    if flags.get("pre_news"):
        rules.append("Opened during news blackout")
    if label == "Yellow":
        rules.append("Opened with Yellow score")
    if flags.get("low_volume"):
        rules.append("Opened with low relative volume")
    side = trade.get("side")
    if bias in ("long", "short") and (
            (bias == "long" and side == "short") or
            (bias == "short" and side == "long")):
        rules.append("Opened against trend bias")
    risk = abs(float(trade["entry"]) - float(trade["stop"]))
    reward = abs(float(trade["target"]) - float(trade["entry"]))
    rr = (reward / risk) if risk > 0 else 0.0
    if rr < 2.0:
        rules.append("Opened without 2R target-to-risk")
    return rules


# --------------------------------------------------------------------------- #
# Backtest
# --------------------------------------------------------------------------- #
def run_backtest(df, cfg, use_time_filter, atr_mult, rr, enforce_limits,
                 max_losses, max_daily_pct):
    rows = []
    in_pos = False
    entry = stop = target = 0.0
    direction = 0
    cur_day = None
    day_losses = 0
    day_R = 0.0
    stopped = False
    idx = df.index
    for i in range(len(df)):
        ts, row = idx[i], df.iloc[i]
        if pd.isna([row.get("ATR"), row.get("EMA200"), row.get("VWAP")]).any():
            continue
        day = ts.date()
        if day != cur_day:
            cur_day = day
            day_losses, day_R, stopped = 0, 0.0, False
            if in_pos:
                R = trade_R("long" if direction == 1 else "short",
                            entry, stop, row["Open"])
                rows.append({"exit": ts, "R": R, "reason": "session_end"})
                day_R += R
                in_pos = False
        if in_pos:
            hit_stop = row["Low"] <= stop if direction == 1 else row["High"] >= stop
            hit_tgt = row["High"] >= target if direction == 1 else row["Low"] <= target
            ex, reason = None, None
            if hit_stop:
                ex, reason = -1.0, "stop"
            elif hit_tgt:
                ex, reason = rr, "target"
            if ex is not None:
                rows.append({"exit": ts, "R": ex, "reason": reason})
                day_R += ex
                if ex < 0:
                    day_losses += 1
                in_pos = False
        if enforce_limits and (day_losses >= max_losses or
                               day_R <= -(max_daily_pct / 100.0) * 100):
            stopped = True
        if not in_pos and not stopped:
            flags = detect_flags(ts, row, cfg)
            lbl, b, _ = score_bar(row, flags, cfg)
            blocked = use_time_filter and (
                flags.get("open_5min") or flags.get("lunch_chop")
                or flags.get("pre_news") or flags.get("low_liquidity"))
            if lbl == "Green" and b in ("long", "short") and not blocked:
                direction = 1 if b == "long" else -1
                entry = row["Close"]
                risk = row["ATR"] * atr_mult
                if risk <= 0:
                    continue
                stop = entry - risk if direction == 1 else entry + risk
                target = entry + rr * risk if direction == 1 else entry - rr * risk
                in_pos = True
    res = pd.DataFrame(rows)
    if res.empty:
        return res, {}
    wins = res[res["R"] > 0]
    losses = res[res["R"] <= 0]
    gw, gl = wins["R"].sum(), abs(losses["R"].sum())
    eq = res["R"].cumsum()
    dd = (eq - eq.cummax()).min()
    met = {
        "Trades": len(res),
        "Win rate": f"{len(wins)/len(res)*100:.1f}%",
        "Total R": f"{res['R'].sum():.2f}",
        "Expectancy (R)": f"{res['R'].mean():.3f}",
        "Profit factor": f"{(gw/gl):.2f}" if gl else "∞",
        "Max DD (R)": f"{dd:.2f}",
    }
    return res, met


# =========================================================================== #
# UI
# =========================================================================== #
st.set_page_config(page_title="Paper Trade Dashboard", page_icon="📊",
                   layout="wide")

ss = st.session_state
ss.setdefault("open_trades", [])
if "journal" not in ss:                 # load saved trades.csv once per session
    ss.journal = load_journal()
ss.setdefault("last_loss_time", None)
ss.setdefault("confirm_reset", False)
ss.setdefault("override_3", False)
ss.setdefault("trade_stage", "entry")     # "entry" -> "review"
ss.setdefault("pending_trade", None)

with st.sidebar:
    st.markdown("### 🧪 PAPER MODE ONLY")
    st.caption("Simulated trades · no brokerage · no live orders.")
    st.divider()

    st.header("Market data")
    ticker = st.text_input("Ticker", value="SPY").strip().upper()
    interval = st.selectbox("Interval", ["1m", "2m", "5m", "15m", "30m", "1h", "1d"],
                            index=2)
    period_map = {"1m": ["1d", "5d", "7d"], "2m": ["1d", "5d", "60d"],
                  "5m": ["1d", "5d", "30d", "60d"], "15m": ["5d", "30d", "60d"],
                  "30m": ["5d", "30d", "60d"], "1h": ["30d", "60d", "180d"],
                  "1d": ["6mo", "1y", "2y"]}
    period = st.selectbox("History", period_map.get(interval, ["5d"]), index=0)
    clean = st.toggle("📸 Clean view (screenshot)", value=False,
                      help="Hides explainers & charts for a tidy screenshot.")

    st.divider()
    st.header("Condition settings")
    relvol_low = st.slider("Low-volume threshold (RelVol)", 0.3, 1.0, 0.7, 0.05)
    atr_low = st.slider("Min healthy ATR %", 0.0, 0.3, 0.08, 0.01) / 100
    atr_high = st.slider("Max healthy ATR %", 0.3, 3.0, 1.0, 0.1) / 100
    lunch = st.slider("Lunch-chop window (ET)", 10.0, 15.0, (11.5, 13.5), 0.25)
    pre_news_min = st.number_input("Pre-news warning (min)", 1, 60, 5)
    news_raw = st.text_area(
        "News / event times today (ET, HH:MM, one per line)",
        placeholder="08:30\n14:00",
        help="Manually enter known events (CPI, FOMC, earnings). The app warns "
             "in the minutes before each.")

    st.divider()
    st.header("Risk rules")
    account = st.number_input("Account size ($)", 100.0, 1e9, 25000.0, step=500.0)
    risk_pct = st.slider("Max risk per trade (%)", 0.1, 5.0, 1.0, 0.1)
    max_daily_pct = st.slider("Max daily loss (%)", 0.5, 10.0, 3.0, 0.5)
    max_losses = int(st.number_input("Lockout after N losses", 1, 10, 2))
    cooldown_min = int(st.number_input("Cooldown after a loss (min)", 0, 120, 10))

news_windows = []
now = dt.datetime.now()
for line in [l.strip() for l in news_raw.splitlines() if l.strip()]:
    try:
        hh, mm = map(int, line.split(":"))
    except Exception:
        st.sidebar.warning(f"Couldn't parse time: '{line}' (use HH:MM)")
        continue
    naive = dt.datetime(now.year, now.month, now.day, hh, mm)
    try:
        news_windows.append(pd.Timestamp(naive, tz=ET))
    except Exception:
        # tz database unavailable — store naive (skipped vs tz-aware bars)
        news_windows.append(pd.Timestamp(naive))

cfg = Config(lunch_start=dt.time(int(lunch[0]), int((lunch[0] % 1) * 60)),
             lunch_end=dt.time(int(lunch[1]), int((lunch[1] % 1) * 60)),
             relvol_low=relvol_low, atr_low=atr_low, atr_high=atr_high,
             pre_news_minutes=int(pre_news_min), news_windows=news_windows)

st.title("📊 Day-Trading Decision Dashboard")
st.caption("🧪 **Paper mode only** — no brokerage, no live orders, no profit "
           "guarantees. Data may be ~15 min delayed. Educational, not advice.")

if not ticker:
    st.info("Enter a ticker to begin."); st.stop()
try:
    raw = fetch(ticker, period, interval)
except Exception as e:
    st.error(f"Data fetch failed: {e}"); st.stop()
if raw.empty or len(raw) < 5:
    st.error(f"No usable data for {ticker} ({interval}/{period})."); st.stop()

data = add_indicators(raw)
latest, latest_ts = data.iloc[-1], data.index[-1]
flags = detect_flags(latest_ts, latest, cfg)
label, bias, reasons = score_bar(latest, flags, cfg)
price = float(latest["Close"])

today_str = dt.date.today().isoformat()
todays = [j for j in ss.journal if str(j.get("exit_date")) == today_str]
daily_realized = sum(float(j["pnl"]) for j in todays)
loss_count = sum(1 for j in todays if float(j["pnl"]) < 0)
max_daily_loss = -account * max_daily_pct / 100.0


def _date_of(iso):
    return str(iso)[:10] if iso else ""


taken_today = (
    sum(1 for j in ss.journal if _date_of(j.get("open_time")) == today_str)
    + sum(1 for t in ss.open_trades if _date_of(t.get("open_time")) == today_str)
)

lock_reasons = []
if loss_count >= max_losses:
    lock_reasons.append(f"{max_losses}-loss limit reached")
if daily_realized <= max_daily_loss:
    lock_reasons.append("daily loss cap reached")
cooldown_left = 0
if ss.last_loss_time and cooldown_min > 0:
    elapsed = (dt.datetime.now() - ss.last_loss_time).total_seconds() / 60
    cooldown_left = max(0, cooldown_min - elapsed)
LOCKED = bool(lock_reasons)
news_now = flags.get("pre_news")

# Top status banners (always visible — screenshot-friendly)
if LOCKED:
    st.error(f"🔒 **DAILY LOCKOUT ACTIVE** — {', '.join(lock_reasons)}. "
             "Stop trading for today. New paper trades are disabled.")
if news_now:
    st.error("⚠️ **NEWS WINDOW** — a news/event is imminent. Best to stand "
             "aside; if you trade anyway you'll have to explain the override.")
if cooldown_left > 0 and not LOCKED:
    st.warning(f"⏳ **Cooldown:** {cooldown_left:.0f} min left after your last "
               "loss — don't revenge trade.")

tabs = st.tabs(["🟢 Decision", "🛡️ Risk & Sizing", "🧪 Paper Trade & Journal",
                "🔁 Backtest", "📈 Strategy Review", "🎯 Estimator",
                "🧭 AI Coach"])

# ----------------------------- DECISION ------------------------------------ #
with tabs[0]:
    ts_lbl = latest_ts.strftime("%Y-%m-%d %H:%M %Z") if latest_ts.tzinfo \
        else latest_ts.strftime("%Y-%m-%d")
    with st.container(border=True):
        head = st.columns([2, 1, 1])
        with head[0]:
            st.markdown(f"### {ticker}")
            st.caption(f"{interval} · last bar {ts_lbl}")
        head[1].metric("Price", f"{price:,.2f}")
        bmap = {"long": "🟩 Long bias", "short": "🟥 Short bias", "none": "⬜ No bias"}
        head[2].metric("Bias", bmap[bias])

        if label == "Green":
            st.success("## 🟢 GREEN — conditions look favorable")
        elif label == "Yellow":
            st.warning("## 🟡 YELLOW — caution")
        else:
            st.error("## 🔴 RED — stand aside")
        if not clean:
            explain({"Green": "green", "Yellow": "yellow", "Red": "red"}[label])

        st.markdown("**Why this score:**")
        for r in reasons:
            st.write(f"- {r}")

        st.markdown("**Bad-time / condition checks:**")
        fc = st.columns(5)
        items = [("open_5min", "First 5 min"), ("lunch_chop", "Lunch chop"),
                 ("low_volume", "Low volume"), ("pre_news", "News window"),
                 ("low_liquidity", "Low liquidity")]
        for col, (k, name) in zip(fc, items):
            col.write(f"{'🔴' if flags.get(k) else '🟢'} {name}")

    st.markdown("#### Indicators")
    g = st.columns(4)
    g[0].metric("VWAP", f"{latest['VWAP']:.2f}" if pd.notna(latest['VWAP']) else "—",
                delta=f"{price-latest['VWAP']:+.2f}" if pd.notna(latest['VWAP']) else None)
    g[1].metric("EMA 9 / 20", f"{latest['EMA9']:.2f} / {latest['EMA20']:.2f}")
    g[2].metric("EMA 200", f"{latest['EMA200']:.2f}")
    g[3].metric("ATR", f"{latest['ATR']:.3f} ({latest['ATR_pct']*100:.2f}%)")
    rv = latest["RelVol"]
    g[0].metric("Rel. volume", f"{rv:.2f}×" if pd.notna(rv) else "—")

    if not clean:
        c1, c2 = st.columns(2)
        with c1:
            explain("vwap"); explain("ema200"); explain("stack")
        with c2:
            explain("atr"); explain("relvol")
        st.divider()
        st.markdown("**Price with VWAP & EMAs**")
        st.line_chart(data[["Close", "VWAP", "EMA9", "EMA20", "EMA200"]].tail(300))
        st.markdown("**Volume**")
        st.bar_chart(data[["Volume"]].tail(300))

# --------------------------- RISK & SIZING --------------------------------- #
with tabs[1]:
    st.subheader("Position sizing")
    explain("sizing")
    c = st.columns(3)
    # Sensible long-setup defaults from live price; ATR offset with a fallback
    # when ATR is NaN/zero, so entry never lands below stop by default.
    atr_val = float(latest["ATR"]) if pd.notna(latest["ATR"]) else float("nan")
    atr_offset = atr_val if (math.isfinite(atr_val) and atr_val > 0) \
        else max(price * 0.01, 0.01)
    entry_default = safe_price(price, fallback=1.0)
    stop_default = safe_price(price - atr_offset,
                              fallback=max(0.0, entry_default - atr_offset))
    entry = c[0].number_input("Entry price", 0.0, 1e6, entry_default, step=0.01)
    stop = c[1].number_input("Stop price", 0.0, 1e6, stop_default, step=0.01)
    rr = c[2].number_input("Reward:risk", 0.5, 10.0, 2.0, 0.5)

    shares, max_trade_loss, per_share = position_size(account, risk_pct, entry, stop)
    if per_share > 0:
        side = "long" if entry >= stop else "short"
        target = entry + rr * per_share if side == "long" else entry - rr * per_share
        r = st.columns(3)
        r[0].metric("Max loss / trade", f"${max_trade_loss:,.2f}")
        r[1].metric("Suggested shares", f"{shares:,}")
        r[2].metric("Target (≈)", f"{target:.2f}")
        st.caption(f"Side **{side}** · per-share risk ${per_share:.2f} · "
                   f"position value ≈ ${shares*entry:,.0f}")
        if side == "short" and target <= 0:
            st.warning("This short's target prices below zero — that's an "
                       "unrealistic setup (entry far below stop). Check your "
                       "entry and stop.")
        # Store clamped values so the Paper Trade form can never receive a
        # negative default (which would raise StreamlitValueBelowMinError).
        ss["sizing"] = dict(side=side,
                            entry=safe_price(entry, price),
                            stop=safe_price(stop, price),
                            target=safe_price(target, price),
                            shares=max(0, int(shares)), rr=rr)
    else:
        st.info("Set a stop different from entry to size the position.")

    st.divider()
    st.subheader("Today's risk status")
    explain("lockout")
    s = st.columns(4)
    s[0].metric("Realized P&L today", f"${daily_realized:,.2f}")
    s[1].metric("Losses today", f"{loss_count} / {max_losses}")
    s[2].metric("Trades taken today", f"{taken_today} / 3")
    s[3].metric("Daily loss cap", f"${max_daily_loss:,.2f}")
    if LOCKED:
        st.error(f"🔒 Locked out: {', '.join(lock_reasons)}.")
    elif cooldown_left > 0:
        st.warning(f"⏳ Cooldown {cooldown_left:.0f} min left.")
    else:
        st.success("✅ Within all limits.")

# --------------------- PAPER TRADE & JOURNAL ------------------------------- #
with tabs[2]:
    st.subheader("🧪 Paper trade")
    explain("paper")
    st.caption("Simulated only. Opens a pretend position at the chosen price; "
               "closing realizes paper P&L into your journal below.")

    _atr = float(latest["ATR"]) if pd.notna(latest["ATR"]) else float("nan")
    _off = _atr if (math.isfinite(_atr) and _atr > 0) else max(price * 0.01, 0.01)
    sizing = ss.get("sizing", dict(
        side="long" if bias != "short" else "short",
        entry=safe_price(price, 1.0),
        stop=safe_price(price - _off, max(0.0, price - _off)),
        target=safe_price(price + 2 * _off, price),
        shares=0, rr=2.0))

    # 3-trade daily cap (manually overridable)
    cap_cols = st.columns([2, 1])
    cap_cols[0].caption(f"Trades taken today: **{taken_today} / 3**")
    ss.override_3 = cap_cols[1].checkbox("Override 3-trade limit",
                                         value=ss.override_3)
    three_hit = taken_today >= 3 and not ss.override_3

    block_reason = None
    if LOCKED:
        block_reason = "Daily lockout active (loss limit / max losses)."
    elif cooldown_left > 0:
        block_reason = f"Cooldown ({cooldown_left:.0f} min) after a loss."
    elif three_hit:
        block_reason = f"3-trade daily limit reached ({taken_today} today). " \
                       "Tick 'Override' to continue anyway."

    # ===== STAGE 1: set up the trade ===================================== #
    if ss.trade_stage == "entry" or ss.pending_trade is None:
        with st.form("open_paper", clear_on_submit=False):
            cc = st.columns(5)
            side = cc[0].selectbox("Side", ["long", "short"],
                                   index=0 if sizing["side"] == "long" else 1)
            p_entry = cc[1].number_input("Entry", 0.0, 1e6,
                                         safe_price(sizing["entry"], price), step=0.01)
            p_stop = cc[2].number_input("Stop", 0.0, 1e6,
                                        safe_price(sizing["stop"], price), step=0.01)
            p_target = cc[3].number_input("Target", 0.0, 1e6,
                                          safe_price(sizing["target"], price), step=0.01)
            p_shares = cc[4].number_input("Shares", 0, 10_000_000,
                                          max(0, int(sizing.get("shares", 0) or 0)))
            reason = st.text_area(
                "Reason for trade (required)", key="reason_box",
                placeholder="e.g. Pullback to VWAP in an uptrend; EMA9 > EMA20; "
                            "volume picking up; clear stop under the swing low.")
            setup_type = st.selectbox("Setup type", SETUP_TYPES, key="setup_type_box")

            per_share = abs(p_entry - p_stop)
            trade_risk = per_share * p_shares
            allowed_risk = account * risk_pct / 100.0
            risk_over = trade_risk > allowed_risk + 1e-9
            rrr = (abs(p_target - p_entry) / per_share) if per_share > 0 else 0.0
            rc = st.columns(3)
            rc[0].metric("This trade's risk", f"${trade_risk:,.2f}")
            rc[1].metric("Allowed risk", f"${allowed_risk:,.2f}")
            rc[2].metric("Target-to-risk", f"{rrr:.2f}R")
            if risk_over:
                st.error(f"🚫 Risk ${trade_risk:,.2f} is ABOVE your allowed "
                         f"${allowed_risk:,.2f}. This trade is blocked — reduce "
                         "shares or tighten the stop.")

            st.markdown("**Pre-trade checklist — all required:**")
            checks = {}
            for key, lbl in CHECKLIST_ITEMS:
                checks[key] = st.checkbox(lbl, key=f"chk_{key}")

            red_reason = ""
            if label == "Red":
                red_reason = st.text_area(
                    "⚠️ Score is RED — Why am I overriding? (required)",
                    key="red_override_box",
                    placeholder="Explain the specific reason you're taking a "
                                "trade the dashboard says to skip.")

            review_btn = st.form_submit_button("Review trade →", type="primary",
                                               disabled=bool(block_reason))
            if block_reason:
                st.warning(f"Opening disabled — {block_reason}")

            if review_btn and not block_reason:
                errors = []
                if not reason.strip():
                    errors.append("write a reason for the trade")
                if p_shares <= 0 or per_share == 0:
                    errors.append("set shares > 0 and a stop different from entry")
                missing = [lbl for k, lbl in CHECKLIST_ITEMS if not checks[k]]
                if missing:
                    errors.append(f"tick every checklist box ({len(missing)} left)")
                if label == "Red" and not red_reason.strip():
                    errors.append("explain your RED-score override")

                if risk_over:
                    st.error("🚫 Trade blocked: risk exceeds your allowed limit.")
                elif errors:
                    st.error("Can't continue yet — please: " + "; ".join(errors) + ".")
                else:
                    hard_rules = []
                    if label == "Red":
                        hard_rules.append("Traded on RED score")
                    if taken_today >= 3 and ss.override_3:
                        hard_rules.append("Overrode 3-trade limit")
                    rv_open = (float(latest["RelVol"])
                               if pd.notna(latest["RelVol"]) else np.nan)
                    atrp_open = (float(latest["ATR_pct"])
                                 if pd.notna(latest["ATR_pct"]) else np.nan)
                    ss.pending_trade = dict(
                        side=side, entry=p_entry, stop=p_stop, target=p_target,
                        shares=int(p_shares), reason=reason.strip(),
                        setup_type=setup_type,
                        relvol_at_open=rv_open, atr_pct_at_open=atrp_open,
                        news_at_open=("within_window" if news_now else "clear"),
                        red_reason=red_reason.strip(),
                        score_at_open=label, bias_at_open=bias,
                        hard_rules=hard_rules,
                        checks={k: bool(v) for k, v in checks.items()})
                    ss.trade_stage = "review"
                    st.rerun()

    # ===== STAGE 2: review soft rules & confirm ========================= #
    else:
        pend = ss.pending_trade
        st.markdown("#### Review & confirm")
        st.info(f"**{pend['side'].upper()} {pend['shares']} {ticker}** @ "
                f"{pend['entry']:.2f} · stop {pend['stop']:.2f} · "
                f"target {pend['target']:.2f}")

        soft = detect_soft_rules(pend, flags, label, bias)
        explanations = {}
        if soft:
            st.warning("⚠️ This trade triggers **soft rules**. Explain each "
                       "override to continue — or cancel and skip the trade. "
                       "(These are quality warnings, not hard blocks.)")
            for r in soft:
                explanations[r] = st.text_input(f"Why override — {r}?",
                                                 key=f"soft_{_slug(r)}")
        else:
            st.success("✅ No soft rules triggered — this is a clean setup.")

        all_expl = all(explanations[r].strip() for r in soft)
        bcols = st.columns(2)
        confirm = bcols[0].button("✅ Confirm & open paper trade", type="primary",
                                  disabled=not all_expl)
        cancel = bcols[1].button("← Cancel / edit")
        if not all_expl and soft:
            st.caption("Fill in an explanation for every soft rule to enable the "
                       "Confirm button.")

        if cancel:
            ss.pending_trade = None
            ss.trade_stage = "entry"
            st.rerun()

        if confirm and all_expl:
            rules_broken = list(pend["hard_rules"]) + soft
            soft_expl = " | ".join(f"{r}: {explanations[r].strip()}" for r in soft)
            ss.open_trades.append(dict(
                ticker=ticker, side=pend["side"], entry=pend["entry"],
                stop=pend["stop"], target=pend["target"], shares=pend["shares"],
                reason=pend["reason"], score_at_open=pend["score_at_open"],
                bias_at_open=pend["bias_at_open"],
                setup_type=pend.get("setup_type", ""),
                relvol_at_open=pend.get("relvol_at_open"),
                atr_pct_at_open=pend.get("atr_pct_at_open"),
                news_at_open=pend.get("news_at_open", ""),
                rules_broken=";".join(rules_broken),
                red_override_reason=pend["red_reason"],
                soft_explanations=soft_expl,
                open_time=dt.datetime.now().isoformat(timespec="seconds"),
                **pend["checks"]))
            ss.pending_trade = None
            ss.trade_stage = "entry"
            st.success("Paper trade opened.")
            st.rerun()

    if ss.open_trades:
        st.markdown("#### Open paper positions")
        for i, tr in enumerate(list(ss.open_trades)):
            upnl = trade_pnl(tr["side"], tr["entry"], price, tr["shares"])
            rmult = trade_R(tr["side"], tr["entry"], tr["stop"], price)
            box = st.container(border=True)
            top = box.columns([3, 2, 2])
            top[0].write(f"**{tr['ticker']} {tr['side'].upper()}** × {tr['shares']}")
            top[0].caption(f"Entry {tr['entry']:.2f} · stop {tr['stop']:.2f} · "
                           f"target {tr['target']:.2f}")
            top[1].metric("Unrealized P&L", f"${upnl:,.2f}")
            top[2].metric("Open R", f"{rmult:+.2f}")
            box.caption(f"📝 Reason: {tr.get('reason', '—')}")
            if tr.get("rules_broken"):
                box.warning(f"⚠️ Rules broken at open: {tr['rules_broken']}")

            mc = box.columns([2, 3, 1])
            exit_px = mc[0].number_input("Exit @", 0.0, 1e6,
                                         safe_price(price, 1.0),
                                         step=0.01, key=f"exit_{i}")
            mistakes = mc[1].multiselect("Mistake tags (optional)", MISTAKE_TAGS,
                                         key=f"mist_{i}")
            mc[2].write("")
            if mc[2].button("Close", key=f"close_{i}"):
                pnl = trade_pnl(tr["side"], tr["entry"], exit_px, tr["shares"])
                R = trade_R(tr["side"], tr["entry"], tr["stop"], exit_px)
                now_dt = dt.datetime.now()
                entry_rec = dict(
                    ticker=tr["ticker"], side=tr["side"], shares=tr["shares"],
                    entry=tr["entry"], stop=tr["stop"], target=tr["target"],
                    exit=exit_px, pnl=round(pnl, 2), R=round(R, 3),
                    reason=tr.get("reason", ""), mistakes=";".join(mistakes),
                    rules_broken=tr.get("rules_broken", ""),
                    red_override_reason=tr.get("red_override_reason", ""),
                    soft_explanations=tr.get("soft_explanations", ""),
                    setup_type=tr.get("setup_type", ""),
                    relvol_at_open=tr.get("relvol_at_open"),
                    atr_pct_at_open=tr.get("atr_pct_at_open"),
                    news_at_open=tr.get("news_at_open", ""),
                    score_at_open=tr.get("score_at_open", label),
                    bias_at_open=tr.get("bias_at_open", bias),
                    open_time=tr["open_time"],
                    exit_time=now_dt.isoformat(timespec="seconds"),
                    exit_date=now_dt.date().isoformat())
                for k, _lbl in CHECKLIST_ITEMS:       # save checklist answers
                    entry_rec[k] = bool(tr.get(k, False))
                ss.journal.append(entry_rec)
                if pnl < 0:
                    ss.last_loss_time = now_dt
                ss.open_trades.pop(i)
                save_journal(ss.journal)        # auto-save to trades.csv
                st.rerun()
    else:
        st.caption("No open paper positions.")

    st.divider()
    st.markdown("#### 📊 Today's stats")
    ds = daily_stats(todays)
    if ds:
        a = st.columns(3)
        a[0].metric("Total trades today", ds["trades"])
        a[1].metric("Win rate", f"{ds['win_rate']:.0f}%")
        a[2].metric("Total realized P&L", f"${ds['total_pnl']:,.2f}")
        b = st.columns(3)
        b[0].metric("Average R", f"{ds['avg_R']:+.2f}")
        b[1].metric("Biggest win", f"${ds['biggest_win']:,.2f}")
        b[2].metric("Biggest loss", f"${ds['biggest_loss']:,.2f}")
    else:
        st.caption("No trades closed today yet.")

    st.divider()
    st.markdown("#### 📒 Trade journal")
    st.caption(f"Auto-saved to `{JOURNAL_PATH}` and reloaded on startup.")
    if ss.journal:
        full = pd.DataFrame(ss.journal).reindex(columns=JOURNAL_COLUMNS)
        disp = full[[c for c in DISPLAY_COLUMNS if c in full.columns]]
        st.dataframe(disp, use_container_width=True, hide_index=True)

        pnl_num = pd.to_numeric(full["pnl"], errors="coerce").fillna(0.0)
        r_num = pd.to_numeric(full["R"], errors="coerce").fillna(0.0)
        m = st.columns(4)
        m[0].metric("Trades (all)", len(full))
        wins = int((pnl_num > 0).sum())
        m[1].metric("Win rate (all)", f"{wins/len(full)*100:.0f}%")
        m[2].metric("Total P&L (all)", f"${pnl_num.sum():,.2f}")
        m[3].metric("Total R (all)", f"{r_num.sum():+.2f}")

        csv = full.to_csv(index=False).encode("utf-8")
        st.download_button("⬇️ Export journal to CSV (full detail)", csv,
                           file_name=f"paper_journal_{today_str}.csv",
                           mime="text/csv")

        # Reset with confirmation
        if not ss.confirm_reset:
            if st.button("🗑️ Reset journal"):
                ss.confirm_reset = True
                st.rerun()
        else:
            st.warning("⚠️ This permanently deletes **all** saved trades "
                       f"(including `{JOURNAL_PATH}`). This cannot be undone.")
            rc = st.columns(2)
            if rc[0].button("Yes, delete everything", type="primary"):
                ss.journal = []
                ss.last_loss_time = None
                ss.confirm_reset = False
                save_journal(ss.journal)        # removes trades.csv
                st.rerun()
            if rc[1].button("Cancel"):
                ss.confirm_reset = False
                st.rerun()
    else:
        st.caption("No closed paper trades yet. Open and close one above to start "
                   "your journal.")

# ----------------------------- BACKTEST ------------------------------------ #
with tabs[3]:
    st.subheader("Rule backtest (illustrative)")
    explain("backtest")
    bc = st.columns(4)
    use_filter = bc[0].checkbox("Apply bad-time filter", True)
    atr_mult = bc[1].slider("Stop = ATR ×", 0.5, 4.0, 1.5, 0.25)
    bt_rr = bc[2].slider("Reward:risk", 0.5, 5.0, 2.0, 0.5)
    enforce = bc[3].checkbox("Enforce daily limits", True)

    if st.button("Run backtest", type="primary"):
        with st.spinner("Backtesting…"):
            res_f, met_f = run_backtest(data, cfg, use_filter, atr_mult, bt_rr,
                                        enforce, max_losses, max_daily_pct)
            res_n, met_n = run_backtest(data, cfg, False, atr_mult, bt_rr,
                                        enforce, max_losses, max_daily_pct)
        if not met_f:
            st.warning("No qualifying trades. Try more history or looser settings.")
        else:
            st.markdown(f"**Filtered{' (bad-time filter ON)' if use_filter else ''}:**")
            cols = st.columns(len(met_f))
            for col, (k, v) in zip(cols, met_f.items()):
                col.metric(k, v)
            st.line_chart(res_f.assign(Equity_R=res_f["R"].cumsum())
                          .set_index("exit")[["Equity_R"]])
            if met_n:
                st.markdown("**Comparison — no bad-time filter:**")
                st.table(pd.DataFrame({"Filtered": met_f,
                                       "Unfiltered": met_n}).fillna("—"))
            with st.expander("Trade list"):
                st.dataframe(res_f, use_container_width=True, hide_index=True)

# ------------------------- STRATEGY REVIEW --------------------------------- #
with tabs[4]:
    st.subheader("📈 Strategy Review")
    st.caption("Analytics over your saved paper-trade journal. Paper only — no "
               "live orders, no brokerage. The more trades you log, the more "
               "reliable these become.")

    rdf = journal_df(ss.journal)
    if rdf.empty:
        st.info("No closed paper trades yet. Log some in the Paper Trade tab to "
                "unlock your review.")
    else:
        SCORE_COLORS = {"Green": "#2e7d32", "Yellow": "#f9a825", "Red": "#c62828"}

        # ---- Discipline grade ---------------------------------------------
        letter, gscore, breakdown = discipline_grade(rdf)
        with st.container(border=True):
            gc = st.columns([1, 3])
            gcolor = {"A": "#2e7d32", "B": "#558b2f", "C": "#f9a825",
                      "D": "#ef6c00", "F": "#c62828", "—": "#777"}[letter]
            gc[0].markdown(
                f"<div style='text-align:center'>"
                f"<div style='font-size:64px;font-weight:800;color:{gcolor}'>{letter}</div>"
                f"<div style='color:#888'>{gscore}/100</div></div>",
                unsafe_allow_html=True)
            with gc[1]:
                st.markdown("**Discipline grade** — based on how well you "
                            "followed your own rules:")
                for label_, count_, pts_ in breakdown:
                    icon = "✅" if pts_ == 0 else "⚠️"
                    st.write(f"{icon} {label_}: **{count_}** ({pts_:+d} pts)")
        st.caption("Grade reflects process, not profit — you can lose money on a "
                   "disciplined day and still earn an A.")

        st.divider()

        # ---- Equity curve & max drawdown ----------------------------------
        st.markdown("#### Equity curve & drawdown")
        eq = equity_curve(rdf)
        mdd = max_drawdown(eq)
        ec = st.columns(4)
        ec[0].metric("Ending P&L", f"${eq['cum_pnl'].iloc[-1]:,.2f}")
        ec[1].metric("Peak P&L", f"${eq['peak'].max():,.2f}")
        ec[2].metric("Max drawdown", f"${mdd['mdd']:,.2f}")
        ec[3].metric("Max drawdown (R)", f"{mdd['mdd_R']:.2f}R")
        if account:
            st.caption(f"Worst peak-to-trough decline on closed trades — "
                       f"about {abs(mdd['mdd']) / account * 100:.1f}% of your "
                       f"${account:,.0f} account. Max drawdown is the single most "
                       "important survival metric: it's the deepest hole you dug "
                       "before recovering.")
        render_equity(eq)

        st.divider()

        # ---- By score color -----------------------------------------------
        st.markdown("#### Performance by score color at entry")
        bs = by_score(rdf)
        if not bs.empty:
            disp = bs.copy()
            disp["win_rate"] = disp["win_rate"].round(1)
            disp["avg_R"] = disp["avg_R"].round(3)
            disp["total_pnl"] = disp["total_pnl"].round(2)
            st.dataframe(disp.rename(columns={
                "trades": "Trades", "win_rate": "Win %", "avg_R": "Avg R",
                "total_pnl": "Total P&L"}), use_container_width=True)
            cols = st.columns(2)
            colors = [SCORE_COLORS.get(s, "#777") for s in bs.index]
            with cols[0]:
                render_bar(bs.index, bs["win_rate"].values,
                           "Win rate by score color", "Win %", colors)
            with cols[1]:
                render_bar(bs.index, bs["avg_R"].values,
                           "Average R by score color", "Avg R", colors)
            if "Red" in bs.index and bs.loc["Red", "trades"] > 0:
                st.caption("👀 You have trades taken on a RED score — those are "
                           "exactly the ones the dashboard told you to skip.")

        st.divider()

        # ---- By mistake tag -----------------------------------------------
        st.markdown("#### Performance by mistake tag")
        bm = by_mistake_tag(rdf)
        if bm.empty:
            st.caption("No mistake tags logged yet. Tag trades when you close "
                       "them to see which errors cost you most.")
        else:
            disp = bm.copy()
            disp["win_rate"] = disp["win_rate"].round(1)
            disp["avg_R"] = disp["avg_R"].round(3)
            disp["total_pnl"] = disp["total_pnl"].round(2)
            st.dataframe(disp.rename(columns={
                "trades": "Trades", "win_rate": "Win %", "avg_R": "Avg R",
                "total_pnl": "Total P&L"}), use_container_width=True)
            neg = ["#c62828" if v < 0 else "#2e7d32" for v in bm["total_pnl"].values]
            render_bar(bm.index, bm["total_pnl"].values,
                       "Total P&L by mistake tag", "P&L ($)", neg)

        st.divider()

        # ---- Rules broken -------------------------------------------------
        st.markdown("#### Rules broken (hard + soft)")
        n_broken = int(rdf["rules_list"].apply(len).gt(0).sum())
        br = by_rules_broken(rdf)
        mcols = st.columns(2)
        mcols[0].metric("Trades with a rule broken", f"{n_broken} / {len(rdf)}")
        if not br.empty:
            costliest = br["total_pnl"].idxmin()
            mcols[1].metric("Costliest rule", costliest,
                            f"${br.loc[costliest, 'total_pnl']:,.2f}")
        if br.empty:
            st.caption("✅ No rules broken on any logged trade. Keep it up.")
        else:
            disp = br.copy()
            disp["win_rate"] = disp["win_rate"].round(1)
            disp["avg_R"] = disp["avg_R"].round(3)
            disp["total_pnl"] = disp["total_pnl"].round(2)
            st.dataframe(disp.rename(columns={
                "trades": "Trades", "win_rate": "Win %", "avg_R": "Avg R",
                "total_pnl": "Total P&L"}), use_container_width=True)
            colors = ["#c62828" if v < 0 else "#2e7d32" for v in br["total_pnl"].values]
            render_bar(br.index, br["total_pnl"].values,
                       "Total P&L by rule broken (most costly first)", "P&L ($)",
                       colors)
            st.caption("Includes hard overrides (Red score, 3-trade limit) and "
                       "soft rules (lunch chop, first 5 min, news, Yellow score, "
                       "low volume, against trend, sub-2R). Negative P&L means the "
                       "guardrail was right.")

        st.divider()

        # ---- P&L by time of day -------------------------------------------
        st.markdown("#### P&L by time of day (entry hour)")
        ph = pnl_by_hour(rdf)
        if ph.empty:
            st.caption("No timed trades yet.")
        else:
            labels = [f"{int(h):02d}:00" for h in ph.index]
            colors = ["#c62828" if v < 0 else "#2e7d32" for v in ph.values]
            render_bar(labels, ph.values, "Realized P&L by entry hour",
                       "P&L ($)", colors)

        st.divider()

        # ---- Best / worst ticker ------------------------------------------
        st.markdown("#### Best & worst ticker")
        bw = best_worst_ticker(rdf)
        if bw:
            c = st.columns(2)
            c[0].metric(f"Best: {bw['best'][0]}", f"${bw['best'][1]:,.2f}")
            c[1].metric(f"Worst: {bw['worst'][0]}", f"${bw['worst'][1]:,.2f}")
            if len(bw["series"]) > 1:
                colors = ["#c62828" if v < 0 else "#2e7d32"
                          for v in bw["series"].values]
                render_bar(bw["series"].index, bw["series"].values,
                           "Total P&L by ticker", "P&L ($)", colors)

        st.divider()

        # ---- Reason keyword edge ------------------------------------------
        st.markdown("#### Setup-reason keywords")
        rk = reason_keyword_stats(rdf, min_count=2)
        if rk.empty:
            rk = reason_keyword_stats(rdf, min_count=1)
        if rk.empty:
            st.caption("Not enough reason text yet.")
        else:
            disp = rk.copy()
            disp["total_pnl"] = disp["total_pnl"].round(2)
            disp["avg_pnl"] = disp["avg_pnl"].round(2)
            disp["win_rate"] = disp["win_rate"].round(0)
            disp = disp.rename(columns={
                "count": "Uses", "total_pnl": "Total P&L",
                "avg_pnl": "Avg P&L", "win_rate": "Win %"})
            c = st.columns(2)
            c[0].markdown("**Best keywords**")
            c[0].dataframe(disp.sort_values("Total P&L", ascending=False).head(5),
                           use_container_width=True)
            c[1].markdown("**Worst keywords**")
            c[1].dataframe(disp.sort_values("Total P&L").head(5),
                           use_container_width=True)
            st.caption("Keywords are pulled from your 'reason for trade' notes — "
                       "a rough signal of which setups work for you, not proof.")

        st.divider()

        # ---- Weekly summary -----------------------------------------------
        st.markdown("#### Weekly summary")
        ws = weekly_summary(rdf)
        if not ws.empty:
            st.dataframe(ws.rename(columns={
                "week": "Week", "trades": "Trades", "win_rate": "Win %",
                "total_pnl": "Total P&L", "avg_R": "Avg R",
                "top_mistake": "Most common mistake"}),
                use_container_width=True, hide_index=True)
            colors = ["#c62828" if v < 0 else "#2e7d32"
                      for v in ws["total_pnl"].values]
            render_bar(ws["week"].values, ws["total_pnl"].values,
                       "Weekly P&L", "P&L ($)", colors)

# ----------------------------- ESTIMATOR ----------------------------------- #
with tabs[5]:
    st.subheader("🎯 Trade Estimator")
    st.caption("Given a set of conditions, this looks up **your own paper "
               "journal** and reports what actually happened: historical win "
               "rate and expected R. It is your personal history, not a market "
               "prediction — and small samples are noise, not edge.")

    edf = journal_df(ss.journal)
    if edf.empty or len(edf) < 3:
        st.info("Log a few paper trades first (with a setup type) — the "
                "estimator needs history to look up. It gets meaningful around "
                "20–30+ trades per condition.")
    else:
        edf = add_estimator_cols(edf, atr_low, atr_high)

        live_sess = session_bucket(latest_ts.hour) if latest_ts.tzinfo else "Any"
        live = {
            "score_at_open": label,
            "relvol_bucket": relvol_bucket(latest["RelVol"]),
            "atr_bucket": atr_bucket(latest["ATR_pct"], atr_low, atr_high),
            "session": live_sess,
            "bias_at_open": bias,
            "news_at_open": "within_window" if news_now else "clear",
            "ticker": ticker,
            "setup_type": "Any",
        }

        def _sel(colname, label_txt, options, live_key):
            opts = ["Any"] + options
            lv = live.get(live_key, "Any")
            idx = opts.index(lv) if lv in opts else 0
            return st.selectbox(label_txt, opts, index=idx, key=f"est_{colname}")

        st.markdown("**Conditions** (defaults reflect the current live setup):")
        c1 = st.columns(4)
        with c1[0]:
            f_score = _sel("score", "Score color", ["Green", "Yellow", "Red"], "score_at_open")
            f_bias = _sel("bias", "Trend bias", ["long", "short", "none"], "bias_at_open")
        with c1[1]:
            f_relvol = _sel("relvol", "Relative volume", ["Low", "Normal", "High"], "relvol_bucket")
            f_atr = _sel("atr", "ATR (volatility)", ["Low", "Normal", "High"], "atr_bucket")
        with c1[2]:
            f_sess = _sel("session", "Time of day",
                          ["Open (9-10)", "Morning (10-12)", "Midday (12-14)",
                           "Power hour (14-16)", "Other"], "session")
            f_news = _sel("news", "News proximity", ["within_window", "clear"], "news_at_open")
        with c1[3]:
            tickers = sorted([t for t in edf["ticker"].unique() if t])
            f_ticker = _sel("ticker", "Ticker", tickers, "ticker")
            f_setup = _sel("setup", "Setup type", SETUP_TYPES, "setup_type")

        filters = {
            "score_at_open": f_score, "bias_at_open": f_bias,
            "relvol_bucket": f_relvol, "atr_bucket": f_atr,
            "session": f_sess, "news_at_open": f_news,
            "ticker": f_ticker, "setup_type": f_setup,
        }

        levels = estimate_levels(edf, filters)
        headline = next((lv for lv in levels if lv["n"] >= 5), None)
        if headline is None:
            headline = next((lv for lv in levels if lv["n"] >= 1), levels[-1])

        st.divider()
        if headline["n"] == 0:
            st.warning("No matching trades in your journal for any level. Log "
                       "more trades or loosen the conditions.")
        else:
            st.markdown(f"**Estimate — {headline['level']}**")
            mcols = st.columns(3)
            mcols[0].metric("Probability of success", f"{headline['win_rate']:.0f}%",
                            help="Historical win rate of matching trades.")
            mcols[1].metric("Expected R / trade", f"{headline['avg_R']:+.2f}R",
                            help="Average R-multiple of matching trades.")
            mcols[2].metric("Sample size", f"{headline['n']} trades")
            st.caption(
                f"95% confidence the true win rate is between "
                f"**{headline['ci_low']:.0f}%–{headline['ci_high']:.0f}%** · "
                f"reliability: **{reliability_label(headline['n'])}**. "
                "Wide range = not enough data to trust the point estimate.")
            if headline["n"] < 15:
                st.warning("⚠️ Small sample — closer to a guess than a statistic. "
                           "Don't size up on it.")

        st.markdown("**All match levels (specific → broad):**")
        rows = []
        for lv in levels:
            rows.append({
                "Level": lv["level"],
                "Trades": lv["n"],
                "Win %": "—" if lv["win_rate"] is None else f"{lv['win_rate']:.0f}%",
                "95% CI": "—" if lv["n"] == 0 else f"{lv['ci_low']:.0f}–{lv['ci_high']:.0f}%",
                "Expected R": "—" if lv["avg_R"] is None else f"{lv['avg_R']:+.2f}",
                "Total P&L": "—" if lv["total_pnl"] is None else f"${lv['total_pnl']:,.0f}",
                "Reliability": reliability_label(lv["n"]),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        st.caption("If the exact match is thin, read down to a broader level with "
                   "more trades. Paper-trading history does not guarantee "
                   "real-market results.")

# ------------------------------ AI COACH ----------------------------------- #
with tabs[6]:
    st.subheader("🧭 AI Coach")
    st.caption("A plain-language summary of what your journal data shows. It "
               "describes past results only — no predictions, no guarantees — "
               "and flags clearly when a sample is too small to mean much.")

    cdf = journal_df(ss.journal)
    if cdf.empty:
        st.info("No closed paper trades yet. Once you've logged some (with a "
                "setup type), the coach will summarize them here.")
    else:
        if len(cdf) < 5:
            st.warning(f"Only {len(cdf)} closed trade(s) logged. Treat "
                       "everything below as a running log, not a conclusion — "
                       "most patterns need roughly 20–30+ trades before they "
                       "mean anything.")
        report = coach_report(cdf, atr_low, atr_high, dt.date.today().isoformat())
        for sec in report:
            with st.container(border=True):
                st.markdown(f"**{sec['title']}**")
                for line in sec["body"]:
                    st.write(line)
                if sec.get("note"):
                    st.caption(f"⚠️ {sec['note']}")
        st.caption("All figures are drawn directly from your logged paper "
                   "trades. Past results do not predict future results.")

st.divider()
st.caption("⚠️ Paper mode only. No brokerage connection, no live orders, no "
           "profit guarantees. Past results never guarantee future results. "
           "Educational tool — not financial advice.")
