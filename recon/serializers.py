from rest_framework import serializers

from .models import BankTransaction, LineItem, Match, Organization


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ['slug', 'name']


class LineItemSerializer(serializers.ModelSerializer):
    investor = serializers.CharField(source='investor.name')
    capital_call = serializers.IntegerField(source='capital_call.number')
    call_date = serializers.DateField(source='capital_call.call_date')
    due_date = serializers.DateField(source='capital_call.due_date')
    amount_remaining = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = LineItem
        fields = [
            'id', 'capital_call', 'call_date', 'due_date', 'investor', 'expected_reference',
            'amount_called', 'amount_funded', 'amount_remaining', 'status',
        ]


class MatchSerializer(serializers.ModelSerializer):
    investor = serializers.CharField(source='line_item.investor.name')
    expected_reference = serializers.CharField(source='line_item.expected_reference')

    class Meta:
        model = Match
        fields = ['id', 'line_item', 'investor', 'expected_reference', 'status', 'reason']


class TransactionSerializer(serializers.ModelSerializer):
    matches = MatchSerializer(many=True)

    class Meta:
        model = BankTransaction
        fields = ['id', 'date', 'description', 'amount', 'bank_reference', 'status', 'review_reason', 'matches']
