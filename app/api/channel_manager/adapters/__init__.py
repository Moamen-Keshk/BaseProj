from .booking_com.adapter import BookingComAdapter
from .expedia.adapter import ExpediaAdapter


ADAPTERS = {
    "booking_com": BookingComAdapter(),
    "expedia": ExpediaAdapter(),
}


def get_adapter(channel_code: str):
    if channel_code not in ADAPTERS:
        raise ValueError(f"Unsupported channel: {channel_code}")
    return ADAPTERS[channel_code]