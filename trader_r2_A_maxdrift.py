import json
from typing import Dict, List

from datamodel import Order, OrderDepth, TradingState

MAF = 10_000


class Trader:
    LIMIT = 80
    MAF = MAF

    DRIFT_PER_TICK = 0.1
    HORIZON = 200
    EOD_START = 950_000
    EOD_HARD_FLATTEN = 990_000

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
                result[product] = self._trade_pepper(state, product, od)

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

    def _trade_pepper(self, state, product, od) -> List[Order]:
        orders: List[Order] = []
        if not od.buy_orders or not od.sell_orders:
            return orders
        pos = state.position.get(product, 0)
        buy_cap = self.LIMIT - pos
        sell_cap = self.LIMIT + pos
        best_bid = max(od.buy_orders.keys())
        best_ask = min(od.sell_orders.keys())
        mid = (best_bid + best_ask) / 2
        forward_fair = mid + self.DRIFT_PER_TICK * self.HORIZON

        ts = state.timestamp
        in_eod = ts >= self.EOD_START
        hard_flatten = ts >= self.EOD_HARD_FLATTEN

        if hard_flatten:
            if pos > 0 and sell_cap > 0:
                for price in sorted(od.buy_orders.keys(), reverse=True):
                    if pos <= 0:
                        break
                    qty = min(od.buy_orders[price], pos, sell_cap)
                    if qty > 0:
                        orders.append(Order(product, price, -qty))
                        pos -= qty
                        sell_cap -= qty
            elif pos < 0 and buy_cap > 0:
                for price in sorted(od.sell_orders.keys()):
                    if pos >= 0:
                        break
                    qty = min(-od.sell_orders[price], -pos, buy_cap)
                    if qty > 0:
                        orders.append(Order(product, price, qty))
                        pos += qty
                        buy_cap -= qty
            return orders

        for price in sorted(od.sell_orders.keys()):
            if price <= forward_fair - 2 and buy_cap > 0:
                qty = min(-od.sell_orders[price], buy_cap)
                if qty > 0:
                    orders.append(Order(product, price, qty))
                    buy_cap -= qty

        for price in sorted(od.buy_orders.keys(), reverse=True):
            if price >= mid + 25 and sell_cap > 0:
                qty = min(od.buy_orders[price], sell_cap)
                if qty > 0:
                    orders.append(Order(product, price, -qty))
                    sell_cap -= qty

        if in_eod:
            if pos > 0 and sell_cap > 0:
                qty = min(od.buy_orders[best_bid], pos, max(1, sell_cap // 2))
                if qty > 0:
                    orders.append(Order(product, best_bid, -qty))
                    sell_cap -= qty
            return orders

        if buy_cap > 0:
            orders.append(Order(product, best_bid + 1, buy_cap))

        return orders
