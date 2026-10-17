from app.tools.nlu_rules import place_is_usable


def test_kuttanad_panchayats_are_places():
    for place in ("Ramankari", "Kuttanad, Ramankari", "Mankombu", "Thakazhy", "Edathua"):
        assert place_is_usable(place), place


def test_junk_still_rejected():
    for junk in ("near the bridge", "Emergency report", "asdf", "bit.ly", "Kuttanad, please help"):
        assert not place_is_usable(junk), junk
