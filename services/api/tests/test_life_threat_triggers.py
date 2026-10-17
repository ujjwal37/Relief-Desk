"""The life-threat lane works in every language a Kuttanad reporter uses."""
import pytest

from app.tools.case_queue import life_phrase

HITS = [
    ("Kainakary: my father is not breathing, water rising fast", "not breathing"),
    ("my mother stopped breathing", "stopped breathing"),
    ("grandfather is unconscious on the roof", "unconscious"),
    ("a child is drowning near the jetty", "drowning"),
    ("heavy bleeding from his leg", "heavy bleeding"),
    ("he has chest pain and water is rising", "chest pain"),
    ("my son fell in the water", "son fell in the water"),
    ("अप्पा की सांस नहीं चल रही", "सांस नहीं"),
    ("पिताजी बेहोश हैं", "बेहोश"),
    ("बच्चा डूब रहा है", "डूब रहा"),
    ("papa ki saans nahi chal rahi", "saans nahi"),
    ("dadi behosh ho gayi", "behosh"),
    ("അച്ഛന് ശ്വാസം ഇല്ല, വെള്ളം കയറുന്നു", "ശ്വാസം ഇല്ല"),
    ("അച്ഛന് ശ്വാസമില്ല", "ശ്വാസമില്ല"),
    ("അച്ഛൻ ശ്വസിക്കുന്നില്ല", "ശ്വസിക്കുന്നില്ല"),
    ("അമ്മയ്ക്ക് ബോധമില്ല", "ബോധമില്ല"),
    ("കുട്ടി മുങ്ങിപ്പോയി", "മുങ്ങിപ്പോയി"),
    ("അച്ഛന് നെഞ്ചുവേദന", "നെഞ്ചുവേദന"),
    ("achan shwasam illa, vellam kerunnu", "shwasam illa"),
    ("ammachikku bodham illa", "bodham illa"),
    ("appachan anakkam illa", "anakkam illa"),
    # QA r4, RD-7701: Malayalam jetty report, 12 people, child not breathing.
    ("ജെട്ടിയിൽ 12 പേർ കുടുങ്ങി, കുട്ടി ശ്വസിക്കുന്നില്ല", "ശ്വസിക്കുന്നില്ല"),
    ("കുട്ടി ശ്വാസം എടുക്കുന്നില്ല", "ശ്വാസം"),
    ("kutti swasikkunnilla", "swasikkunnilla"),
    ("बच्चा सांस नहीं ले रहा", "सांस नहीं"),
    ("baccha saans nahi le raha", "saans nahi"),
    ("12 people at the jetty, a child is not breathing", "not breathing"),
]


@pytest.mark.parametrize("text,words", HITS)
def test_trigger_hits_in_original_script(text, words):
    hit = life_phrase(text)
    assert hit is not None, text
    assert words.lower() in hit.lower() or hit.lower() in text.lower()


@pytest.mark.parametrize("text", [
    "4 people on the roof, water at waist level",
    "he was not breathing well yesterday, now ok",
    "Nobody stranded here, just asking about the road",
    "घर डूब गया, 3 लोग छत पर हैं",
    "വീട് മുങ്ങി, 3 പേർ ടെറസിൽ",
])
def test_no_false_alarm(text):
    assert life_phrase(text) is None


def test_same_sentence_every_language_gets_the_lane():
    same = [
        "my father is not breathing",
        "पिताजी की सांस नहीं चल रही",
        "papa ki saans nahi chal rahi",
        "അച്ഛന് ശ്വാസം ഇല്ല",
        "achan shwasam illa",
    ]
    assert all(life_phrase(text) for text in same)
