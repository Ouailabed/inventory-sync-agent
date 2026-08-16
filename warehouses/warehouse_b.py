"""Warehouse B service. Uses product_code / quantity.

    python -m uvicorn warehouse_b:app --port 8002
"""

import json
import os

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

DATA_FILE = os.path.join(os.path.dirname(__file__), "warehouse_b_data.json")

app = FastAPI(title="Warehouse B")


class QuantityUpdate(BaseModel):
    quantity: int


def _load():
    if not os.path.exists(DATA_FILE):
        default = {
            "SKU-001": {"product_code": "SKU-001", "quantity": 45},
            "SKU-003": {"product_code": "SKU-003", "quantity": 8},
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


@app.get("/stock/{product_code}")
def get_stock(product_code: str):
    record = _load().get(product_code)
    if record is None:
        raise HTTPException(status_code=404, detail=f"{product_code} not stocked here")
    return record


@app.put("/stock/{product_code}")
def set_qty(product_code: str, update: QuantityUpdate):
    stock = _load()
    if product_code not in stock:
        raise HTTPException(status_code=404, detail=f"{product_code} not stocked here")
    stock[product_code]["quantity"] = update.quantity
    _save(stock)
    return stock[product_code]
