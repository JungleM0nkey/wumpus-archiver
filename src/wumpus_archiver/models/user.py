"""User model."""

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from wumpus_archiver.models.base import Base

if TYPE_CHECKING:
    from wumpus_archiver.models.message import Message


class User(Base):
    """Discord user model."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str] = mapped_column(String(100), nullable=False)
    discriminator: Mapped[str | None] = mapped_column(String(4), nullable=True)
    global_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    bot: Mapped[bool] = mapped_column(default=False, nullable=False)

    # Relationships
    messages: Mapped[list["Message"]] = relationship("Message", back_populates="author")

    def __repr__(self) -> str:
        return f"<User(id={self.id}, username={self.username!r})>"

    @property
    def display_name(self) -> str:
        """Return the best display name for the user."""
        return self.global_name or self.username
