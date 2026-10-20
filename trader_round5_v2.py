import json
from typing import Dict, List

from datamodel import Order, TradingState

TRADABLE = {
    "SNACKPACK_CHOCOLATE", "SNACKPACK_PISTACHIO", "SNACKPACK_RASPBERRY",
    "SNACKPACK_STRAWBERRY", "SNACKPACK_VANILLA",
    "GALAXY_SOUNDS_BLACK_HOLES", "GALAXY_SOUNDS_DARK_MATTER",
    "GALAXY_SOUNDS_PLANETARY_RINGS", "GALAXY_SOUNDS_SOLAR_FLAMES",
    "GALAXY_SOUNDS_SOLAR_WINDS",
    "UV_VISOR_AMBER", "UV_VISOR_MAGENTA", "UV_VISOR_ORANGE",
    "UV_VISOR_RED", "UV_VISOR_YELLOW",
}

CAP: int = 15
EDGE: int = 3


class Trader:
    def run(self, state: TradingState):
        result: Dict[str, List[Order]] = {}

        for product, od in state.order_depths.items():
            if product not in TRADABLE:
                continue
            if not od.buy_orders or not od.sell_orders:
                continue
            result[product] = self._mm(state, product, od)

        return result, 0, ""

    def _mm(self, state, product, od) -> List[Order]:
        orders: List[Order] = []
        best_bid = max(od.buy_orders)
        best_ask = min(od.sell_orders)
        mid = (best_bid + best_ask) / 2.0
        mid_int = int(round(mid))

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

        if buy_cap > 0:
            orders.append(Order(product, bp, buy_cap))
        if sell_cap > 0:
            orders.append(Order(product, sp, -sell_cap))
        return orders
