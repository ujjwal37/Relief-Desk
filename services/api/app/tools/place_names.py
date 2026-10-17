"""English place names for Malayalam and Hindi place words, so the desk reads "Champakulam church"."""
import re

_WORDS = {
    "ചമ്പക്കുളം": "Champakulam", "കൈനകരി": "Kainakary", "നെടുമുടി": "Nedumudi", "പുളിങ്കുന്ന്": "Pulinkunnu",
    "കാവാലം": "Kavalam", "രാമങ്കരി": "Ramankary", "തലവടി": "Thalavady", "മങ്കൊമ്പ്": "Moncompu", "എടത്വ": "Edathua",
    "വെളിയനാട്": "Veliyanad", "മുട്ടാർ": "Muttar", "തകഴി": "Thakazhy", "ആലപ്പുഴ": "Alappuzha", "കുട്ടനാട്": "Kuttanad",
    "തോട്ടപ്പള്ളി": "Thottappally",
    "പള്ളി": "church", "പള്ളിക്ക്": "church", "പള്ളിയുടെ": "church", "അമ്പലം": "temple", "ക്ഷേത്രം": "temple",
    "ജെട്ടി": "jetty", "ജെട്ടിക്ക്": "jetty", "ബോട്ട്": "boat", "സ്കൂൾ": "school", "മാർക്കറ്റ്": "market", "ചന്ത": "market",
    "പാലം": "bridge", "റോഡ്": "road", "ആശുപത്രി": "hospital", "ക്യാമ്പ്": "camp",
    "नेदुमुडी": "Nedumudi", "चंपकुलम": "Champakulam", "कैनकरी": "Kainakary",
}
_NON_LATIN = re.compile(r"[\u0900-\u097F\u0D00-\u0D7F]")


def english_place(text):
    """Swap known words; drop a doubled word ("bridge bridge"). Unknown script words stay as written."""
    if not text:
        return text
    if _NON_LATIN.search(text):
        out = []
        for tok in re.split(r"(\s+)", text):
            key = tok.strip(".,")
            out.append(_WORDS.get(key, tok))
        text = "".join(out)
    text = re.sub(r"\b(\w+)(\s+\1\b)+", r"\1", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip()
