from rest_framework.decorators import api_view
from rest_framework.exceptions import NotFound, ParseError
from rest_framework.response import Response

from . import actions
from .importer import import_statement
from .models import BankTransaction, LineItem, Organization
from .serializers import LineItemSerializer, OrganizationSerializer, TransactionSerializer


def get_organization(request):
    slug = request.headers.get('X-Organization', '').strip()
    if not slug:
        raise ParseError('X-Organization header is required.')
    org = Organization.objects.filter(slug=slug).first()
    if org is None:
        raise NotFound(f'Organization "{slug}" not found.')
    return org


def transaction_response(txn):
    txn = BankTransaction.objects.prefetch_related('matches__line_item__investor').get(pk=txn.pk)
    return Response(TransactionSerializer(txn).data)


@api_view(['GET'])
def organization_list(request):
    return Response(OrganizationSerializer(Organization.objects.order_by('name'), many=True).data)


@api_view(['GET'])
def line_item_list(request):
    org = get_organization(request)
    items = (
        LineItem.objects.filter(capital_call__organization=org)
        .select_related('capital_call', 'investor')
        .order_by('capital_call__number', 'expected_reference')
    )
    return Response(LineItemSerializer(items, many=True).data)


@api_view(['GET'])
def transaction_list(request):
    org = get_organization(request)
    txns = BankTransaction.objects.filter(organization=org).prefetch_related('matches__line_item__investor')
    return Response(TransactionSerializer(txns, many=True).data)


@api_view(['POST'])
def transaction_import(request):
    org = get_organization(request)
    upload = request.FILES.get('file')
    if upload is None:
        raise ParseError('Upload a CSV file in the "file" field.')
    return Response(import_statement(org, upload), status=201)


@api_view(['POST'])
def transaction_ignore(request, pk):
    return transaction_response(actions.ignore_transaction(get_organization(request), pk))


@api_view(['POST'])
def match_approve(request, pk):
    return transaction_response(actions.approve_match(get_organization(request), pk))


@api_view(['POST'])
def match_reject(request, pk):
    return transaction_response(actions.reject_match(get_organization(request), pk))
