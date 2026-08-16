"""HTTP client for the three warehouse services."""

import os

import httpx

from normalize import FIELD_NAMES

TIMEOUT_SECONDS = 5.0

# set the env vars to point at other hosts
BASE_URLS = {
    "A": os.environ.get("WAREHOUSE_A_URL", "http://127.0.0.1:8001"),
    "B": os.environ.get("WAREHOUSE_B_URL", "http://127.0.0.1:8002"),
    "C": os.environ.get("WAREHOUSE_C_URL", "http://127.0.0.1:8003"),
}


class WarehouseUnavailable(Exception):
    """Raised when a warehouse can't be reached or doesn't give a usable reply."""


class WarehouseClient:
    def __init__(self, source, base_url):
        self.source = source
        self.base_url = base_url.rstrip("/")
        self.qty_field = FIELD_NAMES[source]["qty"]

    def __repr__(self):
        return f"<WarehouseClient {self.source} at {self.base_url}>"

    def _fail(self, reason):
        return WarehouseUnavailable(f"warehouse {self.source} at {self.base_url}: {reason}")

    def list_stock(self):
        """Return all records, using this warehouse's own field names."""
        try:
            response = httpx.get(f"{self.base_url}/stock", timeout=TIMEOUT_SECONDS)
            response.raise_for_status()
            return response.json()
        except httpx.ConnectError:
            raise self._fail("not responding (is the service running?)")
        except httpx.TimeoutException:
            raise self._fail(f"timed out after {TIMEOUT_SECONDS}s")
        except httpx.HTTPStatusError as e:
            raise self._fail(f"returned HTTP {e.response.status_code}")
        except ValueError:
            # 200 but the body isn't JSON
            raise self._fail("returned a response that isn't JSON")

    def set_qty(self, sku, new_qty):
        """Update the quantity for one SKU."""
        try:
            response = httpx.put(
                f"{self.base_url}/stock/{sku}",
                json={self.qty_field: new_qty},
                timeout=TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            return response.json()
        except httpx.ConnectError:
            raise self._fail("not responding (is the service running?)")
        except httpx.TimeoutException:
            raise self._fail(f"timed out after {TIMEOUT_SECONDS}s")
        except httpx.HTTPStatusError as e:
            raise self._fail(f"rejected the update with HTTP {e.response.status_code}")


WAREHOUSE_CLIENTS = {
    source: WarehouseClient(source, url) for source, url in BASE_URLS.items()
}
