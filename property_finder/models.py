from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field


@dataclass
class Listing:
    title: str = ""
    locality: str = ""            # canonical locality name, e.g. "Miyapur"
    address: str = ""
    rent: int | None = None       # monthly rent, INR
    area_sqft: int | None = None  # carpet/super area in sqft
    deposit: int | None = None
    floor: str = ""               # "ground", "1", ...
    outdoor: bool | None = None   # True when an outdoor / sit-out / frontage space is mentioned
    description: str = ""
    url: str = ""
    source: str = ""              # magicbricks / nobroker / manual / ...
    contact: str = ""
    first_seen: str = ""
    last_seen: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def key(self) -> str:
        """Stable ID used to de-duplicate the same shop posted on several portals."""
        if self.url:
            basis = re.sub(r"[?#].*$", "", self.url.strip().lower())
        else:
            basis = "|".join([
                self.locality.lower(),
                str(self.rent or ""),
                str(self.area_sqft or ""),
                re.sub(r"\W+", "", (self.address or self.title).lower())[:40],
            ])
        return hashlib.sha1(basis.encode()).hexdigest()[:12]

    @property
    def text(self) -> str:
        return " ".join([self.title, self.address, self.description, self.floor]).lower()

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Listing":
        known = {k: d[k] for k in cls.__dataclass_fields__ if k in d}
        return cls(**known)
