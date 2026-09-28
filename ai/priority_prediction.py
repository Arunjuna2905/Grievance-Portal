"""
AI Priority Prediction for SmartGov grievances.

Reads the complaint title + description and assigns one of three levels:
  High   — urgent, safety risk, large-scale disruption, no essential service
  Medium — significant inconvenience, affecting multiple people, degraded service
  Low    — minor issue, cosmetic, localised, or inconvenience only

Logic:
  1. Check HIGH keywords first (safety / life / essential service failure)
  2. Check LOW keywords (cosmetic / minor / single-person issues)
  3. Everything else → Medium
"""

# ── HIGH priority: safety hazards, total service failure, health risk ─────────
HIGH_KEYWORDS = [
    # Water
    "no water", "no water supply", "water not coming", "water supply stopped",
    "water cut", "contaminated water", "dirty water", "sewage overflow",
    "sewage spill", "sewage leak", "pipeline burst", "pipe burst", "main burst",
    # Road / PWD
    "road collapsed", "bridge collapsed", "road accident", "major pothole",
    "road flooded", "road blocked", "road damage", "dangerous road",
    # Electricity
    "no electricity", "power cut", "power outage", "no power",
    "electric shock", "electrocution", "live wire", "exposed wire",
    "wire fallen", "transformer blast", "fire", "sparking wire",
    # Drainage / Flood
    "flood", "flooding", "waterlogging", "water logging",
    "drain overflow", "drain blocked", "sewage on road",
    "stagnant water", "manhole open", "open manhole", "manhole uncovered",
    # Health / Emergency
    "danger", "dangerous", "hazard", "emergency", "accident",
    "collapsed", "collapse", "fallen tree", "tree fallen", "wall collapsed",
    "gas leak", "fire breakout", "burning", "disease", "epidemic",
    "health risk", "contamination", "mosquito breeding",
    # Municipal
    "garbage not collected", "waste overflow", "overflowing bin",
    "days without", "weeks without", "month without", "not coming for",
    "did not come for", "no collection", "stopped",
]

# ── LOW priority: minor, cosmetic, small-scale ────────────────────────────────
LOW_KEYWORDS = [
    # Minor inconvenience
    "small", "minor", "slight", "tiny", "little",
    # Cosmetic / appearance
    "paint", "faded", "dirty wall", "broken bench", "broken sign",
    "broken gate", "broken fence", "park bench", "street sign",
    # Noise / smell (non-urgent)
    "noise", "smell", "odour", "odor",
    # Billing / administrative
    "wrong bill", "billing issue", "meter reading", "meter error",
    "request", "application", "certificate", "noc", "permission",
    # Single-person issues
    "my house", "my home", "my meter", "my connection",
    "single house", "one house", "one building",
    # Street light (non-hazardous)
    "streetlight not working", "streetlight fused", "one streetlight",
    # Low urgency
    "suggestion", "feedback", "improvement", "beautify", "beautification",
    "garden", "park maintenance", "tree trimming", "tree pruning",
]

# ── Urgency intensifiers (push toward High) ───────────────────────────────────
URGENCY_PHRASES = [
    "past 2 days", "past 3 days", "past 4 days", "past 5 days",
    "past week", "past month", "since days", "since weeks",
    "not working for", "no supply for", "without water for",
    "urgent", "immediately", "asap", "please help", "serious problem",
    "affecting many", "whole area", "entire street", "entire colony",
    "everyone", "all residents", "public issue",
]


def predict_priority(text: str, category: str = "") -> str:
    """
    Analyse complaint text and category to assign High / Medium / Low priority.
    """
    value = f"{text} {category}".lower()

    # ── Step 1: Check HIGH keywords ──────────────────────────────────────────
    for kw in HIGH_KEYWORDS:
        if kw in value:
            return "High"

    # ── Step 2: Check urgency boosters → push to High ────────────────────────
    urgency_count = sum(1 for phrase in URGENCY_PHRASES if phrase in value)
    if urgency_count >= 2:
        return "High"

    # ── Step 3: Check LOW keywords ───────────────────────────────────────────
    for kw in LOW_KEYWORDS:
        if kw in value:
            # Even if low keyword found, check single urgency booster
            if urgency_count >= 1:
                return "Medium"
            return "Low"

    # ── Step 4: Category-based default ──────────────────────────────────────
    HIGH_CATEGORIES = {"water supply", "drainage", "electricity"}
    LOW_CATEGORIES  = {"municipal"}  # unless urgency boosters found

    cat_lower = category.lower()
    if cat_lower in HIGH_CATEGORIES:
        return "Medium"   # at least medium for essential services
    if cat_lower in LOW_CATEGORIES and urgency_count == 0:
        return "Low"

    return "Medium"
