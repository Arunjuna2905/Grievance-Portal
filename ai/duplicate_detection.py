def find_duplicate(description, latitude, longitude, complaints, department=None):
    words = {w for w in description.lower().split() if len(w) > 3}
    for complaint in complaints:
        if department and complaint.get("department") != department:
            continue
        old = {w for w in complaint["description"].lower().split() if len(w) > 3}
        nearby = latitude is not None and longitude is not None and complaint["latitude"] is not None and abs(latitude-complaint["latitude"]) < .01 and abs(longitude-complaint["longitude"]) < .01
        if len(words & old) / max(1, len(words | old)) >= .3 and (nearby or latitude is None): return complaint["id"]
    return None
