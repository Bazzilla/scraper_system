"""Portfolio engine — derive current positions from transaction history.

Positions are *not* stored; they are calculated from the full transaction
list using the average-cost method.  Realized P/L is accumulated per-ticker
across all sells and survives recalculation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ── Data structures ──────────────────────────────────────────────────────────

@dataclass
class Position:
    ticker: str
    quantity: float = 0.0
    average_entry_price: float = 0.0
    total_cost: float = 0.0
    realized_pnl: float = 0.0
    market_price: float | None = None

    @property
    def market_value(self) -> float | None:
        if self.market_price is None:
            return None
        return self.quantity * self.market_price

    @property
    def unrealized_pnl(self) -> float | None:
        mv = self.market_value
        if mv is None:
            return None
        return mv - self.total_cost

    @property
    def unrealized_pnl_pct(self) -> float | None:
        up = self.unrealized_pnl
        if up is None or self.total_cost == 0:
            return None
        return up / self.total_cost * 100

    @property
    def total_pnl(self) -> float | None:
        up = self.unrealized_pnl
        if up is None:
            return None
        return self.realized_pnl + up

    @property
    def total_pnl_pct(self) -> float | None:
        tp = self.total_pnl
        if tp is None or self.total_cost == 0:
            return None
        return tp / self.total_cost * 100


@dataclass
class PortfolioResult:
    positions: dict[str, Position] = field(default_factory=dict)
    realized_pnl_by_ticker: dict[str, float] = field(default_factory=dict)


# ── Engine ───────────────────────────────────────────────────────────────────

class PortfolioError(Exception):
    """Raised when a transaction violates portfolio constraints."""


def calculate_positions(
    transactions: list[dict[str, Any]],
    prices: dict[str, float] | None = None,
) -> PortfolioResult:
    """Calculate current positions from a list of transactions.

    Args:
        transactions: list of transaction dicts (must be pre-sorted by
            ``trade_date`` then ``id``).
        prices: optional ``{ticker: last_close}`` map for unrealized P/L.

    Returns:
        PortfolioResult with open positions and realized P/L accumulator.

    Raises:
        PortfolioError: if a SELL exceeds current quantity.
    """
    # State per ticker: {ticker: {qty, cost, realized}}
    state: dict[str, dict[str, float]] = {}
    prices = prices or {}

    for tx in transactions:
        ticker = tx["ticker"]
        action = tx["action"]
        qty = tx["quantity"]
        price = tx["price_usd"]
        commission = tx.get("commission_usd", 0.0) or 0.0

        if ticker not in state:
            state[ticker] = {"qty": 0.0, "cost": 0.0, "realized": 0.0}

        s = state[ticker]

        if action == "BUY":
            buy_cost = qty * price + commission
            s["cost"] += buy_cost
            s["qty"] += qty

        elif action == "SELL":
            if qty > s["qty"] + 1e-9:
                raise PortfolioError(
                    f"SELL {qty} {ticker} exceeds current quantity {s['qty']}"
                )
            # average cost of the portion being sold
            avg = s["cost"] / s["qty"] if s["qty"] > 0 else 0.0
            cost_basis_sold = avg * qty
            sell_proceeds = qty * price - commission
            realized = sell_proceeds - cost_basis_sold
            s["realized"] += realized
            s["qty"] -= qty
            if s["qty"] < 1e-9:
                s["qty"] = 0.0
                s["cost"] = 0.0
            else:
                # cost tracks remaining cost at the same average
                s["cost"] = avg * s["qty"]

    # Build output — only open positions (qty > 0)
    result = PortfolioResult()

    for ticker, s in state.items():
        if s["qty"] > 1e-9:
            avg = s["cost"] / s["qty"] if s["qty"] > 0 else 0.0
            pos = Position(
                ticker=ticker,
                quantity=round(s["qty"], 10),
                average_entry_price=round(avg, 6),
                total_cost=round(s["cost"], 2),
                realized_pnl=round(s["realized"], 2),
                market_price=prices.get(ticker),
            )
            result.positions[ticker] = pos

        # Accumulator: present even for closed positions
        if s["realized"] != 0:
            result.realized_pnl_by_ticker[ticker] = round(s["realized"], 2)

    return result
