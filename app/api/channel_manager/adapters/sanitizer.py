import re


class PayloadSanitizer:
    @staticmethod
    def mask_xml_credit_cards(xml_payload: str) -> str:
        """
        Detects standard OTA credit card nodes in XML and masks them,
        leaving only the last 4 digits visible.
        """
        if not xml_payload:
            return xml_payload

        # Mask Card Number (Booking.com & Expedia common formats)
        cc_pattern = r'(<(?:CardNumber|Number|credit_card_number|creditCardNumber)[^>]*>)(.*?)(</(?:CardNumber|Number|credit_card_number|creditCardNumber)>)'

        def mask_cc(match):
            open_tag = match.group(1)
            raw_cc = match.group(2).strip()
            close_tag = match.group(3)

            if len(raw_cc) > 4:
                masked = '*' * (len(raw_cc) - 4) + raw_cc[-4:]
            else:
                masked = '****'
            return f"{open_tag}{masked}{close_tag}"

        sanitized = re.sub(cc_pattern, mask_cc, xml_payload, flags=re.IGNORECASE)

        # Completely strip CVV/CVC codes (Never store these, even masked)
        cvv_pattern = r'(<(?:CVC|CVV|SeriesCode|cvc)[^>]*>)(.*?)(</(?:CVC|CVV|SeriesCode|cvc)>)'
        sanitized = re.sub(cvv_pattern, r'\g<1>***\g<3>', sanitized, flags=re.IGNORECASE)

        return sanitized

    @staticmethod
    def mask_json_credit_cards(json_payload: dict) -> dict:
        """
        Recursively searches a JSON dictionary and masks credit card fields.
        """
        # (Implementation depends on OTA JSON structure, but the concept is the same)
        pass