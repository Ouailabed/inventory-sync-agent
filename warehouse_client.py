"""Talks to the three warehouse services over HTTP.

Deliberately exposes the same two methods the old importable modules did —
list_stock() and set_qty() — so the detection and execution code didn't need
restructuring when the warehouses moved out of process. The failure handling
that was built for "this file is unreadable" already covers "this service is
unreachable", because both arrive at the same place as an exception.

httpx rather than requests, for one reason above the others: requests has no
default timeout, so a warehouse that accepts a connection and then never replies
would hang the agent forever — and since the agent holds a lock while it runs,
every later run would be refused too. One sick warehouse would take the whole
system down. The timeout below is set explicitly regardless, but a library whose
default is "wait forever" is the wrong default to build an unattended agent on.
"""

import os

import httpx

from normalize import FIELD_NAMES

# Generous enough for a warehouse having a slow moment, short enough that the
# agent doesn't sit on the lock all day waiting for a service that's wedged.
TIMEOUT_SECONDS = 5.0

# Overridable so the same code can point at real hosts instead of localhost.
BASE_URLS = {
    "A": os.environ.get("WAREHOUSE_A_URL", "http://127.0.0.1:8001"),
    "B": os.environ.get("WAREHOUSE_B_URL", "http://127.0.0.1:8002"),
    "C": os.environ.get("WAREHOUSE_C_URL", "http://127.0.0.1:8003"),
}


class WarehouseUnavailable(Exception):
    """We couldn't get a usable answer out of a warehouse.

    One exception type for every transport-level failure, because the agent's
    response to all of them is identical: treat that warehouse as unreadable for
    this run, and — crucially — don't conclude anything about what it stocks.
    """


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
        """Every record this warehouse holds, in its own native field names."""
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
            # A 200 whose body isn't JSON — a proxy error page, say. The status
            # said fine, the content isn't, and .json() is where that surfaces.
            raise self._fail("returned a response that isn't JSON")

    def set_qty(self, sku, new_qty):
        """Write a corrected quantity, using this warehouse's own field name."""
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
