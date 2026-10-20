import json
from typing import Dict, List

from datamodel import Order, OrderDepth, TradingState

MAF = 10_000


class Trader:
    LIMIT = 80
    MAF = MAF
    EMA_ALPHA = 0.5
    EOD_TIGHTEN = 980_000

    def run(self, state: TradingState):
        result: Dict[str, List[Order]] = {}
        try:
            td = json.loads(state.traderData) if state.traderData else {}
        except json.JSONDecodeError:
            td = {}

        for product, od in state.order_depths.items():
            if product == "ASH_COATED_OSMIUM":
                result[product] = self._trade_osmium(state, product, od)
            elif product == "INTARIAN_PEPPER_ROOT":
                result[product] = self._trade_pepper(state, product, od, td)

        return result, 0, json.dumps(td)

    def _trade_osmium(self, state, product, od) -> List[Order]:
        FAIR = 10000
        orders: List[Order] = []
        if not od.buy_orders and not od.sell_orders:
            return orders
        pos = state.position.get(product, 0)
        buy_cap = self.LIMIT - pos
        sell_cap = self.LIMIT + pos

        for price in sorted(od.sell_orders.keys()):
            if price < FAIR and buy_cap > 0:
                qty = min(-od.sell_orders[price], buy_cap)
                if qty > 0:
                    orders.append(Order(product, price, qty))
                    buy_cap -= qty
        for price in sorted(od.buy_orders.keys(), reverse=True):
            if price > FAIR and sell_cap > 0:
                qty = min(od.buy_orders[price], sell_cap)
                if qty > 0:
                    orders.append(Order(product, price, -qty))
                    sell_cap -= qty

        if pos >= 40:
            buy_p, sell_p = 9994, 10002
        elif pos >= 20:
            buy_p, sell_p = 9995, 10003
        elif pos <= -40:
            buy_p, sell_p = 9998, 10006
        elif pos <= -20:
            buy_p, sell_p = 9997, 10005
        else:
            buy_p, sell_p = 9996, 10004
        if buy_cap > 0:
            orders.append(Order(product, buy_p, buy_cap))
        if sell_cap > 0:
            orders.append(Order(product, sell_p, -sell_cap))
        return orders

    def _trade_pepper(self, state, product, od, td) -> List[Order]:
        orders: List[Order] = []
        if not od.buy_orders or not od.sell_orders:
            return orders
        pos = state.position.get(product, 0)
        buy_cap = self.LIMIT - pos
        sell_cap = self.LIMIT + pos
        best_bid = max(od.buy_orders.keys())
        best_ask = min(od.sell_orders.keys())
        mid = (best_bid + best_ask) / 2

        ema = td.get("ipr_ema", mid)
        ema = (1 - self.EMA_ALPHA) * ema + self.EMA_ALPHA * mid
        td["ipr_ema"] = ema
        fv = int(round(ema))

        for price in sorted(od.sell_orders.keys()):
            if price <= fv - 1 and buy_cap > 0:
                qty = min(-od.sell_orders[price], buy_cap)
                if qty > 0:
                    orders.append(Order(product, price, qty))
                    buy_cap -= qty
        for price in sorted(od.buy_orders.keys(), reverse=True):
            if price >= fv + 1 and sell_cap > 0:
                qty = min(od.buy_orders[price], sell_cap)
                if qty > 0:
                    orders.append(Order(product, price, -qty))
                    sell_cap -= qty

        if state.timestamp >= self.EOD_TIGHTEN:
            buy_p, sell_p = fv - 1, fv + 1
        elif pos >= 50:
            buy_p, sell_p = fv - 5, fv + 1
        elif pos >= 30:
            buy_p, sell_p = fv - 4, fv + 2
        elif pos <= -50:
            buy_p, sell_p = fv - 1, fv + 5
        elif pos <= -30:
            buy_p, sell_p = fv - 2, fv + 4
        else:
            buy_p, sell_p = fv - 3, fv + 3
        if buy_cap > 0:
            orders.append(Order(product, int(buy_p), buy_cap))
        if sell_cap > 0:
            orders.append(Order(product, int(sell_p), -sell_cap))
        return orders
