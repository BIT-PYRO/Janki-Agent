from typing import Optional

from pydantic import BaseModel, Field, model_validator


class OrderByNameRequest(BaseModel):
    order_name: str = Field(..., description="Customer order number, e.g. JANKI39765 or #39765")


class OrderByPhoneRequest(BaseModel):
    phone: str = Field(..., description="Caller phone number in national or E.164 format")


class OrderLookupRequest(BaseModel):
    order_name: Optional[str] = Field(default=None)
    phone: Optional[str] = Field(default=None)

    @model_validator(mode="after")
    def validate_at_least_one_identifier(self) -> "OrderLookupRequest":
        if not self.order_name and not self.phone:
            raise ValueError("Either order_name or phone is required")
        return self


class TransferRequest(BaseModel):
    reason: str = Field(..., description="Why the conversation should be transferred")
    customer_phone: Optional[str] = None
    order_name: Optional[str] = None


class CodConfirmationRequest(BaseModel):
    confirmed: bool = Field(..., description="Whether customer confirmed availability for COD delivery")
    order_name: Optional[str] = Field(default=None)
    phone: Optional[str] = Field(default=None)

    @model_validator(mode="after")
    def validate_lookup_identifier(self) -> "CodConfirmationRequest":
        if not self.order_name and not self.phone:
            raise ValueError("Either order_name or phone is required")
        return self


class OrderResponse(BaseModel):
    order_name: str
    order_id: int
    financial_status: Optional[str]
    fulfillment_status: Optional[str]
    total_price: str
    currency: Optional[str]
    customer_phone: Optional[str]
    spoken_status: str


class ApiMessage(BaseModel):
    success: bool
    message: str
    action: Optional[str] = None
    metadata: Optional[dict] = None
