import json
import logging
import os
import time
import urllib.parse
import urllib.request

from .models import BankTransaction

logger = logging.getLogger(__name__)

BATCH_SIZE = 10  # Airtable accepts at most 10 records per request


class AirtableClient:
    def __init__(self, token, base_id, table):
        self.token = token
        self.url = f'https://api.airtable.com/v0/{base_id}/{urllib.parse.quote(table)}'

    def create_records(self, records):
        """Creates records and returns their Airtable ids in the same order."""
        body = json.dumps({'records': [{'fields': fields} for fields in records], 'typecast': True})
        request = urllib.request.Request(
            self.url,
            data=body.encode(),
            method='POST',
            headers={'Authorization': f'Bearer {self.token}', 'Content-Type': 'application/json'},
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            return [record['id'] for record in json.load(response)['records']]


def get_client():
    token = os.environ.get('AIRTABLE_TOKEN')
    base_id = os.environ.get('AIRTABLE_BASE_ID')
    if not token or not base_id:
        return None
    return AirtableClient(token, base_id, os.environ.get('AIRTABLE_TABLE') or 'Needs Review')


def to_fields(txn):
    return {
        'Bank Reference': txn.bank_reference,
        'Organization': txn.organization.slug,
        'Date': txn.date.isoformat(),
        'Description': txn.description,
        'Amount': str(txn.amount),
        'Reason': txn.review_reason,
    }


def sync_needs_review(transactions, client):
    """Creates an Airtable record for each needs_review transaction. Never raises."""
    if client is None:
        return

    txns = [txn for txn in transactions if txn.status == BankTransaction.NEEDS_REVIEW]
    for start in range(0, len(txns), BATCH_SIZE):
        if start:
            time.sleep(0.2)  # stay under the 5 requests/second limit
        batch = txns[start:start + BATCH_SIZE]
        try:
            record_ids = client.create_records([to_fields(txn) for txn in batch])
            for txn, record_id in zip(batch, record_ids):
                txn.airtable_record_id = record_id
                txn.airtable_sync_status = BankTransaction.SYNCED
        except Exception:
            logger.exception('Airtable sync failed')
            for txn in batch:
                txn.airtable_sync_status = BankTransaction.SYNC_FAILED

    BankTransaction.objects.bulk_update(txns, ['airtable_record_id', 'airtable_sync_status'])
