from sqlalchemy import Column, DateTime, ForeignKey, Table, Uuid, func

from app.db.base import Base

""" Relationship table for many-to-many relationship between accounts and users. """

account_users = Table(
    "folio_account_users",
    Base.metadata,
    Column(
        "account_id",
        Uuid,
        ForeignKey("folio_accounts.account_id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "user_id",
        Uuid,
        ForeignKey("folio_users.user_id", ondelete="RESTRICT"),
        primary_key=True,
        index=True,
    ),
    Column("added_timestamp", DateTime(timezone=True), server_default=func.now(), nullable=False),
)