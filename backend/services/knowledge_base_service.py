import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Tuple

import pdfplumber
from fastapi import HTTPException

from backend.models.faq_models import FAQItem


class KnowledgeBaseService:
    def __init__(self) -> None:
        self.data_dir = Path(__file__).resolve().parent.parent / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.kb_file = self.data_dir / "faq_kb.json"

    def _strip_pdf_artifact(self, text: str) -> str:
        """Remove leading colon/whitespace artifacts produced by some PDF parsers."""
        return re.sub(r"^[:\s]+", "", text).strip()

    def _normalize(self, text: str) -> str:
        cleaned = text.lower().strip()
        cleaned = re.sub(r"\s+", " ", cleaned)
        cleaned = re.sub(r"[^a-z0-9 ?]", "", cleaned)
        # Normalize frequent spelling variants so FAQ matching is more stable.
        cleaned = cleaned.replace("arushhaa", "arushaa")
        cleaned = cleaned.replace("arusha", "arushaa")
        cleaned = cleaned.replace("buy one get one", "buy 1 get 1")
        cleaned = cleaned.replace("b1g1", "buy 1 get 1")
        return cleaned

    def _score(self, question: str, candidate: str) -> float:
        q = self._normalize(question)
        c = self._normalize(candidate)
        if not q or not c:
            return 0.0

        ratio = SequenceMatcher(None, q, c).ratio()

        q_tokens = set(q.split())
        c_tokens = set(c.split())
        overlap = len(q_tokens.intersection(c_tokens)) / max(len(q_tokens), 1)

        score = (0.65 * ratio) + (0.35 * overlap)

        # Intent boost for high-value collection terms with common caller phrasing.
        if "arushaa" in q and "arushaa" in c:
            score += 0.12
        if "buy 1 get 1" in q and ("buy 1 get 1" in c or "offer" in c or "collection" in c):
            score += 0.08

        return round(min(score, 1.0), 4)

    def _extract_faq_pairs(self, text: str) -> List[FAQItem]:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        items: List[FAQItem] = []

        current_q = ""
        current_a: List[str] = []

        def commit_current() -> None:
            nonlocal current_q, current_a
            if current_q and current_a:
                items.append(FAQItem(question=current_q, answer=" ".join(current_a).strip()))
            current_q = ""
            current_a = []

        for line in lines:
            q_match = re.match(r"^(Q\.?|Question\s*:?|\d+[\).])\s*(.*)$", line, flags=re.IGNORECASE)
            a_match = re.match(r"^(A\.?|Answer\s*:?)\s*(.*)$", line, flags=re.IGNORECASE)

            if q_match:
                commit_current()
                maybe_q = self._strip_pdf_artifact(q_match.group(2).strip())
                current_q = maybe_q if maybe_q else line
                continue

            if a_match and current_q:
                maybe_a = self._strip_pdf_artifact(a_match.group(2).strip())
                if maybe_a:
                    current_a.append(maybe_a)
                continue

            if current_q and line.endswith("?") and not current_a:
                # Treat consecutive question lines as one question when parser is uncertain.
                current_q = f"{current_q} {line}".strip()
                continue

            if current_q:
                current_a.append(line)

        commit_current()

        if items:
            return items

        # Fallback parser: pair each question-like line with following non-empty lines until next question.
        fallback_items: List[FAQItem] = []
        idx = 0
        while idx < len(lines):
            line = lines[idx]
            if line.endswith("?"):
                question = line
                idx += 1
                answer_parts: List[str] = []
                while idx < len(lines) and not lines[idx].endswith("?"):
                    answer_parts.append(lines[idx])
                    idx += 1
                if answer_parts:
                    fallback_items.append(
                        FAQItem(question=question, answer=" ".join(answer_parts).strip())
                    )
                continue
            idx += 1

        return fallback_items

    def _is_heading_line(self, line: str) -> bool:
        cleaned = line.strip()
        if len(cleaned) < 3 or len(cleaned) > 80:
            return False
        if any(ch.isdigit() for ch in cleaned):
            return False
        letters = [ch for ch in cleaned if ch.isalpha()]
        if not letters:
            return False
        uppercase_ratio = sum(1 for ch in letters if ch.isupper()) / len(letters)
        return uppercase_ratio > 0.8

    def _split_sections(self, text: str) -> Dict[str, List[str]]:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        sections: Dict[str, List[str]] = {}
        current_heading = "GENERAL"
        sections[current_heading] = []

        for line in lines:
            normalized = re.sub(r"^[\u2022\-\*\s]+", "", line)
            if self._is_heading_line(normalized):
                current_heading = normalized
                sections.setdefault(current_heading, [])
                continue
            sections[current_heading].append(normalized)

        return sections

    def _compact_answer(self, text: str, max_chars: int = 320) -> str:
        cleaned = re.sub(r"\s+", " ", text).strip()
        cleaned = cleaned.replace("•", "-").replace("●", "-")
        cleaned = cleaned.encode("ascii", "ignore").decode("ascii")
        if len(cleaned) <= max_chars:
            return cleaned

        cut = cleaned[:max_chars]
        if ". " in cut:
            cut = cut.rsplit(". ", 1)[0] + "."
        return cut.strip()

    def _extract_line_context(self, text: str, keywords: List[str], window: int = 3) -> str:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        for idx, line in enumerate(lines):
            normalized = self._normalize(line)
            if any(keyword in normalized for keyword in keywords):
                block = lines[idx : idx + window]
                return self._compact_answer(" ".join(block), max_chars=360)
        return ""

    def _is_voice_safe(self, answer: str) -> bool:
        bad_tokens = [
            "whatsapp",
            "instagram",
            "dm",
            "pre-sale",
            "sales executive",
            "team direction",
            "retention offer",
        ]
        normalized = self._normalize(answer)
        return not any(token in normalized for token in bad_tokens)

    def _item_priority(self, item: FAQItem) -> int:
        tags = {t.lower() for t in item.tags}
        if "seed" in tags:
            return 3
        if "policy" in tags:
            return 2
        return 1

    def _generate_policy_faqs(self, text: str) -> List[FAQItem]:
        sections = self._split_sections(text)
        section_map = {self._normalize(k): (k, v) for k, v in sections.items()}

        templates = [
            ("cash on delivery", "Do you offer Cash on Delivery?"),
            ("orders payments", "What payment methods do you accept?"),
            ("warranty", "Do you provide warranty on jewelry?"),
            ("tracking order", "How can I track my order?"),
            ("discounts offers", "What offers are currently available?"),
            ("why should customers trust janki", "Why should I trust Janki Jewels?"),
            (
                "fallback handling guideline",
                "What happens if the support agent does not know an answer?",
            ),
            ("exchange", "What can I do if I want an exchange or resolution?"),
        ]

        generated: List[FAQItem] = []

        for needle, question in templates:
            for normalized_heading, (_, content_lines) in section_map.items():
                if needle in normalized_heading and content_lines:
                    answer = self._compact_answer(" ".join(content_lines))
                    if answer:
                        generated.append(
                            FAQItem(
                                question=question,
                                answer=answer,
                                tags=["generated", "policy"],
                            )
                        )
                    break

        normalized_text = self._normalize(text)
        if "3 to 7" in normalized_text or "business days" in normalized_text:
            generated.append(
                FAQItem(
                    question="How long does delivery take?",
                    answer="Delivery usually takes around 3 to 7 business days depending on your location and order processing.",
                    tags=["generated", "delivery"],
                )
            )

        if "damaged" in normalized_text and "replacement" in normalized_text:
            extracted = self._extract_line_context(text, ["damaged", "replacement", "return"], window=4)
            generated.append(
                FAQItem(
                    question="What if my product arrives damaged?",
                    answer=extracted
                    or "If your product arrives damaged, contact support with photos or video and the team will guide you on replacement or return as per policy.",
                    tags=["generated", "returns"],
                )
            )

        if "cash on delivery" in normalized_text or "cod" in normalized_text:
            cod_answer = self._extract_line_context(
                text,
                ["cash on delivery", "cod", "selected serviceable locations"],
                window=4,
            )
            if not cod_answer or not self._is_voice_safe(cod_answer):
                cod_answer = "Yes, Cash on Delivery is available for selected serviceable locations."
            generated.append(
                FAQItem(
                    question="Do you offer Cash on Delivery?",
                    answer=cod_answer,
                    tags=["generated", "payments"],
                )
            )

        if "track my order" in normalized_text or "tracking" in normalized_text:
            generated.append(
                FAQItem(
                    question="Where is my order?",
                    answer="You can track your order from the website using Track My Order and your order ID or AWB number. If tracking is not updated yet, the order may still be in processing.",
                    tags=["generated", "tracking"],
                )
            )

        seed_faqs = [
            FAQItem(
                question="What if my product arrives damaged?",
                answer="If your product arrives damaged, please contact support with photos or video within the policy window, and the team will assist with return or replacement steps.",
                tags=["seed", "returns"],
            ),
            FAQItem(
                question="Do you offer Cash on Delivery?",
                answer="Yes, Cash on Delivery is available for selected serviceable locations.",
                tags=["seed", "payments"],
            ),
            FAQItem(
                question="How long does delivery take?",
                answer="Delivery typically takes around 3 to 7 business days depending on location and order processing.",
                tags=["seed", "delivery"],
            ),
        ]

        generated.extend(seed_faqs)

        return generated

    def _merge_deduplicate(self, items: List[FAQItem]) -> List[FAQItem]:
        merged: Dict[str, FAQItem] = {}
        for item in items:
            # Skip noisy pseudo-questions that are likely section leads with giant mixed answers.
            if item.question.strip().endswith(":") and len(item.answer) > 600:
                continue

            key = self._normalize(item.question)
            if not key:
                continue

            if key in merged:
                existing = merged[key]
                if self._item_priority(item) > self._item_priority(existing):
                    merged[key] = item
                elif self._item_priority(item) == self._item_priority(existing) and len(item.answer) > len(
                    existing.answer
                ):
                    merged[key] = item
                continue

            merged[key] = item

        return list(merged.values())

    def extract_text_from_pdf(self, pdf_path: Path) -> str:
        if not pdf_path.exists():
            raise HTTPException(status_code=400, detail=f"PDF not found: {pdf_path.name}")

        pages: List[str] = []
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    pages.append(page.extract_text() or "")
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Unable to parse PDF: {exc}") from exc

        text = "\n".join(pages).strip()
        if not text:
            raise HTTPException(status_code=400, detail="PDF appears empty or unreadable")
        return text

    def ingest_pdf_to_kb(self, source_pdf: Path) -> Tuple[int, str]:
        text = self.extract_text_from_pdf(source_pdf)
        faq_items = self._extract_faq_pairs(text)

        if len(faq_items) < 5:
            faq_items.extend(self._generate_policy_faqs(text))

        faq_items = self._merge_deduplicate(faq_items)

        if not faq_items:
            raise HTTPException(
                status_code=400,
                detail="Could not detect FAQ pairs in PDF. Use Q:/A: or clear question lines ending with '?'.",
            )

        payload: Dict[str, object] = {
            "source_file": source_pdf.name,
            "faq_count": len(faq_items),
            "faqs": [item.model_dump() for item in faq_items],
        }
        self.kb_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")

        return len(faq_items), source_pdf.name

    def load_faqs(self) -> List[FAQItem]:
        if not self.kb_file.exists():
            return []

        raw = json.loads(self.kb_file.read_text(encoding="utf-8"))
        items = []
        for item in raw.get("faqs", []):
            item["question"] = self._strip_pdf_artifact(item.get("question", ""))
            item["answer"] = self._strip_pdf_artifact(item.get("answer", ""))
            items.append(FAQItem(**item))
        return items

    def answer_question(self, question: str) -> Dict[str, object]:
        faqs = self.load_faqs()
        if not faqs:
            return {
                "answer": "I do not have the latest support knowledge loaded yet. Let me connect you to a human agent.",
                "confidence": 0.0,
                "matched_question": None,
                "fallback_used": True,
                "should_transfer_to_human": True,
                "action": "transfer_to_human",
            }

        scored = [
            {
                "score": self._score(question, item.question),
                "item": item,
            }
            for item in faqs
        ]
        scored.sort(key=lambda x: x["score"], reverse=True)

        best = scored[0]
        best_score = float(best["score"])
        best_item: FAQItem = best["item"]

        complex_intent = any(
            token in question.lower()
            for token in ["lawyer", "legal", "police", "chargeback", "consumer court", "manager"]
        )

        if best_score < 0.42 or complex_intent:
            return {
                "answer": "I want to make sure you get the right help. I am transferring this to a support specialist.",
                "confidence": best_score,
                "matched_question": best_item.question,
                "fallback_used": True,
                "should_transfer_to_human": True,
                "action": "transfer_to_human",
            }

        return {
            "answer": best_item.answer,
            "confidence": best_score,
            "matched_question": best_item.question,
            "fallback_used": False,
            "should_transfer_to_human": False,
            "action": None,
        }


knowledge_base_service = KnowledgeBaseService()
