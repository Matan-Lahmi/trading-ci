from typing import Optional
from datetime import datetime
from pydantic import BaseModel


class TradeCreate(BaseModel):
    symbol: str
    buy_date: str
    quantity: float
    entry_price: float
    notes: Optional[str] = None


class TradeClose(BaseModel):
    close_price: float
    close_date: str


class TradeResponse(BaseModel):
    id: int
    symbol: str
    buy_date: str
    quantity: float
    entry_price: float
    status: str
    close_price: Optional[float] = None
    close_date: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}
