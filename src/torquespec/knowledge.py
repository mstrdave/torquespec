"""Reference data for the 1990 Miata: loading, search and rendering for the LLM prompt."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from typing import Any

FT_LB_TO_NM = 1.35582
IN_LB_TO_NM = 0.112985


def _load(name: str) -> Any:
    return json.loads(resources.files("torquespec.data").joinpath(name).read_text(encoding="utf-8"))


@dataclass(frozen=True)
class TorqueSpec:
    system: str
    component: str
    low: float
    high: float
    unit: str  # "ft-lb" or "in-lb"
    notes: str
    verify: bool

    @property
    def nm(self) -> tuple[float, float]:
        k = FT_LB_TO_NM if self.unit == "ft-lb" else IN_LB_TO_NM
        return round(self.low * k, 1), round(self.high * k, 1)

    def to_dict(self) -> dict[str, Any]:
        lo, hi = self.nm
        return {
            "system": self.system,
            "component": self.component,
            "range": f"{self.low:g} to {self.high:g} {self.unit}",
            "nm": f"{lo:g} to {hi:g} N·m",
            "notes": self.notes,
            "verify": self.verify,
        }


@dataclass(frozen=True)
class KnowledgeBase:
    vehicle: dict[str, Any]
    torque: tuple[TorqueSpec, ...]
    codes: dict[str, Any]
    issues: tuple[dict[str, Any], ...]

    def search_torque(self, query: str = "") -> list[TorqueSpec]:
        words = query.lower().split()
        if not words:
            return list(self.torque)
        return [
            t for t in self.torque
            if all(w in f"{t.system} {t.component} {t.notes}".lower() for w in words)
        ]

    def lookup_code(self, code: str) -> dict[str, Any] | None:
        code = code.strip().zfill(2)
        return next((c for c in self.codes["codes"] if c["code"] == code), None)

    def match_issues(self, text: str, limit: int = 3) -> list[dict[str, Any]]:
        """Rank known issues by how many of their symptom words appear in the text."""
        text = text.lower()
        scored = []
        for issue in self.issues:
            vocab = {w for s in issue["symptoms"] for w in s.lower().split() if len(w) > 3}
            score = sum(1 for w in vocab if w in text)
            if score:
                scored.append((score, issue))
        scored.sort(key=lambda s: -s[0])
        return [i for _, i in scored[:limit]]

    def render_reference(self) -> str:
        """Deterministic text block used in the system prompt (stable so it caches)."""
        v = self.vehicle
        out = [f"# Reference data: {v['name']}", "", "## Engine"]
        out += [f"- {k.replace('_', ' ')}: {val}" for k, val in v["engine"].items()]
        out += ["", "## Tune-up"]
        out += [f"- {t['item']}: {t['value']}{' [verify]' if t.get('verify') else ''}" for t in v["tune_up"]]
        out += ["", "## Fluids"]
        out += [
            f"- {f['system']}: {f['spec']}, {f['capacity']}{' [verify]' if f.get('verify') else ''}"
            for f in v["fluids"]
        ]
        out += ["", "## Torque specs"]
        for t in self.torque:
            d = t.to_dict()
            note = f" ({d['notes']})" if d["notes"] else ""
            out.append(f"- {d['component']}: {d['range']} / {d['nm']}{note}{' [verify]' if t.verify else ''}")
        out += ["", "## Flash codes (jumper TEN to GND, ignition on, count check engine light flashes)"]
        out += [f"- {c['code']}: {c['circuit']}. Checks: {c['checks']}" for c in self.codes["codes"]]
        out += ["", "## Known issues on this model"]
        for i in self.issues:
            out.append(f"- {i['title']} [{i['severity']}]: {i['cause']} Fix: {i['fix']}")
        return "\n".join(out)


@lru_cache(maxsize=1)
def load() -> KnowledgeBase:
    torque = []
    for row in _load("torque_specs.json"):
        unit = "ft-lb" if "ft_lb" in row else "in-lb"
        low, high = row["ft_lb"] if unit == "ft-lb" else row["in_lb"]
        torque.append(TorqueSpec(row["system"], row["component"], low, high, unit,
                                 row.get("notes", ""), row.get("verify", False)))
    return KnowledgeBase(
        vehicle=_load("vehicle.json"),
        torque=tuple(torque),
        codes=_load("trouble_codes.json"),
        issues=tuple(_load("known_issues.json")),
    )
