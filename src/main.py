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
