import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Numeric, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    username: Mapped[str] = mapped_column(Text, unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Bill(Base):
    __tablename__ = "bills"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    slug: Mapped[str] = mapped_column(Text, unique=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(Enum("open", "done", "cancelled", name="bill_status"), server_default="open")
    merchant: Mapped[str | None] = mapped_column(Text)
    bill_date: Mapped[date | None]
    currency: Mapped[str] = mapped_column(Text, server_default="INR")
    subtotal_paise: Mapped[int] = mapped_column(BigInteger)
    total_paise: Mapped[int] = mapped_column(BigInteger)
    tip_paise: Mapped[int] = mapped_column(BigInteger, server_default="0")
    tip_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    version: Mapped[int] = mapped_column(server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    owner: Mapped["User"] = relationship()
    items: Mapped[list["BillItem"]] = relationship(order_by="BillItem.position")
    charges: Mapped[list["BillCharge"]] = relationship(order_by="BillCharge.position")
    participants: Mapped[list["Participant"]] = relationship(order_by="[Participant.joined_at, Participant.id]")


class BillItem(Base):
    __tablename__ = "bill_items"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    bill_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bills.id", ondelete="CASCADE"))
    position: Mapped[int]
    name: Mapped[str] = mapped_column(Text)
    quantity: Mapped[Decimal] = mapped_column(Numeric(10, 3))
    unit_price_paise: Mapped[int | None] = mapped_column(BigInteger)
    line_total_paise: Mapped[int] = mapped_column(BigInteger)

    claims: Mapped[list["Claim"]] = relationship()


class BillCharge(Base):
    __tablename__ = "bill_charges"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    bill_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bills.id", ondelete="CASCADE"))
    position: Mapped[int]
    label: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Enum("tax", "service_charge", "discount", "round_off", "other", name="charge_kind"))
    rate_percent: Mapped[Decimal | None] = mapped_column(Numeric(6, 3))
    amount_paise: Mapped[int] = mapped_column(BigInteger)


class Participant(Base):
    __tablename__ = "participants"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    bill_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bills.id", ondelete="CASCADE"))
    display_name: Mapped[str] = mapped_column(Text)
    name_key: Mapped[str] = mapped_column(Text)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Claim(Base):
    __tablename__ = "claims"

    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bill_items.id", ondelete="CASCADE"), primary_key=True)
    participant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("participants.id", ondelete="CASCADE"), primary_key=True)
    units: Mapped[int] = mapped_column(server_default="1")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
