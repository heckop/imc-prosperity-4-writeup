import json
from typing import Dict, List

from datamodel import Order, TradingState

PRIME = {
    "SNACKPACK_CHOCOLATE", "SNACKPACK_PISTACHIO", "SNACKPACK_RASPBERRY",
    "SNACKPACK_STRAWBERRY", "SNACKPACK_VANILLA",
}

STRONG = {
    "GALAXY_SOUNDS_BLACK_HOLES", "GALAXY_SOUNDS_DARK_MATTER",
    "GALAXY_SOUNDS_PLANETARY_RINGS", "GALAXY_SOUNDS_SOLAR_FLAMES",
    "GALAXY_SOUNDS_SOLAR_WINDS",
    "UV_VISOR_AMBER", "UV_VISOR_MAGENTA", "UV_VISOR_ORANGE",
    "UV_VISOR_RED", "UV_VISOR_YELLOW",
    "OXYGEN_SHAKE_CHOCOLATE", "OXYGEN_SHAKE_EVENING_BREATH",
    "OXYGEN_SHAKE_GARLIC", "OXYGEN_SHAKE_MINT",
    "OXYGEN_SHAKE_MORNING_BREATH",
}

MARGINAL = {
    "PANEL_1X2", "PANEL_1X4", "PANEL_2X2", "PANEL_2X4", "PANEL_4X4",
    "TRANSLATOR_ASTRO_BLACK", "TRANSLATOR_ECLIPSE_CHARCOAL",
    "TRANSLATOR_GRAPHITE_MIST", "TRANSLATOR_SPACE_GRAY",
    "TRANSLATOR_VOID_BLUE",
    "SLEEP_POD_COTTON", "SLEEP_POD_LAMB_WOOL", "SLEEP_POD_NYLON",
    "SLEEP_POD_POLYESTER", "SLEEP_POD_SUEDE",
}

PEBBLES = {
    "PEBBLES_XS", "PEBBLES_S", "PEBBLES_M", "PEBBLES_L", "PEBBLES_XL",
}

TRADABLE = PRIME | STRONG | MARGINAL | PEBBLES

CAP_PRIME: int = 40
CAP_STRONG: int = 30
CAP_MARGINAL: int = 20
CAP_PEBBLES: int = 25

EDGE_PRIME: int = 3
EDGE_STRONG: int = 3
EDGE_MARGINAL: int = 2
EDGE_PEBBLES_NORMAL: int = 3
EDGE_PEBBLES_XL: int = 6

EMA_ALPHA: float = 0.10


class Trader:
    def run(self, state: TradingState):
        result: Dict[str, List[Order]] = {}
        try:
            td = json.loads(state.traderData) if state.traderData else {}
        except json.JSONDecodeError:
            td = {}

        emas = self._update_emas(state, td)

        for product, od in state.order_depths.items():
            if product not in TRADABLE:
                continue
            cap, edge = self._params_for(product)
            result[product] = self._ema_mm(state, product, od, emas, cap, edge)

        return result, 0, json.dumps(td)

    def _params_for(self, product: str):
        if product in PRIME:
            return CAP_PRIME, EDGE_PRIME
        if product in STRONG:
            return CAP_STRONG, EDGE_STRONG
        if product in MARGINAL:
            return CAP_MARGINAL, EDGE_MARGINAL
        if product == "PEBBLES_XL":
            return CAP_PEBBLES, EDGE_PEBBLES_XL
        if product in PEBBLES:
            return CAP_PEBBLES, EDGE_PEBBLES_NORMAL
        return 0, 0

    def _update_emas(self, state: TradingState, td: dict) -> Dict[str, float]:
        emas = td.setdefault("emas", {})
        for product, od in state.order_depths.items():
            if product not in TRADABLE:
                continue
            if not od.buy_orders or not od.sell_orders:
                continue
            mid = (max(od.buy_orders) + min(od.sell_orders)) / 2.0
            if product not in emas:
                emas[product] = mid
            else:
                emas[product] = (1 - EMA_ALPHA) * emas[product] + EMA_ALPHA * mid
        return emas

    def _ema_mm(self, state, product, od, emas, cap: int, edge: int) -> List[Order]:
        orders: List[Order] = []
        if not od.buy_orders or not od.sell_orders:
            return orders
        if product not in emas:
            return orders

        fv = emas[product]
        fv_int = int(round(fv))
        pos = state.position.get(product, 0)
        buy_cap = cap - pos
        sell_cap = cap + pos
        best_bid = max(od.buy_orders)
        best_ask = min(od.sell_orders)

        for price in sorted(od.sell_orders):
            if price <= fv_int - edge and buy_cap > 0:
                qty = min(-od.sell_orders[price], buy_cap)
                if qty > 0:
                    orders.append(Order(product, price, qty))
                    buy_cap -= qty
        for price in sorted(od.buy_orders, reverse=True):
            if price >= fv_int + edge and sell_cap > 0:
                qty = min(od.buy_orders[price], sell_cap)
                if qty > 0:
                    orders.append(Order(product, price, -qty))
                    sell_cap -= qty

        half = cap // 2
        if pos >= half:
            bp, sp = fv_int - edge - 1, fv_int + edge - 1
        elif pos <= -half:
            bp, sp = fv_int - edge + 1, fv_int + edge + 1
        else:
            bp, sp = fv_int - edge, fv_int + edge

        bp = min(bp, best_ask - 1)
        sp = max(sp, best_bid + 1)

        if buy_cap > 0:
            orders.append(Order(product, bp, buy_cap))
        if sell_cap > 0:
            orders.append(Order(product, sp, -sell_cap))
        return orders
