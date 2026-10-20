import json
import math
from typing import Dict, List

from datamodel import Order, OrderDepth, TradingState

MAF = 10_000


class Trader:
    LIMIT = 80
    MAF = MAF

    WINDOW = 300
    HORIZON = 100
    VOL_EWMA_ALPHA = 0.05
    MAX_SKEW_TICKS = 3
    TARGET_SCALE = 0.85

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

        window = td.get("ipr_mids", [])
        prev_mid = window[-1] if window else mid
        window.append(mid)
        if len(window) > self.WINDOW:
            window = window[-self.WINDOW:]
        td["ipr_mids"] = window

        vol = td.get("ipr_vol", 1.0)
        vol = (1 - self.VOL_EWMA_ALPHA) * vol + self.VOL_EWMA_ALPHA * abs(mid - prev_mid)
        vol = max(vol, 1e-6)
        td["ipr_vol"] = vol

        if len(window) >= self.WINDOW:
            slope = (window[-1] - window[0]) / len(window)
        else:
            slope = 0.0
        confidence = max(-3.0, min(3.0, slope * math.sqrt(len(window)) / vol))
        forward_fair = int(round(mid + slope * self.HORIZON))
        target = int(round(max(-1.0, min(1.0, confidence / 3.0)) * self.TARGET_SCALE * self.LIMIT))

        for price in sorted(od.sell_orders.keys()):
            if price <= forward_fair - 1 and buy_cap > 0:
                qty = min(-od.sell_orders[price], buy_cap)
                if qty > 0:
                    orders.append(Order(product, price, qty))
                    buy_cap -= qty
        for price in sorted(od.buy_orders.keys(), reverse=True):
            if price >= forward_fair + 1 and sell_cap > 0:
                qty = min(od.buy_orders[price], sell_cap)
                if qty > 0:
                    orders.append(Order(product, price, -qty))
                    sell_cap -= qty

        diff = target - pos
        skew = min(self.MAX_SKEW_TICKS, abs(diff))
        if diff > 0:
            buy_p = forward_fair - 3 + skew
            sell_p = forward_fair + 3 + skew
            passive_sell_cap = min(sell_cap, max(0, sell_cap - diff))
            passive_buy_cap = buy_cap
        elif diff < 0:
            buy_p = forward_fair - 3 - skew
            sell_p = forward_fair + 3 - skew
            passive_sell_cap = sell_cap
            passive_buy_cap = min(buy_cap, max(0, buy_cap + diff))
        else:
            buy_p = forward_fair - 3
            sell_p = forward_fair + 3
            passive_sell_cap = sell_cap
            passive_buy_cap = buy_cap

        if passive_buy_cap > 0:
            orders.append(Order(product, int(buy_p), passive_buy_cap))
        if passive_sell_cap > 0:
            orders.append(Order(product, int(sell_p), -passive_sell_cap))
        return orders
