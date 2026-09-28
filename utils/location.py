def valid_coordinates(latitude, longitude):
    try: return -90 <= float(latitude) <= 90 and -180 <= float(longitude) <= 180
    except (ValueError, TypeError): return False
