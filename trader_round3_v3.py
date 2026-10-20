import json
import math
from typing import Dict, List

from datamodel import Order, TradingState

SIGMA: float = 0.0128
LIMIT: int = 80
HP_LIMIT: int = 40
OPT_CAP: int = 30
HP_EMA_ALPHA: float = 0.15
VFE_EMA_ALPHA: float = 0.3

HP_TREND_LOOKBACK: int = 3
HP_TREND_THRESHOLD: float = 6.0

VEV_STRIKES: Dict[str, int] = {
    "VEV_4000": 4000, "VEV_4500": 4500, "VEV_5000": 5000,
    "VEV_5100": 5100, "VEV_5200": 5200, "VEV_5300": 5300,
    "VEV_5400": 5400, "VEV_5500": 5500,
    "VEV_6000": 6000, "VEV_6500": 6500,
}

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

        hp_fv, hp_momentum = self._update_hp_ema(state, td)
        S = self._update_vfe_ema(state, td)
        T = self._estimate_T(state, S, td)

        net_delta = sum(
            state.position.get(name, 0) * bs_delta(S, K, T)
            for name, K in VEV_STRIKES.items()
        )

        for product, od in state.order_depths.items():
            if product == "HYDROGEL_PACK":
                result[product] = self._trade_hp(state, product, od, hp_fv, hp_momentum)
            elif product == "VELVETFRUIT_EXTRACT":
                result[product] = self._trade_vfe(state, product, od, S, net_delta)
            elif product in VEV_STRIKES:
                result[product] = self._trade_vev(state, product, od, S, T)

        return result, 0, json.dumps(td)

    def _update_hp_ema(self, state: TradingState, td: dict):
        od = state.order_depths.get("HYDROGEL_PACK")
        momentum = 0.0
        if od and od.buy_orders and od.sell_orders:
            mid = (max(od.buy_orders) + min(od.sell_orders)) / 2.0
            if "hp_ema" not in td:
                td["hp_ema"] = mid
            else:
                td["hp_ema"] = (1 - HP_EMA_ALPHA) * td["hp_ema"] + HP_EMA_ALPHA * mid

            window = td.get("hp_mids", [])
            window.append(mid)
            if len(window) > HP_TREND_LOOKBACK + 1:
                window = window[-(HP_TREND_LOOKBACK + 1):]
            td["hp_mids"] = window
            if len(window) > HP_TREND_LOOKBACK:
                momentum = window[-1] - window[0]

        return td.get("hp_ema", 10_000.0), momentum

    def _update_vfe_ema(self, state: TradingState, td: dict) -> float:
        od = state.order_depths.get("VELVETFRUIT_EXTRACT")
        if od and od.buy_orders and od.sell_orders:
            mid = (max(od.buy_orders) + min(od.sell_orders)) / 2.0
            if "vfe_ema" not in td:
                td["vfe_ema"] = mid
            else:
                td["vfe_ema"] = (1 - VFE_EMA_ALPHA) * td["vfe_ema"] + VFE_EMA_ALPHA * mid
        return td.get("vfe_ema", 5_250.0)

    def _estimate_T(self, state: TradingState, S: float, td: dict) -> float:
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

    def _trade_hp(self, state, product, od, fv: float, momentum: float) -> List[Order]:
        orders: List[Order] = []
        pos = state.position.get(product, 0)
        buy_cap = HP_LIMIT - pos
        sell_cap = HP_LIMIT + pos
        fv_int = int(round(fv))

        for price in sorted(od.sell_orders):
            if price < fv_int and buy_cap > 0:
                qty = min(-od.sell_orders[price], buy_cap)
                if qty > 0:
                    orders.append(Order(product, price, qty))
                    buy_cap -= qty
        for price in sorted(od.buy_orders, reverse=True):
            if price > fv_int and sell_cap > 0:
                qty = min(od.buy_orders[price], sell_cap)
                if qty > 0:
                    orders.append(Order(product, price, -qty))
                    sell_cap -= qty

        if pos >= 30:    bp, sp = fv_int - 4, fv_int + 2
        elif pos >= 15:  bp, sp = fv_int - 3, fv_int + 2
        elif pos <= -30: bp, sp = fv_int - 2, fv_int + 4
        elif pos <= -15: bp, sp = fv_int - 2, fv_int + 3
        else:            bp, sp = fv_int - 3, fv_int + 3

        skip_bid = momentum <= -HP_TREND_THRESHOLD
        skip_ask = momentum >= HP_TREND_THRESHOLD

        if buy_cap > 0 and not skip_bid:
            orders.append(Order(product, bp, buy_cap))
        if sell_cap > 0 and not skip_ask:
            orders.append(Order(product, sp, -sell_cap))
        return orders

    def _trade_vfe(self, state, product, od, S: float, net_delta: float) -> List[Order]:
        orders: List[Order] = []
        if not od.buy_orders or not od.sell_orders:
            return orders
        pos = state.position.get(product, 0)
        buy_cap = LIMIT - pos
        sell_cap = LIMIT + pos
        fv = int(round(S))

        for price in sorted(od.sell_orders):
            if price <= fv - 1 and buy_cap > 0:
                qty = min(-od.sell_orders[price], buy_cap)
                if qty > 0:
                    orders.append(Order(product, price, qty))
                    buy_cap -= qty
        for price in sorted(od.buy_orders, reverse=True):
            if price >= fv + 1 and sell_cap > 0:
                qty = min(od.buy_orders[price], sell_cap)
                if qty > 0:
                    orders.append(Order(product, price, -qty))
                    sell_cap -= qty

        hedge_skew = int(max(-3, min(3, round(net_delta / 15.0))))
        eff_pos = pos + hedge_skew
        if eff_pos >= 40:    bp, sp = fv - 3, fv + 1
        elif eff_pos >= 20:  bp, sp = fv - 2, fv + 1
        elif eff_pos <= -40: bp, sp = fv - 1, fv + 3
        elif eff_pos <= -20: bp, sp = fv - 1, fv + 2
        else:                bp, sp = fv - 2, fv + 2

        if buy_cap > 0:
            orders.append(Order(product, bp, buy_cap))
        if sell_cap > 0:
            orders.append(Order(product, sp, -sell_cap))
        return orders

    def _trade_vev(self, state, product, od, S: float, T: float) -> List[Order]:
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

        if best_ask <= fair - TAKE_EDGE and buy_cap > 0:
            qty = min(-od.sell_orders[best_ask], buy_cap)
            if qty > 0:
                orders.append(Order(product, best_ask, qty))
                buy_cap -= qty

        if best_bid >= fair + TAKE_EDGE and sell_cap > 0:
            qty = min(od.buy_orders[best_bid], sell_cap)
            if qty > 0:
                orders.append(Order(product, best_bid, -qty))
                sell_cap -= qty

        bid_p = max(int(fair) - 1, int(intrinsic))
        ask_p = max(int(fair) + 1, int(intrinsic) + 1)
        bid_p = min(bid_p, best_ask - 1)
        ask_p = max(ask_p, best_bid + 1)

        if buy_cap > 0:
            orders.append(Order(product, bid_p, buy_cap))
        if sell_cap > 0:
            orders.append(Order(product, ask_p, -sell_cap))
        return orders
