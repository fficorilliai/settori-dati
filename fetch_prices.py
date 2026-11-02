"""Scarica i prezzi degli ETF per settore con yfinance e scrive data.json.

Uso locale:
    pip install yfinance
    python fetch_prices.py
"""
import datetime as dt
import json
import sys
import time

import yfinance as yf

STALE_AFTER_DAYS = 4          # oltre questa soglia il dato e' segnalato come vecchio
WAITS = [10, 30, 60]          # secondi di attesa tra un tentativo e il successivo (4 tentativi)
PAUSE_BETWEEN_TICKERS = 2     # pausa gentile tra un ETF e l'altro


def pct(new, old):
    if old in (None, 0):
        return None
    return round((new / old - 1) * 100, 2)


def fetch_close(ticker, today):
    """Scarica le chiusure riprovando in caso di errore.

    Restituisce (serie_chiusure, numero_tentativi). Se alla fine non ci riesce,
    solleva un errore che dice la causa vera (blocco, ticker vuoto, ecc.).
    """
    last_error = "errore sconosciuto"
    tries = len(WAITS) + 1
    for attempt in range(1, tries + 1):
        try:
            df = yf.Ticker(ticker).history(start=f"{today.year - 1}-12-15", auto_adjust=True)
            if df is not None and not df.empty and "Close" in df:
                close = df["Close"].dropna()
                if len(close) >= 2:
                    return close, attempt
            last_error = "Yahoo ha risposto senza prezzi (ticker sbagliato oppure richiesta bloccata)"
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
        print(f"  {ticker}: tentativo {attempt}/{tries} fallito - {last_error}")
        if attempt < tries:
            time.sleep(WAITS[attempt - 1])
    raise RuntimeError(last_error)


def analyze(ticker, today):
    close, attempts = fetch_close(ticker, today)
    last, prev = close.iloc[-1], close.iloc[-2]
    last_date = close.index[-1].date()
    week_ago = close.iloc[-6] if len(close) >= 6 else None
    prev_year = close[close.index.year < today.year]
    year_base = prev_year.iloc[-1] if len(prev_year) else None

    return {
        "last_close": round(float(last), 3),
        "last_date": last_date.isoformat(),
        "stale": (today - last_date).days > STALE_AFTER_DAYS,
        "change_1d_pct": pct(last, prev),
        "change_1w_pct": pct(last, week_ago),
        "change_ytd_pct": pct(last, year_base),
        "attempts": attempts,
    }


def main():
    with open("config.json", encoding="utf-8") as f:
        config = json.load(f)

    today = dt.date.today()
    now = dt.datetime.now(dt.timezone.utc)
    output = {
        "generated_at": now.isoformat(timespec="seconds"),
        "yfinance_version": getattr(yf, "__version__", "sconosciuta"),
        "sectors": {},
    }

    ok, failed = 0, 0
    for sector, etfs in config.items():
        rows = []
        for etf in etfs:
            row = {"name": etf["name"], "isin": etf["isin"], "ticker": etf["ticker"]}
            print(f"{sector} - {etf['ticker']}")
            try:
                row.update(analyze(etf["ticker"], today))
                ok += 1
            except Exception as exc:  # un ETF che fallisce non deve bloccare gli altri
                row["error"] = str(exc)
                failed += 1
            rows.append(row)
            time.sleep(PAUSE_BETWEEN_TICKERS)
        output["sectors"][sector] = rows

    output["summary"] = {"ok": ok, "failed": failed}

    # Scrive sempre il file, cosi' anche gli errori restano leggibili
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"data.json scritto: {ok} ok, {failed} falliti")

    # Se non e' riuscito nessun ETF, il job deve risultare rosso (non verde con file vuoto)
    if ok == 0:
        print("NESSUN ETF scaricato: esco con errore")
        sys.exit(1)


if __name__ == "__main__":
    main()
