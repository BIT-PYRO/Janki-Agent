import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv


load_dotenv()


def _clean_store_domain(raw: str) -> str:
    value = raw.strip().replace("https://", "").replace("http://", "")
    return value.rstrip("/")


@dataclass(frozen=True)
class Settings:
    app_name: str
    app_env: str
    app_debug: bool
    shopify_store: Optional[str]
    shopify_access_token: Optional[str]
    shopify_api_version: str
    request_timeout_seconds: int
    default_order_limit: int


    @property
    def shopify_rest_base_url(self) -> str:
        if not self.shopify_store:
            raise RuntimeError("SHOPIFY_STORE is not configured")
        return f"https://{self.shopify_store}/admin/api/{self.shopify_api_version}"


def get_settings() -> Settings:
    app_env = os.getenv("APP_ENV", "development")
    app_debug = os.getenv("APP_DEBUG", "false").lower() == "true"

    store = os.getenv("SHOPIFY_STORE", os.getenv("SHOPIFY_SHOP", ""))
    token = os.getenv("SHOPIFY_ACCESS_TOKEN", "")

    return Settings(
        app_name=os.getenv("APP_NAME", "Janki Jewels Voice Support Backend"),
        app_env=app_env,
        app_debug=app_debug,
        shopify_store=_clean_store_domain(store) if store else None,
        shopify_access_token=token.strip() if token else None,
        shopify_api_version=os.getenv("SHOPIFY_API_VERSION", "2024-01"),
        request_timeout_seconds=int(os.getenv("SHOPIFY_TIMEOUT_SECONDS", "20")),
        default_order_limit=int(os.getenv("SHOPIFY_DEFAULT_LIMIT", "25")),
    )


settings = get_settings()
