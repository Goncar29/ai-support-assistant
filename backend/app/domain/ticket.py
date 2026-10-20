from dataclasses import dataclass


@dataclass(frozen=True)
class Ticket:
    id: str
    title: str
    description: str
