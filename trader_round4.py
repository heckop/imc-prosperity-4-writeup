import json
import math
from typing import Dict, List

from datamodel import Order, TradingState

SIGMA: float = 0.0128
LIMIT: int = 80
HP_LIMIT: int = 50
OPT_CAP: int = 30

HP_FAIR: float = 9995.0
HP_BUY_PRICE: int = 9990
HP_SELL_PRICE: int = 10001

VFE_FAIR: float = 5247.0
VFE_BUY_PRICE: int = 5245
VFE_SELL_PRICE: int = 5249

DEEP_ITM_OFFSET: int = 10

VEV_STRIKES: Dict[str, int] = {
    "VEV_4000": 4000, "VEV_4500": 4500, "VEV_5000": 5000,
    "VEV_5100": 5100, "VEV_5200": 5200, "VEV_5300": 5300,
    "VEV_5400": 5400, "VEV_5500": 5500,
    "VEV_6000": 6000, "VEV_6500": 6500,
}

DEEP_ITM = {"VEV_4000", "VEV_4500"}
MIN_TV_FOR_MM: float = 2.0
TAKE_EDGE: float = 1.5


def _N(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_call(S: float, K: float, T: float) -> float:
    if T < 1e-9:
        return max(S - K, 0.0)
    sq = SIGMA * math.sqrt(T)
    d1 = (math.log(S / K) + 0.5 * SIGMA * SIGMA * T) / sq
    return S * _N(d1) - K * _N(d1 - sq)


def bs_delta(S: float, K: float, T: float) -> float:
    if T < 1e-9:
        return 1.0 if S > K else 0.0
    d1 = (math.log(S / K) + 0.5 * SIGMA * SIGMA * T) / (SIGMA * math.sqrt(T))
    return _N(d1)


def solve_T(C: float, S: float, K: float) -> float:
    intrinsic = max(S - K, 0.0)
    if C <= intrinsic + 0.3:
        return 0.0
    lo, hi = 0.0, 20.0
    for _ in range(64):
        m = (lo + hi) / 2.0
        if bs_call(S, K, m) < C:
            lo = m
        else:
            hi = m
    return (lo + hi) / 2.0


class Trader:
    def run(self, state: TradingState):
        result: Dict[str, List[Order]] = {}
        try:
            td = json.loads(state.traderData) if state.traderData else {}
        except json.JSONDecodeError:
            td = {}

        S = self._vfe_mid(state, td)
        T = self._estimate_T(state, S, td)

        net_delta = sum(
            state.position.get(name, 0) * bs_delta(S, K, T)
            for name, K in VEV_STRIKES.items()
        )

        for product, od in state.order_depths.items():
            if product == "HYDROGEL_PACK":
                result[product] = self._trade_hp(state, product, od)
            elif product == "VELVETFRUIT_EXTRACT":
                result[product] = self._trade_vfe(state, product, od, net_delta)
            elif product in VEV_STRIKES:
                result[product] = self._trade_vev(state, product, od, S, T)

        return result, 0, json.dumps(td)

    def _vfe_mid(self, state, td) -> float:
        od = state.order_depths.get("VELVETFRUIT_EXTRACT")
        if od and od.buy_orders and od.sell_orders:
            mid = (max(od.buy_orders) + min(od.sell_orders)) / 2.0
            td["vfe_mid"] = mid
            return mid
        return td.get("vfe_mid", VFE_FAIR)

    def _estimate_T(self, state, S, td) -> float:
        T_new = None
        for ref_name, ref_K in [("VEV_5400", 5400), ("VEV_5300", 5300)]:
            od = state.order_depths.get(ref_name)
            if od and od.buy_orders and od.sell_orders:
                mid = (max(od.buy_orders) + min(od.sell_orders)) / 2.0
                tv = mid - max(S - ref_K, 0.0)
                if tv > 1.0:
                    t = solve_T(mid, S, ref_K)
                    if t > 0.1:
                        T_new = t
                        break
        if T_new is not None:
            if "tte" not in td:
                td["tte"] = T_new
            else:
                td["tte"] = 0.98 * td["tte"] + 0.02 * T_new
        return max(td.get("tte", 5.0), 0.0)

    def _trade_hp(self, state, product, od) -> List[Order]:
        orders: List[Order] = []
        pos = state.position.get(product, 0)
        buy_cap = HP_LIMIT - pos
        sell_cap = HP_LIMIT + pos

        for price in sorted(od.sell_orders):
            if price <= HP_BUY_PRICE and buy_cap > 0:
                qty = min(-od.sell_orders[price], buy_cap)
                if qty > 0:
                    orders.append(Order(product, price, qty))
                    buy_cap -= qty
        for price in sorted(od.buy_orders, reverse=True):
            if price >= HP_SELL_PRICE and sell_cap > 0:
                qty = min(od.buy_orders[price], sell_cap)
                if qty > 0:
                    orders.append(Order(product, price, -qty))
                    sell_cap -= qty

        if pos >= 25:    bp, sp = HP_BUY_PRICE - 1, HP_SELL_PRICE - 1
        elif pos <= -25: bp, sp = HP_BUY_PRICE + 1, HP_SELL_PRICE + 1
        else:            bp, sp = HP_BUY_PRICE, HP_SELL_PRICE

        if buy_cap > 0:
            orders.append(Order(product, bp, buy_cap))
        if sell_cap > 0:
            orders.append(Order(product, sp, -sell_cap))
        return orders

    def _trade_vfe(self, state, product, od, net_delta: float) -> List[Order]:
        orders: List[Order] = []
        if not od.buy_orders or not od.sell_orders:
            return orders
        pos = state.position.get(product, 0)
        buy_cap = LIMIT - pos
        sell_cap = LIMIT + pos

        for price in sorted(od.sell_orders):
            if price <= VFE_BUY_PRICE and buy_cap > 0:
                qty = min(-od.sell_orders[price], buy_cap)
                if qty > 0:
                    orders.append(Order(product, price, qty))
                    buy_cap -= qty
        for price in sorted(od.buy_orders, reverse=True):
            if price >= VFE_SELL_PRICE and sell_cap > 0:
                qty = min(od.buy_orders[price], sell_cap)
                if qty > 0:
                    orders.append(Order(product, price, -qty))
                    sell_cap -= qty

        hedge_skew = int(max(-2, min(2, round(net_delta / 20.0))))
        eff_pos = pos + hedge_skew

        if eff_pos >= 30:    bp, sp = VFE_BUY_PRICE - 1, VFE_SELL_PRICE - 1
        elif eff_pos <= -30: bp, sp = VFE_BUY_PRICE + 1, VFE_SELL_PRICE + 1
        else:                bp, sp = VFE_BUY_PRICE, VFE_SELL_PRICE

        if buy_cap > 0:
            orders.append(Order(product, bp, buy_cap))
        if sell_cap > 0:
            orders.append(Order(product, sp, -sell_cap))
        return orders

    def _trade_vev(self, state, product, od, S: float, T: float) -> List[Order]:
        if product in DEEP_ITM:
            return self._trade_deep_itm_vev(state, product, od, S)
        return self._trade_otm_vev(state, product, od, S, T)

    def _trade_deep_itm_vev(self, state, product, od, S: float) -> List[Order]:
        orders: List[Order] = []
        if not od.buy_orders or not od.sell_orders:
            return orders
        K = VEV_STRIKES[product]
        pos = state.position.get(product, 0)
        buy_cap = min(OPT_CAP - pos, LIMIT - pos)
        sell_cap = min(OPT_CAP + pos, LIMIT + pos)
        intrinsic = max(S - K, 0.0)
        bid_p = int(round(intrinsic - DEEP_ITM_OFFSET))
        ask_p = int(round(intrinsic + DEEP_ITM_OFFSET))

        best_ask = min(od.sell_orders)
        best_bid = max(od.buy_orders)
        if best_ask <= bid_p and buy_cap > 0:
            qty = min(-od.sell_orders[best_ask], buy_cap)
            if qty > 0:
                orders.append(Order(product, best_ask, qty))
                buy_cap -= qty
        if best_bid >= ask_p and sell_cap > 0:
            qty = min(od.buy_orders[best_bid], sell_cap)
            if qty > 0:
                orders.append(Order(product, best_bid, -qty))
                sell_cap -= qty

        if buy_cap > 0:
            orders.append(Order(product, bid_p, buy_cap))
        if sell_cap > 0:
            orders.append(Order(product, ask_p, -sell_cap))
        return orders

    def _trade_otm_vev(self, state, product, od, S: float, T: float) -> List[Order]:
        orders: List[Order] = []
        if not od.buy_orders or not od.sell_orders:
            return orders
        K = VEV_STRIKES[product]
        pos = state.position.get(product, 0)
        buy_cap = min(OPT_CAP - pos, LIMIT - pos)
        sell_cap = min(OPT_CAP + pos, LIMIT + pos)

        intrinsic = max(S - K, 0.0)
        fair = max(bs_call(S, K, T), intrinsic)
        tv = fair - intrinsic

        best_ask = min(od.sell_orders)
        best_bid = max(od.buy_orders)

        if best_ask < intrinsic - 0.5 and buy_cap > 0:
            qty = min(-od.sell_orders[best_ask], buy_cap)
            if qty > 0:
                orders.append(Order(product, best_ask, qty))
                buy_cap -= qty

        if tv < MIN_TV_FOR_MM:
            return orders

        if best_bid >= fair + TAKE_EDGE and sell_cap > 0:
            qty = min(od.buy_orders[best_bid], sell_cap)
            if qty > 0:
                orders.append(Order(product, best_bid, -qty))
                sell_cap -= qty

        if best_ask <= fair - TAKE_EDGE * 1.5 and buy_cap > 0:
            qty = min(-od.sell_orders[best_ask], buy_cap)
            if qty > 0:
                orders.append(Order(product, best_ask, qty))
                buy_cap -= qty

        bid_p = max(int(fair) - 1, int(intrinsic))
        ask_p = max(int(fair) + 1, int(intrinsic) + 1)
        bid_p = min(bid_p, best_ask - 1)
        ask_p = max(ask_p, best_bid + 1)

        if buy_cap > 0:
            orders.append(Order(product, bid_p, buy_cap))
        if sell_cap > 0:
            orders.append(Order(product, ask_p, -sell_cap))
        return orders
