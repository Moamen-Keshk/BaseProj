from app.api.channel_manager.adapters.booking_com.adapter import BookingComAdapter
from app.api.channel_manager.adapters.expedia.adapter import ExpediaAdapter


ADAPTERS = {
    'booking_com': BookingComAdapter(),
    'expedia': ExpediaAdapter(),
}


def get_adapter(channel_code: str):
    adapter = ADAPTERS.get(channel_code)
    if not adapter:
        raise ValueError(f'Unsupported channel: {channel_code}')
    return adapter