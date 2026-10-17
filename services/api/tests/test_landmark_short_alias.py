from app.agents.dedupe import gazetteer


def test_short_landmark_name_resolves_like_full_name():
    # "Kainakary jetty" (English) and "കൈനകരി ജെട്ടി" (Malayalam) are the same landmark.
    en = gazetteer.landmark_ids_in("Near Kainakary jetty: six people stuck in a house")
    ml = gazetteer.landmark_ids_in("കൈനകരി ജെട്ടിക്ക് സമീപം 6 പേർ കുടുങ്ങി")
    assert en == {"LM-02"}
    assert ml == {"LM-02"}
