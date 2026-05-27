# Vapi Integration Setup

## 1. Expose FastAPI public URL
Use ngrok or your cloud URL.

Example:
- `https://abc123.ngrok-free.app`

## 2. Import tool definitions
Create two Vapi function tools using:
- `vapi/tool_check_kb_answer.json`
- `vapi/tool_transfer_to_human.json`

Replace `https://YOUR_PUBLIC_DOMAIN` in both files with your live public URL.

## 3. Set assistant system prompt
Copy content from:
- `vapi/assistant_prompt.txt`

Paste in Vapi assistant system prompt.

## 4. Call-time logic in assistant
Expected flow:
1. User asks a support question.
2. Assistant calls `check_kb_answer`.
3. Assistant reads back `answer` from tool result.
4. If `should_transfer_to_human=true` or `action=transfer_to_human`, assistant calls `transfer_to_human` and informs caller.

## 5. Quick endpoint test before Vapi
- `POST /support/kb/ask`
- `POST /support/transfer`

## 6. Validation checklist
- Known FAQ question returns `fallback_used=false`.
- Unknown/complex question returns `should_transfer_to_human=true`.
- Transfer tool returns `action=transfer_to_human`.
- Assistant speaks concise customer-safe response.
