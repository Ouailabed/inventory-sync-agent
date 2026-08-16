"""Warehouse C as a standalone service. Speaks item / stock_level.

Unlike A and B this one will happily hold a negative stock level, which is how
overselling shows up in the data.

    python -m uvicorn warehouse_c:app --port 8003
"""

import json
import os

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

DATA_FILE = os.path.join(os.path.dirname(__file__), "warehouse_c_data.json")

app = FastAPI(title="Warehouse C")


class StockLevelUpdate(BaseModel):
    stock_level: int


def _load():
    if not os.path.exists(DATA_FILE):
        default = {
            "SKU-001": {"item": "SKU-001", "stock_level": 50},
            "SKU-002": {"item": "SKU-002", "stock_level": -3},
        }
        _save(default)
        return default
    with open(DATA_FILE, "r") as f:
        return json.load(f)


def _save(stock):
    with open(DATA_FILE, "w") as f:
        json.dump(stock, f, indent=2)


@app.get("/stock")
def list_stock():
    return list(_load().values())


@app.get("/stock/{item}")
def get_stock(item: str):
    record = _load().get(item)
    if record is None:
        raise HTTPException(status_code=404, detail=f"{item} not stocked here")
    return record


@app.put("/stock/{item}")
def set_qty(item: str, update: StockLevelUpdate):
    stock = _load()
    if item not in stock:
        raise HTTPException(status_code=404, detail=f"{item} not stocked here")
    stock[item]["stock_level"] = update.stock_level
    _save(stock)
    return stock[item]
