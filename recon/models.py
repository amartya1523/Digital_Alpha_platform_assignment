from decimal import Decimal

from django.db import models


class Organization(models.Model):
    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=200)

    def __str__(self):
        return self.name


class InvestorEntity(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='investors')
    name = models.CharField(max_length=200)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['organization', 'name'], name='unique_investor_per_org'),
        ]

    def __str__(self):
        return self.name


class CapitalCall(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='capital_calls')
    number = models.PositiveIntegerField()
    call_date = models.DateField()
    due_date = models.DateField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['organization', 'number'], name='unique_call_number_per_org'),
        ]

    def __str__(self):
        return f'{self.organization.slug} call #{self.number}'


class LineItem(models.Model):
    OPEN = 'open'
    PARTIALLY_FUNDED = 'partially_funded'
    FUNDED = 'funded'
    STATUS_CHOICES = [
        (OPEN, 'Open'),
        (PARTIALLY_FUNDED, 'Partially funded'),
        (FUNDED, 'Funded'),
    ]

    capital_call = models.ForeignKey(CapitalCall, on_delete=models.CASCADE, related_name='line_items')
    investor = models.ForeignKey(InvestorEntity, on_delete=models.PROTECT, related_name='line_items')
    expected_reference = models.CharField(max_length=50)
    amount_called = models.DecimalField(max_digits=14, decimal_places=2)
    amount_funded = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=OPEN)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount_funded__lte=models.F('amount_called')),
                name='funded_not_more_than_called',
            ),
        ]

    @property
    def amount_remaining(self):
        return self.amount_called - self.amount_funded

    def add_funding(self, amount):
        self.amount_funded += amount
        if self.amount_funded == self.amount_called:
            self.status = self.FUNDED
        else:
            self.status = self.PARTIALLY_FUNDED

    def __str__(self):
        return f'{self.expected_reference} {self.investor.name}'


class BankTransaction(models.Model):
    SUGGESTED = 'suggested'
    NEEDS_REVIEW = 'needs_review'
    RECONCILED = 'reconciled'
    IGNORED = 'ignored'
    STATUS_CHOICES = [
        (SUGGESTED, 'Suggested'),
        (NEEDS_REVIEW, 'Needs review'),
        (RECONCILED, 'Reconciled'),
        (IGNORED, 'Ignored'),
    ]

    NOT_SYNCED = 'not_synced'
    SYNCED = 'synced'
    SYNC_FAILED = 'sync_failed'
    SYNC_CHOICES = [
        (NOT_SYNCED, 'Not synced'),
        (SYNCED, 'Synced'),
        (SYNC_FAILED, 'Sync failed'),
    ]

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='transactions')
    date = models.DateField()
    description = models.TextField()
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    bank_reference = models.CharField(max_length=100)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    review_reason = models.TextField(blank=True)
    airtable_record_id = models.CharField(max_length=50, blank=True)
    airtable_sync_status = models.CharField(max_length=20, choices=SYNC_CHOICES, default=NOT_SYNCED)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-id']
        constraints = [
            models.UniqueConstraint(fields=['organization', 'bank_reference'], name='unique_bank_ref_per_org'),
        ]

    def __str__(self):
        return f'{self.bank_reference} {self.amount}'


class Match(models.Model):
    PROPOSED = 'proposed'
    APPROVED = 'approved'
    REJECTED = 'rejected'
    STATUS_CHOICES = [
        (PROPOSED, 'Proposed'),
        (APPROVED, 'Approved'),
        (REJECTED, 'Rejected'),
    ]

    transaction = models.ForeignKey(BankTransaction, on_delete=models.CASCADE, related_name='matches')
    line_item = models.ForeignKey(LineItem, on_delete=models.CASCADE, related_name='matches')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=PROPOSED)
    reason = models.TextField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['transaction', 'line_item'], name='unique_match_per_line_item'),
        ]
