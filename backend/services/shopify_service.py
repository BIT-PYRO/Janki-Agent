import re
from typing import Any, Dict, List, Optional

import requests
from fastapi import HTTPException

from backend.config import settings


class ShopifyService:
    def __init__(self) -> None:
        self.base_url = (
            f"https://{settings.shopify_store}/admin/api/{settings.shopify_api_version}"
            if settings.shopify_store
            else ""
        )
        self.default_limit = settings.default_order_limit
        self.timeout = settings.request_timeout_seconds
        self.session = requests.Session()
        self.session.headers.update(
            {
                "X-Shopify-Access-Token": settings.shopify_access_token or "",
                "Content-Type": "application/json",
            }
        )

    def _ensure_configured(self) -> None:
        if not settings.shopify_store or not settings.shopify_access_token:
            raise HTTPException(
                status_code=503,
                detail="Shopify integration is not configured yet. Use knowledge-base support endpoints.",
            )

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        self._ensure_configured()
        url = f"{self.base_url}/{path.lstrip('/')}"
        try:
            response = self.session.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            raise HTTPException(status_code=502, detail=f"Shopify GET failed: {exc}") from exc

    def _put(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_configured()
        url = f"{self.base_url}/{path.lstrip('/')}"
        try:
            response = self.session.put(url, json=payload, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            raise HTTPException(status_code=502, detail=f"Shopify PUT failed: {exc}") from exc

    @staticmethod
    def _normalize_phone(phone: str) -> str:
        raw = phone.strip()
        digits = re.sub(r"\D", "", raw)
        if raw.startswith("+") and digits:
            return f"+{digits}"
        return digits

    @staticmethod
    def _normalize_order_name(order_name: str) -> str:
        cleaned = order_name.strip().upper().replace(" ", "")
        return cleaned

    @staticmethod
    def _extract_numeric_order_token(order_name: str) -> str:
        return "".join(re.findall(r"\d+", order_name))

    @staticmethod
    def _collect_customer_phones(order: Dict[str, Any]) -> List[str]:
        phones: List[str] = []

        for field in ["phone"]:
            value = order.get(field)
            if isinstance(value, str) and value:
                phones.append(value)

        customer = order.get("customer") or {}
        if isinstance(customer, dict):
            value = customer.get("phone")
            if isinstance(value, str) and value:
                phones.append(value)

        for addr_key in ["billing_address", "shipping_address"]:
            address = order.get(addr_key) or {}
            if isinstance(address, dict):
                value = address.get("phone")
                if isinstance(value, str) and value:
                    phones.append(value)

        return phones

    @staticmethod
    def _match_phone(order: Dict[str, Any], target_phone: str) -> bool:
        normalized_target = re.sub(r"\D", "", target_phone)
        if not normalized_target:
            return False

        for phone in ShopifyService._collect_customer_phones(order):
            candidate = re.sub(r"\D", "", phone)
            if not candidate:
                continue
            if candidate.endswith(normalized_target) or normalized_target.endswith(candidate):
                return True
        return False

    @staticmethod
    def _match_order_name(order: Dict[str, Any], order_name: str) -> bool:
        target = ShopifyService._normalize_order_name(order_name)
        existing_name = ShopifyService._normalize_order_name(str(order.get("name", "")))
        if target and target in existing_name:
            return True

        numeric_target = ShopifyService._extract_numeric_order_token(target)
        if not numeric_target:
            return False

        if numeric_target in existing_name:
            return True

        order_number = str(order.get("order_number", ""))
        return numeric_target == order_number

    def _fetch_orders(self, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        response = self._get("orders.json", params=params)
        return response.get("orders", [])

    def find_order_by_name(self, order_name: str) -> Optional[Dict[str, Any]]:
        normalized = self._normalize_order_name(order_name)
        numeric = self._extract_numeric_order_token(normalized)

        targeted_queries = [
            {"status": "any", "name": normalized, "limit": self.default_limit},
            {"status": "any", "query": f"name:{normalized}", "limit": self.default_limit},
        ]

        if numeric:
            targeted_queries.append(
                {"status": "any", "query": f"name:{numeric}", "limit": self.default_limit}
            )

        for params in targeted_queries:
            orders = self._fetch_orders(params)
            for order in orders:
                if self._match_order_name(order, normalized):
                    return order

        # Last fallback to recent orders only, not full history.
        fallback_orders = self._fetch_orders({"status": "any", "limit": 50, "order": "created_at desc"})
        for order in fallback_orders:
            if self._match_order_name(order, normalized):
                return order
        return None

    def find_order_by_phone(self, phone: str) -> Optional[Dict[str, Any]]:
        normalized = self._normalize_phone(phone)

        targeted_queries = [
            {"status": "any", "phone": normalized, "limit": self.default_limit},
            {"status": "any", "query": f"phone:{normalized}", "limit": self.default_limit},
        ]

        for params in targeted_queries:
            orders = self._fetch_orders(params)
            for order in orders:
                if self._match_phone(order, normalized):
                    return order

        fallback_orders = self._fetch_orders({"status": "any", "limit": 50, "order": "created_at desc"})
        for order in fallback_orders:
            if self._match_phone(order, normalized):
                return order
        return None

    def add_tag_to_order(self, order_id: int, tag: str) -> Dict[str, Any]:
        existing_order = self._get(f"orders/{order_id}.json", params={"status": "any"}).get("order", {})
        existing_tags = [t.strip() for t in str(existing_order.get("tags", "")).split(",") if t.strip()]

        if tag not in existing_tags:
            existing_tags.append(tag)

        payload = {
            "order": {
                "id": order_id,
                "tags": ", ".join(existing_tags),
            }
        }
        return self._put(f"orders/{order_id}.json", payload)

    def list_cod_orders_needing_confirmation(self, limit: int = 50) -> List[Dict[str, Any]]:
        orders = self._fetch_orders({"status": "any", "limit": limit, "order": "created_at desc"})
        candidates: List[Dict[str, Any]] = []

        for order in orders:
            gateways = [g.lower() for g in order.get("payment_gateway_names") or []]
            tags = [t.strip().upper() for t in str(order.get("tags", "")).split(",") if t.strip()]
            financial_status = str(order.get("financial_status", "")).lower()

            is_cod = any("cod" in g or "cash on delivery" in g for g in gateways)
            already_confirmed = "COD_CONFIRMED" in tags
            needs_confirmation = financial_status in {"pending", "authorized"}

            if is_cod and not already_confirmed and needs_confirmation:
                candidates.append(order)

        return candidates


shopify_service = ShopifyService()
