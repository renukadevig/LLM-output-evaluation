#!/usr/bin/env python3
"""Stand-in for a real source-of-truth API, so the API-comparison example runs
offline. In practice you would NOT use this — you'd point reference_command at
your real endpoint, e.g.:

    reference_command: "curl -s https://api.example.com/orders/5512 | jq -r .eta"

Here we just return canned data for an order id."""
import sys

ORDERS = {
    "5512": {"eta": "2026-07-20", "status": "shipped"},
}

order_id = sys.argv[1] if len(sys.argv) > 1 else "5512"
field = sys.argv[2] if len(sys.argv) > 2 else "eta"
print(ORDERS.get(order_id, {}).get(field, "unknown"))
