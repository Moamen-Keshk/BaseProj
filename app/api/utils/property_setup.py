from datetime import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


DEFAULT_PROPERTY_TIMEZONE = 'UTC'
DEFAULT_PROPERTY_CURRENCY = 'USD'
DEFAULT_PROPERTY_TAX_RATE = 0.0
DEFAULT_CHECK_IN_TIME = '15:00'
DEFAULT_CHECK_OUT_TIME = '11:00'


def _normalize_time_string(value, *, field_name):
    if value in (None, ''):
        return None

    if isinstance(value, time):
        return value.strftime('%H:%M')

    try:
        parsed = time.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(f'{field_name} must use HH:MM format.') from exc

    return parsed.strftime('%H:%M')


def normalize_property_payload(payload, *, partial=False):
    if not isinstance(payload, dict):
        raise ValueError('Invalid property payload.')

    normalized = {}

    if 'name' in payload:
        name = str(payload.get('name') or '').strip()
        if not name:
            raise ValueError('Property name is required.')
        normalized['name'] = name
    elif not partial:
        raise ValueError('Property name is required.')

    if 'address' in payload:
        address = str(payload.get('address') or '').strip()
        if not address:
            raise ValueError('Property address is required.')
        normalized['address'] = address
    elif not partial:
        raise ValueError('Property address is required.')

    if 'phone_number' in payload or not partial:
        normalized['phone_number'] = str(payload.get('phone_number') or '').strip()

    if 'email' in payload or not partial:
        normalized['email'] = str(payload.get('email') or '').strip().lower()

    if 'timezone' in payload or not partial:
        timezone_value = str(payload.get('timezone') or DEFAULT_PROPERTY_TIMEZONE).strip()
        try:
            ZoneInfo(timezone_value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError('Timezone must be a valid IANA timezone, for example Europe/London.') from exc
        normalized['timezone'] = timezone_value

    if 'currency' in payload or not partial:
        currency = str(payload.get('currency') or DEFAULT_PROPERTY_CURRENCY).strip().upper()
        if len(currency) != 3 or not currency.isalpha():
            raise ValueError('Currency must be a 3-letter ISO code.')
        normalized['currency'] = currency

    if 'tax_rate' in payload or not partial:
        raw_tax_rate = payload.get('tax_rate', DEFAULT_PROPERTY_TAX_RATE)
        try:
            tax_rate = float(raw_tax_rate or 0.0)
        except (TypeError, ValueError) as exc:
            raise ValueError('Tax rate must be a number.') from exc
        if tax_rate < 0 or tax_rate > 100:
            raise ValueError('Tax rate must be between 0 and 100.')
        normalized['tax_rate'] = round(tax_rate, 2)

    if 'default_check_in_time' in payload or not partial:
        normalized['default_check_in_time'] = _normalize_time_string(
            payload.get('default_check_in_time', DEFAULT_CHECK_IN_TIME),
            field_name='Default check-in time',
        ) or DEFAULT_CHECK_IN_TIME

    if 'default_check_out_time' in payload or not partial:
        normalized['default_check_out_time'] = _normalize_time_string(
            payload.get('default_check_out_time', DEFAULT_CHECK_OUT_TIME),
            field_name='Default check-out time',
        ) or DEFAULT_CHECK_OUT_TIME

    if 'status_id' in payload:
        try:
            status_id = int(payload['status_id'])
        except (TypeError, ValueError) as exc:
            raise ValueError('Status is invalid.') from exc
        normalized['status_id'] = status_id

    if 'floors' in payload:
        floors = payload.get('floors') or []
        if not isinstance(floors, list):
            raise ValueError('Floors must be a list of floor numbers.')
        normalized_floors = []
        seen = set()
        for floor in floors:
            try:
                floor_number = int(floor)
            except (TypeError, ValueError) as exc:
                raise ValueError('Floor numbers must be integers.') from exc
            if floor_number <= 0:
                raise ValueError('Floor numbers must be greater than zero.')
            if floor_number in seen:
                raise ValueError('Floor numbers must be unique.')
            seen.add(floor_number)
            normalized_floors.append(floor_number)
        normalized['floors'] = normalized_floors

    if 'amenity_ids' in payload:
        amenity_ids = payload.get('amenity_ids') or []
        if not isinstance(amenity_ids, list):
            raise ValueError('Amenity IDs must be a list.')
        normalized_amenity_ids = []
        seen = set()
        for amenity_id in amenity_ids:
            try:
                amenity_int = int(amenity_id)
            except (TypeError, ValueError) as exc:
                raise ValueError('Amenity IDs must be integers.') from exc
            if amenity_int in seen:
                continue
            seen.add(amenity_int)
            normalized_amenity_ids.append(amenity_int)
        normalized['amenity_ids'] = normalized_amenity_ids

    return normalized
