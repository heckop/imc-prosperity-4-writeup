import json
from datamodel import OrderDepth, TradingState, Order
from typing import Dict, List


class Trader:

    def run(self, state: TradingState) -> tuple:
        result: Dict[str, List[Order]] = {}
        trader_data = {}
        if state.traderData:
            try:
                trader_data = json.loads(state.traderData)
            except json.JSONDecodeError:
                trader_data = {}

        for product in state.order_depths:
            if product == "EMERALDS":
                result[product] = self.trade_emeralds(state, product)
            elif product == "TOMATOES":
                result[product] = self.trade_tomatoes(state, product, trader_data)

        return result, 0, json.dumps(trader_data)

    def trade_emeralds(self, state: TradingState, product: str) -> List[Order]:
        LIMIT = 80
        FAIR = 10000
        orders: List[Order] = []
        od = state.order_depths[product]
        pos = state.position.get(product, 0)

        buy_cap = LIMIT - pos
        sell_cap = LIMIT + pos

        for price in sorted(od.sell_orders.keys()):
            if price <= FAIR and buy_cap > 0:
                qty = min(-od.sell_orders[price], buy_cap)
                orders.append(Order(product, price, qty))
                buy_cap -= qty

        for price in sorted(od.buy_orders.keys(), reverse=True):
            if price >= FAIR and sell_cap > 0:
                qty = min(od.buy_orders[price], sell_cap)
                orders.append(Order(product, price, -qty))
                sell_cap -= qty

        if pos > 40:
            buy_price, sell_price = 9995, 10001
        elif pos > 20:
            buy_price, sell_price = 9996, 10002
        elif pos < -40:
            buy_price, sell_price = 9999, 10005
        elif pos < -20:
            buy_price, sell_price = 9998, 10004
        else:
            buy_price, sell_price = 9997, 10003

        if buy_cap > 0:
            orders.append(Order(product, buy_price, buy_cap))
        if sell_cap > 0:
            orders.append(Order(product, sell_price, -sell_cap))

        return orders

    def trade_tomatoes(self, state: TradingState, product: str, td: dict) -> List[Order]:
        LIMIT = 80
        orders: List[Order] = []
        od = state.order_depths[product]
        pos = state.position.get(product, 0)

        best_bid = max(od.buy_orders.keys()) if od.buy_orders else None
        best_ask = min(od.sell_orders.keys()) if od.sell_orders else None
        if best_bid is None or best_ask is None:
            return orders

        mid = (best_bid + best_ask) / 2

        ema = td.get("te", mid)
        ema = ema * 0.8 + mid * 0.2
        td["te"] = ema
        fv = round(ema)

        buy_cap = LIMIT - pos
        sell_cap = LIMIT + pos

        for price in sorted(od.sell_orders.keys()):
            if price <= fv - 1 and buy_cap > 0:
                qty = min(-od.sell_orders[price], buy_cap)
                orders.append(Order(product, price, qty))
                buy_cap -= qty

        for price in sorted(od.buy_orders.keys(), reverse=True):
            if price >= fv + 1 and sell_cap > 0:
                qty = min(od.buy_orders[price], sell_cap)
                orders.append(Order(product, price, -qty))
                sell_cap -= qty

        if pos > 40:
            buy_price, sell_price = fv - 4, fv
        elif pos > 15:
            buy_price, sell_price = fv - 3, fv + 1
        elif pos < -40:
            buy_price, sell_price = fv, fv + 4
        elif pos < -15:
            buy_price, sell_price = fv - 1, fv + 3
        else:
            buy_price, sell_price = fv - 2, fv + 2

        if buy_cap > 0:
            orders.append(Order(product, int(buy_price), buy_cap))
        if sell_cap > 0:
            orders.append(Order(product, int(sell_price), -sell_cap))

        return orders
