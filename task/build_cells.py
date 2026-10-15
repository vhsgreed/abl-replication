#!/usr/bin/env python3
"""Build the frozen decision cells from public daily price data (Yahoo chart JSON in data/raw).
Output: data/cells.jsonl, one line per (segment, ticker, as_of). Deterministic; rerun must give identical sha256."""
import json, math, pathlib, datetime as dt

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
US = "AAPL MSFT NVDA AMZN GOOGL META JPM V XOM JNJ PG KO WMT HD CVX MRK PEP COST BAC CSCO".split()
EU = ("ASML.AS SAP.DE SIE.DE MC.PA TTE.PA SAN.MC ALV.DE NOVO-B.CO NESN.SW AZN.L "
      "SHEL.L HSBA.L ULVR.L BP.L VOW3.DE BMW.DE OR.PA AIR.PA INGA.AS ABI.BR").split()
BENCH = {"US": ("SPY", "S&P 500 (SPY)"), "EU": ("^STOXX50E", "EURO STOXX 50")}
# 24 grid Fridays: 2026-04-24 .. 2026-10-02. Smoke Fridays lie BEFORE the grid and are never scored.
GRID = [dt.date(2026, 4, 24) + dt.timedelta(weeks=i) for i in range(24)]
SMOKE = [dt.date(2026, 4, 10), dt.date(2026, 4, 17)]


def series(sym):
    d = json.load(open(RAW / f"{sym}.json"))["chart"]["result"][0]
    q = d["indicators"]["quote"][0]
    rows = []
    for t, o, c in zip(d["timestamp"], q["open"], q["close"]):
        if c is None or o is None:
            continue
        day = dt.datetime.fromtimestamp(t + d["meta"].get("gmtoffset", 0), dt.UTC).date()
        rows.append((day, o, c))
    rows.sort()
    return d["meta"], rows


def ret(rows, i, k):
    return 100.0 * (rows[i][2] / rows[i - k][2] - 1.0)


def features(rows, asof):
    i = max(j for j, r in enumerate(rows) if r[0] <= asof)
    assert i >= 60, f"not enough history before {asof}"
    lr = [math.log(rows[j][2] / rows[j - 1][2]) for j in range(i - 19, i + 1)]
    mu = sum(lr) / len(lr)
    vol = math.sqrt(sum((x - mu) ** 2 for x in lr) / (len(lr) - 1)) * math.sqrt(252) * 100
    ma50 = sum(rows[j][2] for j in range(i - 49, i + 1)) / 50
    ytd0 = next(r for r in rows if r[0].year == asof.year)
    return i, {
        "as_of_trading_day": rows[i][0].isoformat(),
        "last_close": round(rows[i][2], 2),
        "ret_1w_pct": round(ret(rows, i, 5), 2), "ret_4w_pct": round(ret(rows, i, 20), 2),
        "ret_12w_pct": round(ret(rows, i, 60), 2),
        "ret_ytd_pct": round(100 * (rows[i][2] / ytd0[2] - 1), 2),
        "vol_20d_ann_pct": round(vol, 1),
        "vs_ma50_pct": round(100 * (rows[i][2] / ma50 - 1), 2),
        "last_10_closes": [[rows[j][0].isoformat(), round(rows[j][2], 2)] for j in range(i - 9, i + 1)],
    }


def outcome(rows, asof):
    """Exploratory only: next week's Monday open -> Friday close (first/last trading day of that week)."""
    mon = asof + dt.timedelta(days=3)
    wk = [r for r in rows if mon <= r[0] <= mon + dt.timedelta(days=4)]
    return round(100 * (wk[-1][2] / wk[0][1] - 1), 3) if wk else None


def main():
    out = []
    bench = {s: series(BENCH[s][0])[1] for s in BENCH}
    for seg, names in (("US", US), ("EU", EU)):
        for sym in names:
            meta, rows = series(sym)
            name = meta.get("longName") or meta.get("shortName") or sym
            for split, days in (("smoke", SMOKE), ("grid", GRID)):
                for asof in days:
                    _, f = features(rows, asof)
                    _, b = features(bench[seg], asof)
                    out.append({
                        "cell_id": f"{seg}|{sym}|{asof.isoformat()}", "split": split, "segment": seg,
                        "ticker": sym, "company": name, "currency": meta.get("currency"),
                        "week": asof.isoformat(), **f,
                        "bench_name": BENCH[seg][1], "bench_ret_1w_pct": b["ret_1w_pct"],
                        "bench_ret_4w_pct": b["ret_4w_pct"],
                        "next_week_return_pct": outcome(rows, asof),
                    })
    p = ROOT / "data" / "cells.jsonl"
    with p.open("w") as fh:
        for r in out:
            fh.write(json.dumps(r, sort_keys=True) + "\n")
    print(len(out), "cells ->", p)


if __name__ == "__main__":
    main()
