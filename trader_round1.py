import json
from datamodel import OrderDepth, TradingState, Order
from typing import Dict, List


class Trader:

    LIMIT = 80

    def run(self, state: TradingState) -> tuple:
        result: Dict[str, List[Order]] = {}
        td = {}
        if state.traderData:
            try:
                td = json.loads(state.traderData)
            except json.JSONDecodeError:
                td = {}

        for product in state.order_depths:
            if product == "ASH_COATED_OSMIUM":
                result[product] = self.trade_ako(state, product)
            elif product == "INTARIAN_PEPPER_ROOT":
                result[product] = self.trade_ipr(state, product, td)

        return result, 0, json.dumps(td)

    def trade_ako(self, state: TradingState, product: str) -> List[Order]:
        FAIR = 10000
        orders: List[Order] = []
        od = state.order_depths[product]
        pos = state.position.get(product, 0)

        if not od.buy_orders and not od.sell_orders:
            return orders

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

        if pos > 40:
            buy_price, sell_price = 9994, 10002
        elif pos > 20:
            buy_price, sell_price = 9995, 10003
        elif pos < -40:
            buy_price, sell_price = 9998, 10006
        elif pos < -20:
            buy_price, sell_price = 9997, 10005
        else:
            buy_price, sell_price = 9996, 10004

        if buy_cap > 0:
            orders.append(Order(product, buy_price, buy_cap))
        if sell_cap > 0:
            orders.append(Order(product, sell_price, -sell_cap))

        return orders

    def trade_ipr(self, state: TradingState, product: str, td: dict) -> List[Order]:
        orders: List[Order] = []
        od = state.order_depths[product]
        pos = state.position.get(product, 0)

        best_bid = max(od.buy_orders.keys()) if od.buy_orders else None
        best_ask = min(od.sell_orders.keys()) if od.sell_orders else None
        if best_bid is None or best_ask is None:
            return orders

        mid = (best_bid + best_ask) / 2

        ema = td.get("ipr_ema", mid)
        ema = ema * 0.5 + mid * 0.5
        td["ipr_ema"] = ema
        fv = round(ema)

        buy_cap = self.LIMIT - pos
        sell_cap = self.LIMIT + pos

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

        if pos > 50:
            buy_price, sell_price = fv - 5, fv + 1
        elif pos > 30:
            buy_price, sell_price = fv - 4, fv + 2
        elif pos < -50:
            buy_price, sell_price = fv - 1, fv + 5
        elif pos < -30:
            buy_price, sell_price = fv - 2, fv + 4
        else:
            buy_price, sell_price = fv - 3, fv + 3

        if buy_cap > 0:
            orders.append(Order(product, int(buy_price), buy_cap))
        if sell_cap > 0:
            orders.append(Order(product, int(sell_price), -sell_cap))

        return orders
