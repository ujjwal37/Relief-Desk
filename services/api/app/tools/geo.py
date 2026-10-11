import math
from typing import Tuple


EARTH_RADIUS_KM = 6371.0


def haversine_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Computes great-circle distance between two points on Earth in kilometers."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lng2 - lng1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return round(EARTH_RADIUS_KM * c, 3)


def grid_cell_id(lat: float, lng: float, cell_size_km: float = 0.5) -> str:
    """Maps (lat, lng) to an area-level ~500 m grid cell ID.
    Zero exact PII is leaked when publishing area cells."""
    # 1 degree of latitude is approximately 111.139 km
    lat_step = cell_size_km / 111.139
    # Longitude step adjusts for latitude
    lng_step = cell_size_km / (111.139 * max(0.1, math.cos(math.radians(lat))))

    cell_lat_idx = int(math.floor(lat / lat_step))
    cell_lng_idx = int(math.floor(lng / lng_step))
    return f"cell_{cell_lat_idx}_{cell_lng_idx}"


def is_within_distance(
    lat1: float, lng1: float, lat2: float, lng2: float, max_km: float = 3.0
) -> bool:
    """Checks whether two locations are within a specified distance in km."""
    return haversine_distance(lat1, lng1, lat2, lng2) <= max_km
