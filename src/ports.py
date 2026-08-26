"""
Major Indian ports (incoming / outgoing traffic) plus a few common
foreign destination ports Indian ships sail to.

Coordinates are the approximate sea approach (slightly offshore) so the
endpoint lands on open water rather than inside a harbour/land cell.
"""

# name -> (lat, lon).  West coast, east coast, islands, foreign approaches.
PORTS = {
    # ---- West coast (Arabian Sea) ----
    "Mundra (Gujarat)":            (22.74, 69.70),
    "Kandla (Gujarat)":            (22.90, 70.10),
    "Mumbai (JNPT)":               (18.85, 72.85),
    "Mormugao (Goa)":              (15.35, 73.75),
    "New Mangalore (Karnataka)":   (12.90, 74.75),
    "Cochin (Kerala)":             (9.90, 76.20),
    # ---- Southern tip ----
    "Vizhinjam (Kerala)":          (8.35, 76.95),
    "Tuticorin (Tamil Nadu)":      (8.72, 78.25),
    # ---- East coast (Bay of Bengal) ----
    "Chennai (Tamil Nadu)":        (13.10, 80.35),
    "Ennore/Kamarajar (TN)":       (13.28, 80.40),
    "Krishnapatnam (AP)":          (14.25, 80.20),
    "Visakhapatnam (AP)":          (17.65, 83.35),
    "Paradip (Odisha)":            (20.25, 86.75),
    "Haldia/Kolkata (WB)":         (21.60, 88.10),
    # ---- Islands ----
    "Port Blair (Andaman)":        (11.65, 92.75),
    # ---- Common foreign approaches ----
    "Colombo (Sri Lanka)":         (6.90, 79.75),
    # Jebel Ali sits deep inside the Persian Gulf behind the narrow Strait
    # of Hormuz (which the 22 km safety buffer closes), so we use the
    # open-sea UAE approach on the Gulf of Oman side (Fujairah).
    "Dubai / Jebel Ali (UAE)":     (25.12, 56.38),
    "Salalah (Oman)":              (16.90, 54.00),
    "Malacca Strait approach":     (4.00, 99.00),
}


def port_list():
    """Sorted list of port names for UI dropdowns."""
    return sorted(PORTS.keys())


def coord(name):
    """(lat, lon) for a port name."""
    return PORTS[name]
