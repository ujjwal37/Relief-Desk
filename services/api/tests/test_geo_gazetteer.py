from app.tools.geo import haversine_distance, grid_cell_id, is_within_distance
from app.tools.gazetteer import gazetteer


def test_haversine_distance_calculation():
    # Kainakary to Champakulam is a few kilometres.
    dist = haversine_distance(9.470, 76.390, 9.416, 76.411)
    assert 4.0 < dist < 10.0
    assert haversine_distance(10.50, 76.30, 10.50, 76.30) == 0.0


def test_grid_cell_id_anonymization():
    # Two points within ~100m should map to same or adjacent grid cell
    cell1 = grid_cell_id(26.8520, 80.9250)
    cell2 = grid_cell_id(26.8521, 80.9251)
    assert cell1 == cell2
    assert cell1.startswith("cell_")


def test_champakulam_school_ke_paas_resolves_to_seeded_landmark():
    match = gazetteer.lookup("Champakulam school ke paas")
    assert match.is_low_confidence is False
    assert match.landmark_id == "LM-06"
    assert "Champakulam School" in match.landmark_name
    assert match.ward_id == "ward_2"
    assert match.lat is not None and match.lng is not None
    assert match.cell_id is not None
    assert match.confidence >= 0.8


def test_hindi_script_champakulam_school_resolves():
    match = gazetteer.lookup("चम्पाकुलाम स्कूल के पीछे")
    assert match.is_low_confidence is False
    assert match.landmark_id == "LM-06"
    assert match.ward_id == "ward_2"


def test_unknown_place_flags_low_confidence():
    # Hero acceptance criteria: unknown place -> low confidence flag
    match = gazetteer.lookup("some random imaginary unknown alien place xyz 123")
    assert match.is_low_confidence is True
    assert match.confidence < 0.6
    assert match.landmark_id is None
