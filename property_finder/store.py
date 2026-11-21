"""JSON listing history. Remembers when each shop was first seen so the daily report can flag new ones."""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from .models import Listing


class Store:
    def __init__(self, path: Path):
        self.path = path
        self.items: dict[str, Listing] = {}
        if path.exists():
            for d in json.loads(path.read_text(encoding="utf-8")):
                l = Listing.from_dict(d)
                self.items[l.key] = l

    def upsert(self, listings: list[Listing], today: str) -> list[Listing]:
        """Add or refresh listings. Returns the ones never seen before."""
        new = []
        for l in listings:
            old = self.items.get(l.key)
            if old:
                # keep the original first_seen and fill in any fields the old copy was missing
                for f, v in l.to_dict().items():
                    if v not in (None, "", {}) and f not in ("first_seen",):
                        setattr(old, f, v)
                old.last_seen = today
            else:
                l.first_seen = l.first_seen or today
                l.last_seen = today
                self.items[l.key] = l
                new.append(l)
        return new

    def active(self, today: str, days: int = 21) -> list[Listing]:
        """Listings seen in the last `days` days. Older ones are probably already let out."""
        cutoff = (date.fromisoformat(today) - timedelta(days=days)).isoformat()
        return [l for l in self.items.values() if (l.last_seen or today) >= cutoff]

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = sorted((l.to_dict() for l in self.items.values()), key=lambda d: d["first_seen"])
        self.path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
