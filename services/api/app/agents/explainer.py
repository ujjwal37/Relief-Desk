import logging
import re
from typing import List, Optional, Set
from app.config import settings
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
        people = request.people_count if request.people_count else 1
        text_en = (
            f"{resource.name} is {breakdown.distance_km} km away with {resource.capacity_remaining} capacity "
            f"to assist {people} people. Total match score is {breakdown.total_score} based on proximity and urgency."
        )

        res_name_hi = resource.name_hi or resource.name
        text_hi = (
            f"{res_name_hi} {breakdown.distance_km} किमी दूर है और {people} लोगों की सहायता के लिए उपलब्ध है। "
            f"कुल मिलान स्कोर {breakdown.total_score} है।"
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

        if not settings.GEMINI_ENABLED:
            return fallback

        prompt = (
            f"Explain why {resource.name} is matched to this rescue request in <= 2 sentences.\n"
            f"Input numbers:\n"
            f"- Distance: {breakdown.distance_km} km (score: {breakdown.distance_score})\n"
            f"- Capacity remaining: {resource.capacity_remaining} (needed: {request.people_count or 1})\n"
            f"- Urgency score: {breakdown.urgency_score}\n"
            f"- Vulnerability score: {breakdown.vulnerability_fit_score}\n"
            f"- Total match score: {breakdown.total_score}\n"
            f"RULE: Cite ONLY these provided numbers. Do not invent any numbers.\n"
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

            return Explanation(
                text_en=en_text or fallback.text_en,
                text_hi=hi_text or fallback.text_hi,
            )
        except Exception as e:
            logger.info("Explainer LLM generation skipped or failed: %s. Using template fallback.", e)
            return fallback


explainer_agent = ExplainerAgent()
