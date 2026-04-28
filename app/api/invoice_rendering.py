from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from flask import render_template


_CURRENCY_SYMBOLS = {
    'AUD': 'A$',
    'CAD': 'C$',
    'EUR': 'EUR ',
    'GBP': '£',
    'USD': '$',
}


def _currency_symbol(currency_code: str | None) -> str:
    normalized = (currency_code or 'USD').upper()
    return _CURRENCY_SYMBOLS.get(normalized, f'{normalized} ')


def format_money(amount: Any, currency_code: str | None = None) -> str:
    return f"{_currency_symbol(currency_code)}{float(amount or 0.0):,.2f}"


def build_invoice_template_context(
    booking,
    invoice,
    *,
    property_obj=None,
    custom_message: str | None = None,
):
    property_obj = (
        property_obj
        or getattr(invoice, 'property', None)
        or getattr(booking, 'property_ref', None)
        or SimpleNamespace(
            name='Your Property',
            address='',
            phone_number='',
            email='',
            currency=(getattr(invoice, 'currency', None) or 'USD'),
            default_check_in_time='15:00',
            default_check_out_time='11:00',
        )
    )

    currency_code = (
        getattr(invoice, 'currency', None)
        or getattr(property_obj, 'currency', None)
        or 'USD'
    ).upper()

    guest_name = ' '.join(
        part for part in [getattr(booking, 'first_name', None), getattr(booking, 'last_name', None)] if part
    ).strip() or 'Guest'

    stay_nights = getattr(booking, 'number_of_days', None)
    if not stay_nights and getattr(booking, 'check_in', None) and getattr(booking, 'check_out', None):
        stay_nights = max((booking.check_out - booking.check_in).days, 0)

    return {
        'booking': booking,
        'invoice': invoice,
        'property': property_obj,
        'guest_name': guest_name,
        'currency_code': currency_code,
        'currency_symbol': _currency_symbol(currency_code),
        'format_money': lambda amount: format_money(amount, currency_code),
        'custom_message': custom_message.strip() if custom_message else None,
        'stay_nights': stay_nights or 0,
    }


def render_printable_invoice_html(
    booking,
    invoice,
    *,
    property_obj=None,
    custom_message: str | None = None,
) -> str:
    return render_template(
        'invoices/print.html',
        **build_invoice_template_context(
            booking,
            invoice,
            property_obj=property_obj,
            custom_message=custom_message,
        ),
    )
