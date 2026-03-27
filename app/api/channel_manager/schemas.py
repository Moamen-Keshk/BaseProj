from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional


@dataclass
class ARIUpdate:
    property_id: int
    room_id: int
    rate_plan_id: Optional[int]
    stay_date: date
    availability: Optional[int] = None
    amount: Optional[Decimal] = None
    min_los: Optional[int] = None
    max_los: Optional[int] = None
    closed: Optional[bool] = None
    closed_to_arrival: Optional[bool] = None
    closed_to_departure: Optional[bool] = None


@dataclass
class ChannelReservationPayload:
    channel_code: str
    external_reservation_id: str
    external_version: Optional[str]
    property_id: int
    guest_name: Optional[str]
    guest_email: Optional[str]
    checkin_date: date
    checkout_date: date
    total_amount: Optional[Decimal]
    currency: Optional[str]
    external_room_id: Optional[str]
    external_rate_plan_id: Optional[str]
    status: str
    raw_payload: dict | str