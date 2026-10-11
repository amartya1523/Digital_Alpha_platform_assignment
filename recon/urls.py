from django.urls import path

from . import views

urlpatterns = [
    path('organizations/', views.organization_list),
    path('line-items/', views.line_item_list),
    path('transactions/', views.transaction_list),
    path('transactions/import/', views.transaction_import),
    path('transactions/<int:pk>/ignore/', views.transaction_ignore),
    path('matches/<int:pk>/approve/', views.match_approve),
    path('matches/<int:pk>/reject/', views.match_reject),
]
