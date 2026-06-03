"""
Team-name normalisation across sources.

Canonical names follow football-data.co.uk style (the backbone source).
ALIASES maps other-source spellings (Understat, openfootball, API-Football)
to the canonical name so the same club joins cleanly across datasets.

Extend ALIASES as new mismatches surface during ingest.
"""
from __future__ import annotations

# variant (lowercased) -> canonical name
ALIASES = {
    # England
    "manchester united": "Man United",
    "man utd": "Man United",
    "manchester city": "Man City",
    "newcastle united": "Newcastle",
    "newcastle utd": "Newcastle",
    "tottenham hotspur": "Tottenham",
    "spurs": "Tottenham",
    "wolverhampton wanderers": "Wolves",
    "wolverhampton": "Wolves",
    "brighton & hove albion": "Brighton",
    "brighton and hove albion": "Brighton",
    "west ham united": "West Ham",
    "nottingham forest": "Nott'm Forest",
    "sheffield united": "Sheffield United",
    "sheffield utd": "Sheffield United",
    "leeds united": "Leeds",
    "leicester city": "Leicester",
    "norwich city": "Norwich",
    "cardiff city": "Cardiff",
    "stoke city": "Stoke",
    "swansea city": "Swansea",
    "hull city": "Hull",
    # Spain
    "atletico madrid": "Ath Madrid",
    "atletico de madrid": "Ath Madrid",
    "athletic club": "Ath Bilbao",
    "athletic bilbao": "Ath Bilbao",
    "real betis": "Betis",
    "celta vigo": "Celta",
    "rayo vallecano": "Vallecano",
    "real sociedad": "Sociedad",
    "deportivo alaves": "Alaves",
    "fc barcelona": "Barcelona",
    "real madrid cf": "Real Madrid",
    # Italy
    "internazionale": "Inter",
    "inter milan": "Inter",
    "ac milan": "Milan",
    "as roma": "Roma",
    "ssc napoli": "Napoli",
    "hellas verona": "Verona",
    "juventus fc": "Juventus",
    # Germany
    "bayern munich": "Bayern Munich",
    "fc bayern munchen": "Bayern Munich",
    "borussia dortmund": "Dortmund",
    "borussia monchengladbach": "M'gladbach",
    "bayer leverkusen": "Leverkusen",
    "eintracht frankfurt": "Ein Frankfurt",
    "rb leipzig": "RB Leipzig",
    "vfb stuttgart": "Stuttgart",
    "vfl wolfsburg": "Wolfsburg",
    "fc koln": "FC Koln",
    "1. fc koln": "FC Koln",
    "werder bremen": "Werder Bremen",
    # France
    "paris saint-germain": "Paris SG",
    "paris saint germain": "Paris SG",
    "psg": "Paris SG",
    "olympique marseille": "Marseille",
    "olympique de marseille": "Marseille",
    "olympique lyonnais": "Lyon",
    "as monaco": "Monaco",
    "lille osc": "Lille",
    "stade rennais": "Rennes",
    "ogc nice": "Nice",
}


def canonical(name: str) -> str:
    """Return canonical team name for any source spelling."""
    if not name:
        return ""
    key = name.strip().lower()
    if key in ALIASES:
        return ALIASES[key]
    # default: return original trimmed (football-data names are canonical)
    return name.strip()
