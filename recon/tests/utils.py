from io import StringIO
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from rest_framework.test import APITestCase

from recon.models import LineItem

HEADER = 'date,description,amount,type,reference\n'


def csv_file(rows, header=HEADER):
    return SimpleUploadedFile('statement.csv', (header + rows).encode(), content_type='text/csv')


class ReconTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_demo', stdout=StringIO())

    def setUp(self):
        # never talk to the real Airtable from tests
        patcher = mock.patch('recon.importer.get_airtable_client', return_value=None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def upload(self, rows, org='northwind', header=HEADER):
        return self.client.post(
            '/api/transactions/import/', {'file': csv_file(rows, header)}, HTTP_X_ORGANIZATION=org
        )

    def post(self, url, org='northwind'):
        return self.client.post(url, HTTP_X_ORGANIZATION=org)

    def line_item(self, reference):
        return LineItem.objects.get(expected_reference=reference)
