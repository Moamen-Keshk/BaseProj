class Constants:

    OrderStatusCoding = {
            'Draft': 1,
            'Solicitor': 2,
            'FCDO': 3,
            'Embassy': 4,
            'Completed': 5,
            'Shipped': 6,
            1: 'Draft',
            2: 'Solicitor',
            3: 'FCDO',
            4: 'Embassy',
            5: 'Completed',
            6: 'Shipped'
        }

    PropertyStatusCoding = {
            'Open': 1,
            'Pre-Open': 2,
            'Hold': 3,
            'Closed': 4,
            'Maintain': 5,
            1: 'Open',
            2: 'Pre-Open',
            3: 'Hold',
            4: 'Closed',
            5: 'Maintain'
    }

    RoomStatusCoding = {
            'Open': 1,
            'Blocked': 2,
            'Maintain': 3,
            1: 'Open',
            2: 'Blocked',
            3: 'Maintain'
    }

    BookingStatusCoding = {
            'Confirmed': 1,
            'Completed': 2,
            'Cancelled': 3,
        'No show': 4,
            1: 'Confirmed',
            2: 'Completed',
            3: 'Cancelled',
        4: 'No show'
    }

    PaymentStatusCoding = {
            'Paid': 1,
            'Unpaid': 2,
            'Suspended': 3,
            1: 'Paid',
            2: 'Unpaid',
            3: 'Suspended'
    }
