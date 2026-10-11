from unittest import mock

from recon.models import BankTransaction

from .utils import ReconTestCase

ROWS = (
    '2026-04-09,UNKNOWN INCOMING WIRE,9999.99,credit,B1\n'
    '2026-04-07,WIRE INCOMING PATEL FAMILY TRUST,12500.00,credit,B2\n'
)


class FakeAirtable:
    def __init__(self, fail=False):
        self.fail = fail
        self.sent = []

    def create_records(self, records):
        if self.fail:
            raise ConnectionError('Airtable is down')
        self.sent += records
        return [f'rec{i}' for i in range(len(records))]


class AirtableSyncTests(ReconTestCase):
    def upload_with(self, client):
        with mock.patch('recon.importer.get_airtable_client', return_value=client):
            return self.upload(ROWS)

    def test_only_needs_review_transactions_are_sent(self):
        fake = FakeAirtable()
        self.upload_with(fake)

        self.assertEqual([r['Bank Reference'] for r in fake.sent], ['B1'])
        needs_review = BankTransaction.objects.get(bank_reference='B1')
        self.assertEqual(needs_review.airtable_sync_status, BankTransaction.SYNCED)
        self.assertEqual(needs_review.airtable_record_id, 'rec0')
        suggested = BankTransaction.objects.get(bank_reference='B2')
        self.assertEqual(suggested.airtable_sync_status, BankTransaction.NOT_SYNCED)

    def test_airtable_failure_does_not_break_import(self):
        # the failure should be logged, not raised
        with self.assertLogs('recon.airtable', level='ERROR'):
            res = self.upload_with(FakeAirtable(fail=True))

        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data['imported'], 2)
        txn = BankTransaction.objects.get(bank_reference='B1')
        self.assertEqual(txn.airtable_sync_status, BankTransaction.SYNC_FAILED)
        self.assertEqual(txn.status, BankTransaction.NEEDS_REVIEW)

    def test_nothing_is_sent_when_not_configured(self):
        self.upload_with(None)
        self.assertEqual(BankTransaction.objects.get(bank_reference='B1').airtable_sync_status, 'not_synced')
