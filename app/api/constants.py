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
            'Available': 1,
            'Booked': 2,
            'Blocked': 3,
            1: 'Available',
            2: 'Booked',
            3: 'Blocked'
    }

    BookingStatusCoding = {
            'Confirmed': 1,
            'Checked In': 2,
            'Checked Out': 3,
            'Completed': 4,
            'Cancelled': 5,
            'No show': 6,
            1: 'Confirmed',
            2: 'Checked In',
            3: 'Checked Out',
            4: 'Completed',
            5: 'Cancelled',
            6: 'No show'
    }

    PaymentStatusCoding = {
            'Paid': 1,
            'POA': 2,
            'Unpaid': 3,
            'Suspended': 4,
            1: 'Paid',
            2: 'POA',
            3: 'Unpaid',
            4: 'Suspended'
    }

    CategoryCoding = {
            'Single': 1,
            'Double': 2,
            'Twin': 3,
            'Triple': 4,
            1: 'Single',
            2: 'Double',
            3: 'Twin',
            4: 'Triple'
    }
