"""
Servicio Geoespacial (GIS) para EduAgro.
Proporciona funciones para el cálculo de área en hectáreas (ha), perímetro en metros/kilómetros y centroide (lat, lng)
de polígonos GeoJSON (RFC 7946) utilizando la fórmula geodésica sobre la esfera terrestre WGS84.
"""

import math
from typing import Dict, Any, Tuple, Optional, List

# Radio medio terrestre WGS84 en metros
EARTH_RADIUS_METERS = 6371008.8


def haversine_distance_meters(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Calcula la distancia geodésica en metros entre dos puntos (lat, lng) usando la fórmula de Haversine."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)

    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlng / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return EARTH_RADIUS_METERS * c


def calcular_area_esferica_m2(coordinates_ring: List[List[float]]) -> float:
    """
    Calcula la superficie en metros cuadrados (m²) de un anillo de coordenadas GeoJSON [[lng, lat], ...]
    utilizando el método del exceso esférico de Gauss para coordenadas geográficas en radianes.
    """
    num_points = len(coordinates_ring)
    if num_points < 4:
        return 0.0

    total_sum = 0.0
    for i in range(num_points - 1):
        p1 = coordinates_ring[i]
        p2 = coordinates_ring[i + 1]

        lng1_rad = math.radians(p1[0])
        lat1_rad = math.radians(p1[1])
        lng2_rad = math.radians(p2[0])
        lat2_rad = math.radians(p2[1])

        total_sum += (lng2_rad - lng1_rad) * (2.0 + math.sin(lat1_rad) + math.sin(lat2_rad))

    area_m2 = abs(total_sum * (EARTH_RADIUS_METERS ** 2) / 2.0)
    return area_m2


def calcular_perimetro_metros(coordinates_ring: List[List[float]]) -> float:
    """Calcula el perímetro total en metros de un anillo cerrado de coordenadas [[lng, lat], ...]."""
    num_points = len(coordinates_ring)
    if num_points < 2:
        return 0.0

    perimetro = 0.0
    for i in range(num_points - 1):
        p1 = coordinates_ring[i]
        p2 = coordinates_ring[i + 1]
        perimetro += haversine_distance_meters(p1[1], p1[0], p2[1], p2[0])

    return perimetro


def calcular_centroide(coordinates_ring: List[List[float]]) -> Tuple[float, float]:
    """Calcula el punto de centroide (latitud, longitud) del anillo de coordenadas."""
    if not coordinates_ring:
        return 0.0, 0.0

    pts = coordinates_ring[:-1] if len(coordinates_ring) > 1 else coordinates_ring
    if not pts:
        pts = coordinates_ring

    sum_lat = sum(p[1] for p in pts)
    sum_lng = sum(p[0] for p in pts)
    count = len(pts)

    return round(sum_lat / count, 6), round(sum_lng / count, 6)


def validar_poligono_geojson(geojson_dict: Dict[str, Any]) -> Tuple[bool, str]:
    """Valida la estructura y cierre de un polígono GeoJSON."""
    if not isinstance(geojson_dict, dict):
        return False, "El parámetro debe ser un diccionario GeoJSON válido."

    geo_type = geojson_dict.get("type")
    if geo_type != "Polygon":
        return False, f"Se esperaba un objeto de tipo 'Polygon', pero se obtuvo '{geo_type}'."

    coordinates = geojson_dict.get("coordinates")
    if not isinstance(coordinates, list) or not coordinates:
        return False, "La propiedad 'coordinates' debe ser una lista no vacía."

    outer_ring = coordinates[0]
    if not isinstance(outer_ring, list) or len(outer_ring) < 4:
        return False, "El anillo exterior del polígono debe contener al menos 4 puntos [longitud, latitud]."

    first_pt = outer_ring[0]
    last_pt = outer_ring[-1]

    if abs(first_pt[0] - last_pt[0]) > 1e-7 or abs(first_pt[1] - last_pt[1]) > 1e-7:
        # Cerrar el anillo automáticamente
        outer_ring.append([first_pt[0], first_pt[1]])

    return True, "Polígono válido."


def procesar_geometria_lote(geojson_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Procesa un objeto GeoJSON de tipo Polygon y retorna las métricas calculadas:
    - superficie_calculada_gis_ha (float)
    - perimetro_calculado_m (float)
    - centroide_lat (float)
    - centroide_lng (float)
    - geojson_normalizado (dict)
    """
    es_valido, msg = validar_poligono_geojson(geojson_dict)
    if not es_valido:
        raise ValueError(msg)

    outer_ring = geojson_dict["coordinates"][0]
    area_m2 = calcular_area_esferica_m2(outer_ring)
    perimetro_m = calcular_perimetro_metros(outer_ring)
    lat_cent, lng_cent = calcular_centroide(outer_ring)

    superficie_ha = round(area_m2 / 10000.0, 4)
    perimetro_m_round = round(perimetro_m, 2)

    return {
        "superficie_calculada_gis_ha": superficie_ha,
        "perimetro_calculado_m": perimetro_m_round,
        "perimetro_calculado_km": round(perimetro_m_round / 1000.0, 3),
        "centroide_lat": lat_cent,
        "centroide_lng": lng_cent,
        "geojson": geojson_dict,
    }
