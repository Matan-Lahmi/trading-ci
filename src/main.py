import os
from contextlib import asynccontextmanager
from typing import Optional

import yfinance as yf
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from .database import Trade, get_db, init_db
from .models import TradeClose, TradeCreate, TradeResponse

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Trading Tracker", lifespan=lifespan)


@app.get("/")
def serve_index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.post("/api/trades", response_model=TradeResponse)
def create_trade(trade: TradeCreate, db: Session = Depends(get_db)):
    db_trade = Trade(
        symbol=trade.symbol.upper(),
        buy_date=trade.buy_date,
        quantity=trade.quantity,
        entry_price=trade.entry_price,
        notes=trade.notes,
        status="open",
    )
    db.add(db_trade)
    db.commit()
    db.refresh(db_trade)
    return db_trade


@app.get("/api/trades")
def get_trades(db: Session = Depends(get_db)):
    open_trades = db.query(Trade).filter(Trade.status == "open").all()
    closed_trades = db.query(Trade).filter(Trade.status == "closed").all()
    return {
        "open": [TradeResponse.model_validate(t) for t in open_trades],
        "closed": [TradeResponse.model_validate(t) for t in closed_trades],
    }


@app.put("/api/trades/{trade_id}/close", response_model=TradeResponse)
def close_trade(
    trade_id: int, close_data: TradeClose, db: Session = Depends(get_db)
):
    trade = db.query(Trade).filter(Trade.id == trade_id).first()
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    trade.status = "closed"
    trade.close_price = close_data.close_price
    trade.close_date = close_data.close_date
    db.commit()
    db.refresh(trade)
    return trade


@app.delete("/api/trades/{trade_id}")
def delete_trade(trade_id: int, db: Session = Depends(get_db)):
    trade = db.query(Trade).filter(Trade.id == trade_id).first()
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    db.delete(trade)
    db.commit()
    return {"message": "Trade deleted"}


@app.get("/api/prices/{symbol}")
def get_price(symbol: str):
    try:
        ticker = yf.Ticker(symbol.upper())
        hist = ticker.history(period="2d")
        if hist.empty:
            return {
                "symbol": symbol.upper(),
                "current_price": None,
                "daily_change_pct": None,
            }
        current_price = round(float(hist["Close"].iloc[-1]), 2)
        if len(hist) < 2:
            return {
                "symbol": symbol.upper(),
                "current_price": current_price,
                "daily_change_pct": None,
            }
        prev_price = float(hist["Close"].iloc[-2])
        daily_change_pct = round(
            ((current_price - prev_price) / prev_price) * 100, 2
        )
        return {
            "symbol": symbol.upper(),
            "current_price": current_price,
            "daily_change_pct": daily_change_pct,
        }
    except Exception:
        return {
            "symbol": symbol.upper(),
            "current_price": None,
            "daily_change_pct": None,
        }


@app.get("/api/portfolio/daily-history")
def get_portfolio_daily_history(db: Session = Depends(get_db)):
    try:
        open_trades = (
            db.query(Trade).filter(Trade.status == "open").all()
        )
        if not open_trades:
            return []

        # Fetch price history per unique symbol from its buy_date
        sym_hist: dict = {}
        for trade in open_trades:
            sym = trade.symbol
            if sym in sym_hist:
                continue
            try:
                ticker = yf.Ticker(sym)
                h = ticker.history(start=trade.buy_date)
                if h.empty:
                    sym_hist[sym] = {}
                else:
                    sym_hist[sym] = {
                        idx.strftime("%Y-%m-%d"): round(
                            float(row["Close"]), 2
                        )
                        for idx, row in h.iterrows()
                    }
            except Exception:
                sym_hist[sym] = {}

        # Per-symbol sorted dates and prev-close lookup
        sym_sorted: dict = {}
        sym_prev: dict = {}
        for sym, h in sym_hist.items():
            dates = sorted(h.keys())
            sym_sorted[sym] = dates
            sym_prev[sym] = {
                d: (h[dates[i - 1]] if i > 0 else None)
                for i, d in enumerate(dates)
            }

        # First active market date per trade (for entry-price baseline)
        trade_first: dict = {}
        for trade in open_trades:
            dates = sym_sorted.get(trade.symbol, [])
            trade_first[trade.id] = next(
                (d for d in dates if d >= trade.buy_date), None
            )

        # Trades grouped by symbol
        by_sym: dict = {}
        for t in open_trades:
            by_sym.setdefault(t.symbol, []).append(t)

        # Union of all dates across all symbols
        all_dates = sorted({
            d for h in sym_hist.values() for d in h
        })
        if not all_dates:
            return []

        result = []
        for date in all_dates:
            daily_pnl = 0.0
            total_pnl = 0.0
            breakdown = []

            for sym, h in sym_hist.items():
                day_close = h.get(date)
                if day_close is None:
                    continue
                prev_close = sym_prev[sym].get(date)

                for trade in by_sym.get(sym, []):
                    if trade.buy_date > date:
                        continue
                    # On the trade's first market day use entry as base
                    if date == trade_first.get(trade.id):
                        base = trade.entry_price
                    else:
                        base = (
                            prev_close
                            if prev_close is not None
                            else trade.entry_price
                        )
                    t_daily = (day_close - base) * trade.quantity
                    t_total = (
                        (day_close - trade.entry_price)
                        * trade.quantity
                    )
                    daily_pnl += t_daily
                    total_pnl += t_total
                    breakdown.append({
                        "symbol": sym,
                        "qty": trade.quantity,
                        "entry_price": trade.entry_price,
                        "day_close": day_close,
                        "daily_pnl": round(t_daily, 2),
                        "total_pnl": round(t_total, 2),
                    })

            if breakdown:
                result.append({
                    "date": date,
                    "daily_pnl": round(daily_pnl, 2),
                    "total_pnl_from_entry": round(total_pnl, 2),
                    "breakdown": breakdown,
                })

        return result

    except Exception:
        return []


@app.get("/api/prices/{symbol}/history")
def get_price_history(symbol: str, from_date: Optional[str] = None):
    try:
        ticker = yf.Ticker(symbol.upper())
        hist = (
            ticker.history(start=from_date)
            if from_date
            else ticker.history(period="1y")
        )
        if hist.empty:
            return []
        return [
            {
                "date": idx.strftime("%Y-%m-%d"),
                "close": round(float(row["Close"]), 2),
            }
            for idx, row in hist.iterrows()
        ]
    except Exception:
        return []
