REQUIRED_COLUMNS = [
    "date",
    "card_name",
    "set_name",
    "card_number",
    "condition",
    "price",
]

# Optional columns the app can use if present.
OPTIONAL_COLUMNS = [
    "variant",
    "expansion_code",
    "tcgplayer_id",
]

VALID_GRANULARITIES = {"daily", "weekly"}
