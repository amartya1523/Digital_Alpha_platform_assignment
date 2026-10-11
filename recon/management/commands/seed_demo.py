from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from recon.models import CapitalCall, InvestorEntity, LineItem, Organization

DEMO_DATA = [
    {
        'slug': 'northwind',
        'name': 'Northwind Ventures',
        'calls': [
            {
                'number': 1,
                'call_date': date(2026, 3, 25),
                'due_date': date(2026, 4, 10),
                'line_items': [
                    ('Haller Capital LLC', 'CC-1001', '27500.00'),
                    ('Rahul Shah Trust', 'CC-1002', '25000.00'),
                    ('Patel Family Trust', 'CC-1003', '12500.00'),
                    ('Meridian Partners LP', 'CC-1004', '15000.00'),
                    ('Oakridge Holdings LLC', 'CC-1005', '15000.00'),
                ],
            },
            {
                'number': 2,
                'call_date': date(2026, 4, 1),
                'due_date': date(2026, 4, 20),
                'line_items': [
                    ('Oakridge Holdings LLC', 'CC-1006', '15000.00'),
                ],
            },
        ],
    },
    {
        'slug': 'bluebird',
        'name': 'Bluebird Capital',
        'calls': [
            {
                'number': 1,
                'call_date': date(2026, 4, 1),
                'due_date': date(2026, 4, 15),
                'line_items': [
                    ('Cedar Grove Fund LP', 'CC-2001', '40000.00'),
                ],
            },
        ],
    },
]


class Command(BaseCommand):
    help = 'Creates the demo organizations, capital calls and line items. Safe to run more than once.'

    @transaction.atomic
    def handle(self, *args, **options):
        for org_data in DEMO_DATA:
            org, _ = Organization.objects.get_or_create(slug=org_data['slug'], defaults={'name': org_data['name']})

            for call_data in org_data['calls']:
                call, _ = CapitalCall.objects.get_or_create(
                    organization=org,
                    number=call_data['number'],
                    defaults={'call_date': call_data['call_date'], 'due_date': call_data['due_date']},
                )
                for investor_name, reference, amount in call_data['line_items']:
                    investor, _ = InvestorEntity.objects.get_or_create(organization=org, name=investor_name)
                    LineItem.objects.get_or_create(
                        capital_call=call,
                        expected_reference=reference,
                        defaults={'investor': investor, 'amount_called': Decimal(amount)},
                    )

        self.stdout.write(self.style.SUCCESS('Demo data is ready.'))
