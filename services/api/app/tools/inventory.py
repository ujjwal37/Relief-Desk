"""Deterministic logistics for requirements entered by a human, never diagnosed by AI."""
from __future__ import annotations


def missing_supplies(request, resource) -> dict[str, int]:
    return {name: amount - resource.supplies.get(name, 0)
            for name, amount in request.required_supplies.items()
            if resource.supplies.get(name, 0) < amount}


def inventory_note(request, resource) -> str:
    if not request.required_supplies:
        return ""
    items = ", ".join(f"{name.upper()}: {resource.supplies.get(name, 0)} in stock" for name in request.required_supplies)
    return f"Human-entered referral requirement; {items}. Facilities without the required stock are excluded."
