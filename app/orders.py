from __future__ import annotations

from dataclasses import asdict, dataclass

from app.security import AuthError, User


@dataclass(frozen=True, slots=True)
class OrderStatus:
    order_id: str
    status: str
    carrier: str
    tracking_no: str
    estimated_delivery: str


ORDERS = {
    "SO-1001": OrderStatus("SO-1001", "运输中", "顺丰", "SF202610200001", "2026-10-24"),
    "SO-1002": OrderStatus("SO-1002", "已签收", "顺丰", "SF202610180008", "2026-10-20"),
    "SO-1003": OrderStatus("SO-1003", "待发货", "待分配", "", "2026-10-27"),
}


class OrderService:
    def get_status(self, user: User, order_id: str) -> dict:
        if user.role == "viewer":
            raise AuthError("只读用户无权查询订单")
        order = ORDERS.get(order_id.strip().upper())
        if order is None:
            raise LookupError("订单不存在")
        return asdict(order)
