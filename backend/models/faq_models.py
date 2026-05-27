from typing import List, Optional

from pydantic import BaseModel, Field


class FAQItem(BaseModel):
    question: str
    answer: str
    tags: List[str] = Field(default_factory=list)


class FAQIngestResponse(BaseModel):
    success: bool
    source_file: str
    faq_count: int
    message: str


class FAQQueryRequest(BaseModel):
    question: str = Field(..., description="Customer question from an inbound call")
    caller_phone: Optional[str] = None


class FAQQueryResponse(BaseModel):
    success: bool
    question: str
    answer: str
    result: str
    confidence: float
    matched_question: Optional[str] = None
    fallback_used: bool
    should_transfer_to_human: bool
    action: Optional[str] = None


class PromptResponse(BaseModel):
    system_prompt: str
