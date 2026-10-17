from types import SimpleNamespace

from app.models.firestore_models import HazardType, IncidentType
from app.tools.scoring import scoring_engine


def _req(text, people=3):
    return SimpleNamespace(
        vulnerable=SimpleNamespace(child=False, elderly=False, disabled=False, pregnant=False, medical_need=False),
        hazard=HazardType.STRANDED, type=IncidentType.RESCUE, people_count=people,
    )


def test_roof_with_everything_below_submerged_is_urgent():
    for text in (
        "In Muttar, 3 of us are on the roof, everything below is submerged, please help",
        "मुट्टार में हम 3 लोग छत पर हैं, नीचे सब डूब गया है",
    ):
        tier, _ = scoring_engine.tier_for(_req(text), text, 0)
        assert tier == "urgent", text


def test_roof_alone_without_water_words_is_not_raised():
    text = "We fixed the roof, 3 people are fine"
    tier, _ = scoring_engine.tier_for(_req(text), text, 0)
    assert tier == "standard"
