from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FailFlags:
    portal_remaining: int = 0
    ledger_remaining: int = 0
    notes: list[str] = field(default_factory=list)

    def arm(self, target: str, count: int = 1) -> str:
        if target == "portal":
            self.portal_remaining = count
        elif target == "ledger":
            self.ledger_remaining = count
        else:
            raise ValueError(f"Unknown fail target: {target}")
        msg = f"Armed {target} to fail {count} time(s)"
        self.notes.append(msg)
        return msg

    def hit_portal(self) -> bool:
        if self.portal_remaining > 0:
            self.portal_remaining -= 1
            return True
        return False

    def hit_ledger(self) -> bool:
        if self.ledger_remaining > 0:
            self.ledger_remaining -= 1
            return True
        return False

    def snapshot(self) -> dict[str, int | list[str]]:
        return {
            "portal_remaining": self.portal_remaining,
            "ledger_remaining": self.ledger_remaining,
            "notes": list(self.notes[-8:]),
        }


FLAGS = FailFlags()
