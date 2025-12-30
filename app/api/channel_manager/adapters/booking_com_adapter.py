import requests
from xml.etree import ElementTree as ETree
from datetime import datetime, timedelta, timezone


class BookingComAdapter:
    def __init__(self, hotel_id, username, password):
        self.hotel_id = hotel_id
        self.username = username
        self.password = password
        self.endpoint = "https://supply-xml.booking.com/hotels/xml/reservations"

    def fetch_bookings(self, since_date: datetime = None):
        """
        Fetch new or updated bookings from Booking.com
        :param since_date: datetime object for last fetch (UTC)
        :return: list of reservations
        """
        if not since_date:
            since_date = datetime.now(timezone.utc) - timedelta(days=1)

        payload = f"""<?xml version="1.0" encoding="UTF-8"?>
<request>
  <username>{self.username}</username>
  <password>{self.password}</password>
  <hotel_id>{self.hotel_id}</hotel_id>
  <from_date>{since_date.strftime('%Y-%m-%d')}</from_date>
</request>"""

        response = requests.post(self.endpoint, data=payload)
        if response.status_code != 200:
            raise Exception(f"Failed to fetch reservations: {response.text}")

        return self.parse_reservations_xml(response.text)

    @staticmethod
    def parse_reservations_xml(xml_string):
        """
        Parses XML response from Booking.com into a list of dicts
        """
        root = ETree.fromstring(xml_string)
        reservations = []

        for res in root.findall("reservation"):
            guest_name = res.findtext("guest/name")
            checkin = res.findtext("checkin")
            checkout = res.findtext("checkout")
            total_price = float(res.findtext("total_price") or 0)
            currency = res.findtext("currency_code")
            room_id = res.findtext("room/id")
            booking_id = res.findtext("id")

            reservation_data = {
                "booking_id": booking_id,
                "guest_name": guest_name,
                "checkin": checkin,
                "checkout": checkout,
                "total_price": total_price,
                "currency": currency,
                "ota_room_id": room_id,
            }

            reservations.append(reservation_data)

        return reservations
