from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException

from backend.models.order_models import (
    ApiMessage,
    CodConfirmationRequest,
    OrderByNameRequest,
    OrderByPhoneRequest,
    OrderLookupRequest,
    OrderResponse,
    TransferRequest,
)
from backend.services.shopify_service import shopify_service

router = APIRouter(tags=["orders"])


def _human_order_status(financial_status: Optional[str], fulfillment_status: Optional[str]) -> str:
    finance = (financial_status or "").lower()
    fulfillment = (fulfillment_status or "unfulfilled").lower()

    if fulfillment in {"fulfilled", "shipped"}:
        return "Your order has already been shipped and is on the way."

    if fulfillment in {"partial", "partially_fulfilled"}:
        return "Part of your order has shipped. The remaining items will be dispatched soon."

    if finance in {"paid", "authorized"}:
        return "Your order is confirmed and is currently being prepared for shipment."

    if finance in {"pending", "partially_paid"}:
        return "Your order is placed and we are waiting for payment confirmation."

    if finance in {"refunded", "voided"}:
        return "This order was cancelled or refunded. A human agent can help with details."

    return "Your order is in progress. A support agent can share more detailed updates if needed."


def _serialize_order(order: Dict[str, Any]) -> OrderResponse:
    spoken_status = _human_order_status(
        financial_status=order.get("financial_status"),
        fulfillment_status=order.get("fulfillment_status"),
    )

    return OrderResponse(
        order_name=order.get("name", ""),
        order_id=int(order.get("id", 0)),
        financial_status=order.get("financial_status"),
        fulfillment_status=order.get("fulfillment_status"),
        total_price=str(order.get("total_price", "0")),
        currency=order.get("currency"),
        customer_phone=order.get("phone")
        or (order.get("shipping_address") or {}).get("phone")
        or (order.get("billing_address") or {}).get("phone"),
        spoken_status=spoken_status,
    )


@router.get("/")
def home() -> dict:
    return {
        "status": "AI backend running",
        "service": "shopify-voice-support",
    }


@router.post("/order", response_model=OrderResponse)
def get_order_by_name(req: OrderByNameRequest) -> OrderResponse:
    order = shopify_service.find_order_by_name(req.order_name)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return _serialize_order(order)


@router.post("/order/by-phone", response_model=OrderResponse)
def get_order_by_phone(req: OrderByPhoneRequest) -> OrderResponse:
    order = shopify_service.find_order_by_phone(req.phone)
    if not order:
        raise HTTPException(status_code=404, detail="No order found for this phone number")
    return _serialize_order(order)


@router.post("/order/status", response_model=OrderResponse)
def get_order_status(req: OrderLookupRequest) -> OrderResponse:
    order = None

    if req.phone:
        order = shopify_service.find_order_by_phone(req.phone)

    if not order and req.order_name:
        order = shopify_service.find_order_by_name(req.order_name)

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    return _serialize_order(order)


@router.post("/support/transfer", response_model=ApiMessage)
def transfer_to_human(req: TransferRequest) -> ApiMessage:
    return ApiMessage(
        success=True,
        action="transfer_to_human",
        message="Transferring this call to a human support agent.",
        metadata={
            "reason": req.reason,
            "customer_phone": req.customer_phone,
            "order_name": req.order_name,
        },
    )


@router.post("/cod/confirm", response_model=ApiMessage)
def confirm_cod(req: CodConfirmationRequest) -> ApiMessage:
    order = None

    if req.phone:
        order = shopify_service.find_order_by_phone(req.phone)

    if not order and req.order_name:
        order = shopify_service.find_order_by_name(req.order_name)

    if not order:
        raise HTTPException(status_code=404, detail="Order not found for COD confirmation")

    if not req.confirmed:
        return ApiMessage(
            success=True,
            message="Customer did not confirm COD delivery availability.",
            metadata={"order_name": order.get("name"), "cod_confirmed": False},
        )

    updated = shopify_service.add_tag_to_order(order_id=int(order["id"]), tag="COD_CONFIRMED")

    return ApiMessage(
        success=True,
        message="COD confirmation recorded and order tagged as COD_CONFIRMED.",
        metadata={
            "order_name": order.get("name"),
            "order_id": order.get("id"),
            "shopify_order": updated.get("order", {}),
            "cod_confirmed": True,
        },
    )


@router.get("/cod/pending-calls")
def cod_pending_calls(limit: int = 25) -> dict:
    effective_limit = min(max(limit, 1), 100)
    orders = shopify_service.list_cod_orders_needing_confirmation(limit=effective_limit)

    return {
        "count": len(orders),
        "orders": [
            {
                "order_id": order.get("id"),
                "order_name": order.get("name"),
                "phone": order.get("phone")
                or (order.get("shipping_address") or {}).get("phone")
                or (order.get("billing_address") or {}).get("phone"),
                "financial_status": order.get("financial_status"),
                "fulfillment_status": order.get("fulfillment_status"),
                "tags": order.get("tags"),
            }
            for order in orders
        ],
    }
