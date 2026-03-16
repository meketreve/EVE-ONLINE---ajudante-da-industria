"""
Industry cost and profit calculation engine.

All formulas follow EVE Online's official industry mechanics.
"""

from dataclasses import dataclass
from typing import Sequence


@dataclass
class Material:
    type_id: int
    quantity: int
    unit_price: float = 0.0

    @property
    def total_cost(self) -> float:
        return self.quantity * self.unit_price


@dataclass
class ProductionCostBreakdown:
    material_cost: float
    estimated_item_value: float
    job_cost: float
    total_cost: float
    system_cost_index: float
    facility_tax: float
    scc_surcharge: float


@dataclass
class ProfitBreakdown:
    sale_price: float
    production_cost: float
    gross_profit: float
    broker_fee: float
    sales_tax: float
    net_profit: float
    margin_pct: float  # net profit / sale_price * 100


def calculate_production_cost(
    materials: Sequence[Material],
    estimated_item_value: float,
    system_cost_index: float = 0.05,
    facility_tax: float = 0.0,
    scc_surcharge: float = 0.015,
) -> ProductionCostBreakdown:
    """
    Calculate the total production cost of a manufacturing job.

    Parameters
    ----------
    materials:
        List of Material objects, each carrying quantity and unit_price.
    estimated_item_value:
        The estimated value of the job's output (used by EVE to compute the job fee).
        In practice this is the adjusted price of the output item multiplied by quantity.
    system_cost_index:
        The manufacturing cost index of the system where the job runs (e.g. 0.05 = 5%).
    facility_tax:
        Additional facility-imposed tax on top of the cost index (e.g. 0.10 = 10%).
    scc_surcharge:
        CCP's fixed SCC surcharge, currently 1.5% (0.015).

    Returns
    -------
    ProductionCostBreakdown with all individual components and the total.
    """
    material_cost = sum(m.total_cost for m in materials)
    job_cost = estimated_item_value * (system_cost_index + facility_tax + scc_surcharge)
    total = material_cost + job_cost

    return ProductionCostBreakdown(
        material_cost=material_cost,
        estimated_item_value=estimated_item_value,
        job_cost=job_cost,
        total_cost=total,
        system_cost_index=system_cost_index,
        facility_tax=facility_tax,
        scc_surcharge=scc_surcharge,
    )


def calculate_profit(
    sale_price: float,
    production_cost: float,
    broker_fee_pct: float = 0.03,
    sales_tax_pct: float = 0.036,
) -> ProfitBreakdown:
    """
    Calculate net profit after selling the manufactured item.

    Parameters
    ----------
    sale_price:
        The price at which the item will be sold (ISK per unit * quantity).
    production_cost:
        The total production cost returned by calculate_production_cost.
    broker_fee_pct:
        Broker fee as a decimal fraction (e.g. 0.03 = 3%).
    sales_tax_pct:
        Sales tax as a decimal fraction (e.g. 0.036 = 3.6%).

    Returns
    -------
    ProfitBreakdown with gross and net profit details.
    """
    gross = sale_price - production_cost
    broker_fee = sale_price * broker_fee_pct
    sales_tax = sale_price * sales_tax_pct
    taxes = broker_fee + sales_tax
    net = gross - taxes
    margin = (net / sale_price * 100) if sale_price > 0 else 0.0

    return ProfitBreakdown(
        sale_price=sale_price,
        production_cost=production_cost,
        gross_profit=gross,
        broker_fee=broker_fee,
        sales_tax=sales_tax,
        net_profit=net,
        margin_pct=margin,
    )


def apply_me_level(
    base_quantity: int,
    me_level: int,
    structure_me_bonus: float = 0.0,
) -> int:
    """
    Apply Material Efficiency to a material quantity.

    EVE Online formula (multiplicative stacking):
        ceil(base_qty * (1 - bp_me/100) * (1 - structure_me/100))

    `me_level` is the blueprint ME level (0–10, each = 1% reduction).
    `structure_me_bonus` is the total structure ME bonus in % (e.g. 3.0 = -3%).
    """
    import math

    me_level = max(0, min(10, me_level))
    structure_me_bonus = max(0.0, min(100.0, structure_me_bonus))
    result = math.ceil(
        base_quantity * (1.0 - me_level / 100.0) * (1.0 - structure_me_bonus / 100.0)
    )
    return max(1, result)
