"""Warehouse A as a standalone service. Speaks sku_id / qty.

Runs on its own port, in its own process, with its own storage. It has no idea
warehouses B and C exist — which is the point of the exercise.

    python -m uvicorn warehouse_a:app --port 8001
"""

import json
import os

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

DATA_FILE = os.path.join(os.path.dirname(__file__), "warehouse_a_data.json")

app = FastAPI(title="Warehouse A")


class QtyUpdate(BaseModel):
    qty: int


def _load():
    if not os.path.exists(DATA_FILE):
        default = {
            "SKU-001": {"sku_id": "SKU-001", "qty": 50},
            "SKU-002": {"sku_id": "SKU-002", "qty": 12},
        }
        _save(default)
        return default
    with open(DATA_FILE, "r") as f:
        return json.load(f)


def _save(stock):
    with open(DATA_FILE, "w") as f:
        json.dump(stock, f, indent=2)


# Read from disk on every request rather than caching in memory. Slower, but the
# agent is allowed to see edits made to the file underneath it, and an in-memory
# copy was the source of a bug earlier in this project where corrections looked
# applied but never persisted.
@app.get("/stock")
def list_stock():
    return list(_load().values())


@app.get("/stock/{sku_id}")
def get_stock(sku_id: str):
    record = _load().get(sku_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"{sku_id} not stocked here")
    return record


@app.put("/stock/{sku_id}")
def set_qty(sku_id: str, update: QtyUpdate):
    stock = _load()
    if sku_id not in stock:
        raise HTTPException(status_code=404, detail=f"{sku_id} not stocked here")
    stock[sku_id]["qty"] = update.qty
    _save(stock)
    return stock[sku_id]
