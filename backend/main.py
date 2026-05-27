from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import settings
from backend.routes.support import router as support_router

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(support_router)

try:
    from backend.routes.orders import router as order_router

    app.include_router(order_router)
except Exception:
    # Keep app startup resilient when Shopify configuration is intentionally absent.
    pass
