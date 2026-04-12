class ValidationError(ValueError):
    pass

class ChannelIntegrationError(Exception):
    """
    Custom exception raised when a channel manager integration (e.g., Booking.com, Expedia)
    encounters an error during API communication, data parsing, or validation.
    """
    pass