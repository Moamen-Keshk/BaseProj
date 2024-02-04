class Constants:

    EmbassyCoding = {
            'Emirates': 1,
            'Saudi Arabia': 2,
            'Qatar': 3,
            'Egypt': 4,
            'Kuwait': 5,
            'Lebanon': 6,
            'FCDO Only': 7,
            'Sol+FCDO': 8,
            1: 'UAE',
            2: 'KSA',
            3: 'QAT',
            4: 'EGY',
            5: 'KWT',
            6: 'LBN',
            7: 'FCDO',
            8: 'S+FC'
        }

    DocTypeCoding = {
            'Educational': 1,
            'Transcript': 2,
            'Commercial': 3,
            1: 'Educational',
            2: 'Transcript',
            3: 'Commercial'
        }

    ServiceTypeCoding = {
            'Full': 1,
            'Sol+FCDO': 2,
            'FCDO Only': 3,
            'Emb Only': 4,
            1: 'FULL',
            2: 'S+FC',
            3: 'FCDO',
            4: 'EMB'
        }

    ServiceOptionCoding = {
            'Standard': 1,
            'Express': 2,
            'Urgent': 3,
            1: 'Standard',
            2: 'Express',
            3: 'Urgent'
        }

    CollectionTypeCoding = {
            'Customer Courier': 1,
            'Royal Mail': 2,
            'In Person': 3,
            1: 'Courier',
            2: 'R-Mail',
            3: 'In Person'
        }

    TariffCoding = {
            'Standard': ['std_w', 'std_f'],
            'Express': ['exp_w', 'exp_f'],
            'Urgent': ['urg_w', 'urg_f']
        }

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
