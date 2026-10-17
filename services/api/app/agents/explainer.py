import logging
import re
from typing import List, Optional, Set
from app.models.firestore_models import StoredRequest, StoredResource, MatchBreakdown
from app.models.schemas import Explanation
from app.llm.client import llm_client

logger = logging.getLogger("relief_desk.explainer")


class ExplainerAgent:
    """
    Explainer Agent: Generates plain-language, <= 2 sentence explanations (EN + HI)
    explaining why a resource was matched to a request.
    Strictly enforces numeric consistency: any numeric token generated that is NOT
    present in the input numbers list immediately triggers deterministic template fallback.
    """

    def generate_template_fallback(
        self,
        request: StoredRequest,
        resource: StoredResource,
        breakdown: MatchBreakdown,
    ) -> Explanation:
        # The live score is shown next to this text; repeating it here goes stale as wait time grows.
        people = request.people_count
        who_en = f"{people} {'person' if people == 1 else 'people'}" if people else "the people reported (count not stated)"
        text_en = (
            f"{resource.name} is {breakdown.distance_km} km away"
            f"{' by water (boat, straight line)' if getattr(resource.kind, 'value', resource.kind) == 'boat' else ''} with {resource.capacity_remaining} seats "
            f"to assist {who_en}."
        )

        from app.tools.inventory import inventory_note
        note = inventory_note(request, resource)
        if note:
            text_en += " " + note
        if _life_threat(request) and "112" not in text_en:
            text_en += " In an emergency call 112."

        res_name_hi = resource.name_hi or resource.name
        text_hi = (
            f"{res_name_hi} {breakdown.distance_km} किमी दूर है और "
            f"{(str(people) + ' लोगों') if people else 'बताए गए लोगों'} की सहायता के लिए उपलब्ध है।"
        )

        return Explanation(text_en=text_en, text_hi=text_hi)

    def extract_allowed_numbers(
        self,
        request: StoredRequest,
        resource: StoredResource,
        breakdown: MatchBreakdown,
    ) -> Set[float]:
        numbers: Set[float] = {
            float(breakdown.distance_km),
            float(breakdown.distance_score),
            float(breakdown.capacity_fit_score),
            float(breakdown.urgency_score),
            float(breakdown.vulnerability_fit_score),
            float(breakdown.total_score),
            float(resource.capacity_total),
            float(resource.capacity_remaining),
        }
        if request.people_count is not None:
            numbers.add(float(request.people_count))
        else:
            numbers.add(1.0)

        # Allow 0, 1, 2 for sentence counts or common rank references
        numbers.add(0.0)
        numbers.add(1.0)
        numbers.add(2.0)
        return numbers

    def verify_numbers(self, text: str, allowed_numbers: Set[float]) -> bool:
        """Finds all numeric tokens in text and ensures each exists in allowed_numbers."""
        tokens = re.findall(r"\b\d+(?:\.\d+)?\b", text)
        for token in tokens:
            try:
                val = float(token)
                if val not in allowed_numbers:
                    logger.warning(
                        "Explainer guardrail failed: number '%s' not in allowed numbers %s",
                        token,
                        allowed_numbers,
                    )
                    return False
            except ValueError:
                continue
        return True

    def explain(
        self,
        request: StoredRequest,
        resource: StoredResource,
        breakdown: MatchBreakdown,
        forged_llm_text: Optional[str] = None,
    ) -> Explanation:
        allowed = self.extract_allowed_numbers(request, resource, breakdown)
        fallback = self.generate_template_fallback(request, resource, breakdown)

        # Testing hook for simulated forged LLM output
        if forged_llm_text is not None:
            if not self.verify_numbers(forged_llm_text, allowed):
                logger.info("Explainer: Forged output rejected by guardrail, using template fallback.")
                return fallback
            return Explanation(text_en=forged_llm_text, text_hi=fallback.text_hi)

        if not llm_client.gemini_live():
            return fallback

        prompt = (
            f"Explain why {resource.name} is matched to this rescue request in <= 2 sentences.\n"
            f"Use plain words. Do not write the field names urgency_score or match_score.\n"
            f"Input numbers:\n"
            f"- Distance: {breakdown.distance_km} km\n"
            f"- Seats free: {resource.capacity_remaining} (people reported: {request.people_count or 1})\n"
            f"- How urgent this case is, as a number already on the card: {breakdown.urgency_score}\n"
            f"- How well this team fits: {breakdown.total_score}\n"
            f"RULE: Cite ONLY these provided numbers. Do not invent any numbers.\n"
            f"If someone may die (not breathing, unconscious, oxygen, bleeding), end with: In an emergency call 112.\n"
            f"Provide valid JSON: {{\"text_en\": \"...\", \"text_hi\": \"...\"}}"
        )

        try:
            resp = llm_client.generate(prompt=prompt, system_instruction="Output valid JSON only.")
            import json
            clean = resp.strip().removeprefix("```json").removesuffix("```").strip()
            data = json.loads(clean)
            en_text = data.get("text_en", "")
            hi_text = data.get("text_hi", "")

            # Strict Guardrail Check
            if not self.verify_numbers(en_text, allowed):
                logger.warning("LLM hallucinated numbers not in breakdown. Falling back to template.")
                return fallback

            en_text = _plain_words(en_text or fallback.text_en)
            hi_text = _plain_words(hi_text or fallback.text_hi)
            if _life_threat(request) and "112" not in en_text:
                en_text += " In an emergency call 112."
            return Explanation(
                text_en=en_text or fallback.text_en,
                text_hi=hi_text or fallback.text_hi,
            )
        except Exception as e:
            logger.info("Explainer LLM generation skipped or failed: %s. Using template fallback.", e)
            return fallback


def _plain_words(text: str) -> str:
    """Internal score field names stay off the card."""
    if not text:
        return text
    text = re.sub(r"urgency[_\s-]*scores?", "how urgent it is", text, flags=re.I)
    text = re.sub(r"(?:total\s+)?match[_\s-]*scores?", "how well this team fits", text, flags=re.I)
    return text


def _life_threat(request: StoredRequest) -> bool:
    from app.agents.intake import _LIFE_THREAT
    kind = getattr(request.type, "value", request.type)
    return kind == "medical" or bool(_LIFE_THREAT.search(request.raw_text or ""))


explainer_agent = ExplainerAgent()
