from .booking_com.adapter import BookingComAdapter
from .expedia.adapter import ExpediaAdapter
from .dummy_adapter import DummyAdapter


ADAPTERS = {
    'booking_com': BookingComAdapter(),
    'expedia': ExpediaAdapter(),
    'dummy_ota': DummyAdapter()
}


def get_adapter(channel_code: str):
    adapter = ADAPTERS.get(channel_code)
    if not adapter:
        raise ValueError(f'Unsupported channel: {channel_code}')
    return adapter