from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from backend.models.faq_models import FAQIngestResponse, FAQQueryRequest, FAQQueryResponse, PromptResponse
from backend.models.order_models import ApiMessage, TransferRequest
from backend.services.knowledge_base_service import knowledge_base_service

router = APIRouter(prefix="/support", tags=["support"])


def build_system_prompt() -> str:
    return (
        "You are Janki Jewels customer support assistant for inbound voice calls. "
        "Always be polite, concise, and helpful. Use only approved knowledge base answers when possible. "
        "If a question is unclear, ask one short clarifying question. "
        "If you are not confident or the issue is sensitive/complex, trigger transfer_to_human. "
        "Do not invent policy details. "
        "If user asks order-tracking status, explain that order tracking support will be handled by an agent shortly "
        "and ask for order number so handoff is faster."
    )


@router.get("/health")
def support_health() -> dict:
    return {"status": "ok", "service": "knowledge-base-support"}


@router.post("/kb/upload", response_model=FAQIngestResponse)
async def upload_support_kb(file: UploadFile = File(...)) -> FAQIngestResponse:
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    target_dir = Path(__file__).resolve().parent.parent / "data"
    target_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = target_dir / file.filename

    data = await file.read()
    pdf_path.write_bytes(data)

    faq_count, source_file = knowledge_base_service.ingest_pdf_to_kb(pdf_path)

    return FAQIngestResponse(
        success=True,
        source_file=source_file,
        faq_count=faq_count,
        message="Knowledge base parsed and saved successfully.",
    )


@router.post("/kb/ask", response_model=FAQQueryResponse)
def ask_support_question(req: FAQQueryRequest) -> FAQQueryResponse:
    result = knowledge_base_service.answer_question(req.question)
    answer = str(result["answer"])

    return FAQQueryResponse(
        success=True,
        question=req.question,
        answer=answer,
        result=answer,
        confidence=float(result["confidence"]),
        matched_question=result.get("matched_question"),
        fallback_used=bool(result["fallback_used"]),
        should_transfer_to_human=bool(result["should_transfer_to_human"]),
        action=result.get("action"),
    )


@router.post("/kb/ask-vapi")
async def ask_support_question_vapi(request: Request) -> dict:
    payload = await request.json()

    def _extract_question(data: dict) -> str:
        if isinstance(data.get("question"), str):
            return data["question"]

        for key in ["parameters", "args", "arguments", "input"]:
            nested = data.get(key)
            if isinstance(nested, dict) and isinstance(nested.get("question"), str):
                return nested["question"]

        return ""

    def _extract_call_from_payload(data: dict) -> tuple[str, str]:
        tool_call_id = str(data.get("toolCallId") or data.get("id") or "").strip()
        question = _extract_question(data)
        return tool_call_id, question

    # Handle direct/simple request body shape.
    direct_tool_call_id, direct_question = _extract_call_from_payload(payload)
    if direct_question:
        result = knowledge_base_service.answer_question(direct_question)
        answer = str(result["answer"]).replace("\n", " ").strip()

        if direct_tool_call_id:
            return {
                "results": [
                    {
                        "toolCallId": direct_tool_call_id,
                        "result": answer,
                    }
                ]
            }

        # Backward-compatible response for manual tests.
        return {
            "result": answer,
            "answer": answer,
            "should_transfer_to_human": bool(result["should_transfer_to_human"]),
            "action": result.get("action"),
            "confidence": float(result["confidence"]),
            "matched_question": result.get("matched_question"),
        }

    # Handle batched tool call payloads used by some Vapi tool modes.
    potential_lists = [
        payload.get("toolCalls"),
        payload.get("toolCallList"),
        payload.get("calls"),
        (payload.get("message") or {}).get("toolCalls") if isinstance(payload.get("message"), dict) else None,
    ]

    for call_list in potential_lists:
        if isinstance(call_list, list) and call_list:
            results = []
            for call in call_list:
                if not isinstance(call, dict):
                    continue

                tool_call_id = str(
                    call.get("toolCallId")
                    or call.get("id")
                    or ((call.get("toolCall") or {}).get("id") if isinstance(call.get("toolCall"), dict) else "")
                ).strip()

                question = _extract_question(call)

                # Some formats wrap args in function.arguments.
                function_data = call.get("function")
                if not question and isinstance(function_data, dict):
                    function_args = function_data.get("arguments")
                    if isinstance(function_args, dict):
                        question = str(function_args.get("question") or "")

                if not question:
                    question = "I need help with my order and support."

                response = knowledge_base_service.answer_question(question)
                answer = str(response["answer"]).replace("\n", " ").strip()

                if tool_call_id:
                    results.append({"toolCallId": tool_call_id, "result": answer})

            if results:
                return {"results": results}

    # Final safe fallback in expected Vapi response envelope.
    fallback_answer = "I want to make sure you get the right help. I am transferring this to a support specialist."
    return {
        "results": [
            {
                "toolCallId": "unknown_call",
                "result": fallback_answer,
            }
        ]
    }


@router.get("/prompt", response_model=PromptResponse)
def get_voice_system_prompt() -> PromptResponse:
    return PromptResponse(system_prompt=build_system_prompt())


@router.post("/transfer", response_model=ApiMessage)
def transfer_to_human(req: TransferRequest) -> ApiMessage:
    return ApiMessage(
        success=True,
        action="transfer_to_human",
        message="Transferring this call to a human support specialist.",
        metadata={
            "reason": req.reason,
            "customer_phone": req.customer_phone,
            "order_name": req.order_name,
        },
    )
