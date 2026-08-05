"""Final promotion policy after manual review of ambiguous exact-slug boards."""
from __future__ import annotations

import promote_discovered_sources as promotion


promotion.GENERIC_BOARD_WORDS.add("io")  # Honeycomb.io is Honeycomb's official board.
promotion.KNOWN_INVALID.update({
    # This is a US healthcare staffing company, not Porter India logistics.
    ("porter", "lever"),
    # This is the Portugal/US luggage-storage company, not Bounce India mobility.
    ("bounce", "ashby"),
})


if __name__ == "__main__":
    raise SystemExit(promotion.main())
