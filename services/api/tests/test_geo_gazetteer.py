from app.tools.geo import haversine_distance, grid_cell_id, is_within_distance
from app.tools.gazetteer import gazetteer


def test_haversine_distance_calculation():
    # Riverbend ward 1 to ward 2 distance (~0.8 to 1.5 km)
    dist = haversine_distance(26.845, 80.932, 26.852, 80.925)
    assert 0.5 < dist < 2.0
    # Zero distance
    assert haversine_distance(26.85, 80.92, 26.85, 80.92) == 0.0


def test_grid_cell_id_anonymization():
    # Two points within ~100m should map to same or adjacent grid cell
    cell1 = grid_cell_id(26.8520, 80.9250)
    cell2 = grid_cell_id(26.8521, 80.9251)
    assert cell1 == cell2
    assert cell1.startswith("cell_")


def test_gandhi_school_ke_paas_resolves_to_seeded_landmark():
    # Hero acceptance criteria: "Gandhi school ke paas" resolves to seeded landmark
    match = gazetteer.lookup("Gandhi school ke paas")
    assert match.is_low_confidence is False
    assert match.landmark_id == "LM-06"
    assert "Gandhi High School" in match.landmark_name
    assert match.ward_id == "ward_2"
    assert match.lat is not None and match.lng is not None
    assert match.cell_id is not None
    assert match.confidence >= 0.8


def test_hindi_script_gandhi_school_resolves():
    match = gazetteer.lookup("गांधी स्कूल के पीछे")
    assert match.is_low_confidence is False
    assert match.landmark_id == "LM-06"
    assert match.ward_id == "ward_2"


def test_unknown_place_flags_low_confidence():
    # Hero acceptance criteria: unknown place -> low confidence flag
    match = gazetteer.lookup("some random imaginary unknown alien place xyz 123")
    assert match.is_low_confidence is True
    assert match.confidence < 0.6
    assert match.landmark_id is None
