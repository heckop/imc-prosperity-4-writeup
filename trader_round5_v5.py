import json
from typing import Dict, List

from datamodel import Order, TradingState

CAP: int = 10
EDGE: int = 5
LOOKBACK: int = 5
THRESHOLD: int = 20


class Trader:
    def run(self, state: TradingState):
        result: Dict[str, List[Order]] = {}
        try:
            td = json.loads(state.traderData) if state.traderData else {}
        except json.JSONDecodeError:
            td = {}

        mids_history = td.setdefault("mids", {})

        for product, od in state.order_depths.items():
            if not od.buy_orders or not od.sell_orders:
                continue
            result[product] = self._mm(state, product, od, mids_history)

        return result, 0, json.dumps(td)

    def _mm(self, state, product, od, mids_history) -> List[Order]:
        orders: List[Order] = []
        best_bid = max(od.buy_orders)
        best_ask = min(od.sell_orders)
        mid = (best_bid + best_ask) / 2.0
        mid_int = int(round(mid))

        window = mids_history.setdefault(product, [])
        window.append(mid)
        if len(window) > LOOKBACK + 1:
            del window[: len(window) - (LOOKBACK + 1)]

        momentum = window[-1] - window[0] if len(window) > LOOKBACK else 0.0

        pos = state.position.get(product, 0)
        buy_cap = CAP - pos
        sell_cap = CAP + pos

        bp = mid_int - EDGE
        sp = mid_int + EDGE

        if pos >= CAP // 2:
            bp -= 1
            sp -= 1
        elif pos <= -CAP // 2:
            bp += 1
            sp += 1

        bp = min(bp, best_ask - 1)
        sp = max(sp, best_bid + 1)

        skip_bid = momentum <= -THRESHOLD
        skip_ask = momentum >= THRESHOLD

        if buy_cap > 0 and not skip_bid:
            orders.append(Order(product, bp, buy_cap))
        if sell_cap > 0 and not skip_ask:
            orders.append(Order(product, sp, -sell_cap))
        return orders
