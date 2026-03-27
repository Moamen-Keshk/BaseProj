from xml.etree.ElementTree import Element, SubElement, tostring


class BookingComMapper:
    @staticmethod
    def build_ari_xml(connection, ari_updates: list[dict]) -> str:
        root = Element("ARIUpdate")
        hotel_id = str((connection.credentials_json or {}).get("hotel_id", ""))

        hotel_el = SubElement(root, "Hotel")
        hotel_el.set("id", hotel_id)

        for update in ari_updates:
            item_el = SubElement(hotel_el, "RoomRate")
            item_el.set("room_id", str(update["room_id"]))
            item_el.set("date", update["stay_date"])

            if update.get("rate_plan_id") is not None:
                item_el.set("rate_plan_id", str(update["rate_plan_id"]))

            if update.get("availability") is not None:
                item_el.set("availability", str(update["availability"]))

            if update.get("amount") is not None:
                item_el.set("amount", str(update["amount"]))

            if update.get("min_los") is not None:
                item_el.set("min_los", str(update["min_los"]))

            if update.get("max_los") is not None:
                item_el.set("max_los", str(update["max_los"]))

            if update.get("closed") is not None:
                item_el.set("closed", str(update["closed"]).lower())

            if update.get("closed_to_arrival") is not None:
                item_el.set("closed_to_arrival", str(update["closed_to_arrival"]).lower())

            if update.get("closed_to_departure") is not None:
                item_el.set("closed_to_departure", str(update["closed_to_departure"]).lower())

        return tostring(root, encoding="unicode")