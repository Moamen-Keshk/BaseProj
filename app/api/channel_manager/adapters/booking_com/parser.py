import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from decimal import Decimal

from app.api.channel_manager.schemas import ChannelReservationPayload, PaymentInfo
from app.api.exceptions import ChannelIntegrationError

logger = logging.getLogger(__name__)


class BookingComParser:

    # --- New Methods for Rooms & Rates Configuration ---

    @staticmethod
    def _check_for_faults(root: ET.Element):
        """Helper to catch Booking.com <Fault> or <Error> payloads."""
        fault = root.find('.//Fault') or root.find('.//error')
        if fault is not None:
            fault_string = fault.findtext('faultstring') or fault.get('description') or "Unknown API Error"
            raise ChannelIntegrationError(f"Booking.com API returned an error: {fault_string}")

    @staticmethod
    def parse_rooms_response(xml_content: str) -> list[dict]:
        """
        Parses the XML response to extract room external IDs and names.
        Expected generic return format: [{'external_id': '123', 'external_name': 'Double Room'}, ...]
        """
        try:
            root = ET.fromstring(xml_content)
            BookingComParser._check_for_faults(root)

            external_rooms = []
            # Note: Adjust the XPath './/room' to match the exact Booking.com XML response node names
            for room_node in root.findall('.//room'):
                room_id = room_node.get('id') or room_node.findtext('room_id')
                room_name = room_node.get('name') or room_node.findtext('room_name') or f"Room {room_id}"

                if room_id:
                    external_rooms.append({
                        'external_id': str(room_id).strip(),
                        'external_name': str(room_name).strip()
                    })

            return external_rooms

        except ET.ParseError as e:
            logger.error(f"[Booking.com] Failed to parse Rooms XML: {str(e)}\nPayload: {xml_content}")
            raise ChannelIntegrationError("Invalid XML response received from Booking.com when fetching rooms.") from e

    @staticmethod
    def parse_rate_plans_response(xml_content: str) -> list[dict]:
        """
        Parses the XML response to extract rate plan external IDs and names.
        Expected generic return format: [{'external_id': '1', 'external_name': 'Standard Rate'}, ...]
        """
        try:
            root = ET.fromstring(xml_content)
            BookingComParser._check_for_faults(root)

            external_rate_plans = []
            # Note: Adjust the XPath './/rateplan' to match the exact Booking.com XML response node names
            for rp_node in root.findall('.//rateplan'):
                rp_id = rp_node.get('id') or rp_node.findtext('rateplan_id')
                rp_name = rp_node.get('name') or rp_node.findtext('rateplan_name') or f"RatePlan {rp_id}"

                if rp_id:
                    external_rate_plans.append({
                        'external_id': str(rp_id).strip(),
                        'external_name': str(rp_name).strip()
                    })

            return external_rate_plans

        except ET.ParseError as e:
            logger.error(f"[Booking.com] Failed to parse Rate Plans XML: {str(e)}\nPayload: {xml_content}")
            raise ChannelIntegrationError(
                "Invalid XML response received from Booking.com when fetching rate plans.") from e

    # --- Existing Methods for Reservations ---

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