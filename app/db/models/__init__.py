from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


from app.db.models.classification_attempt import ClassificationAttempt  # noqa: E402, F401
from app.db.models.ticket import Ticket  # noqa: E402, F401
