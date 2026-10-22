from dataclasses import dataclass

# Bounds what one request can write: the model fills these fields from user input.
TITLE_MAX_LENGTH = 120
DESCRIPTION_MAX_LENGTH = 2000


class InvalidTicket(ValueError):
    """The ticket fields break a domain rule; nothing was stored."""


def validate_ticket_fields(title: str, description: str) -> None:
    for name, value, limit in (("title", title, TITLE_MAX_LENGTH), ("description", description, DESCRIPTION_MAX_LENGTH)):
        if len(value) > limit:
            raise InvalidTicket("%s must be at most %d characters" % (name, limit))


@dataclass(frozen=True)
class Ticket:
    id: str
    title: str
    description: str
