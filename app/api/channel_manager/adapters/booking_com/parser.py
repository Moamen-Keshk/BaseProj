import xml.etree.ElementTree as ET
from datetime import timezone

from app.api.channel_manager.schemas import ChannelReservationPayload, PaymentInfo
from datetime import datetime
from decimal import Decimal


class BookingComParser:
    @staticmethod
    def parse_reservation(xml_string: str, property_id: int) -> ChannelReservationPayload:
        root = ET.fromstring(xml_string)

        # ... (Your existing parsing logic for dates, guests, etc.) ...

        # 1. Extract Payment Details
        payment_info = None
        credit_card_node = root.find('.//CreditCard')

        if credit_card_node is not None:
            card_code = credit_card_node.findtext('CardCode', '')

            payment_info = PaymentInfo(
                card_type=card_code,
                card_number=credit_card_node.findtext('CardNumber', ''),
                card_holder=credit_card_node.findtext('CardHolder', ''),
                expiration_date=credit_card_node.findtext('ExpireDate', ''),  # Usually MM/YYYY
                cvc=credit_card_node.findtext('CVC', ''),
                # Booking.com VCCs usually come with a specific VirtualCard flag or brand
                is_vcc=True if card_code == 'MC' and root.find('.//IsVirtualCard') is not None else False
            )

        # 2. Build Payload
        return ChannelReservationPayload(
            channel_code='booking_com',
            external_reservation_id=root.findtext('.//id'),
            external_version='',
            property_id=property_id,
            guest_name='',
            guest_email='',
            checkin_date=datetime.now(timezone.utc),
            checkout_date=datetime.now(timezone.utc),
            total_amount=None,
            currency='',
            external_room_id='',
            external_rate_plan_id='',
            # ... (adjust fields) ...
            status='new',  # parsed from XML
            raw_payload=xml_string,  # Keep raw here for now, sanitize later
            payment_info=payment_info
        )

    @staticmethod
    def build_reservation_payload(
        property_id: int,
        external_reservation_id: str,
        checkin_date: str,
        checkout_date: str,
        guest_name: str | None = None,
        guest_email: str | None = None,
        total_amount: str | None = None,
        currency: str | None = None,
        external_room_id: str | None = None,
        external_rate_plan_id: str | None = None,
        status: str = 'new',
        external_version: str | None = None,
        raw_payload: dict | str | None = None,
    ) -> dict:
        return {
            'channel_code': 'booking_com',
            'external_reservation_id': external_reservation_id,
            'external_version': external_version,
            'property_id': property_id,
            'guest_name': guest_name,
            'guest_email': guest_email,
            'checkin_date': datetime.fromisoformat(checkin_date).date(),
            'checkout_date': datetime.fromisoformat(checkout_date).date(),
            'total_amount': Decimal(total_amount) if total_amount is not None else None,
            'currency': currency,
            'external_room_id': external_room_id,
            'external_rate_plan_id': external_rate_plan_id,
            'status': status,
            'raw_payload': raw_payload or {},
        }