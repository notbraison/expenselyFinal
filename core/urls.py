from django.urls import path
from . import views
from core.views import home_page, group_members_api,load_participant_forms, make_payment, notifications_view, unpaid_expenses, profile, pending_payments, ExpenseDetailView

app_name = 'core'

urlpatterns = [
    path('home/', home_page, name='home'),
    # Groups
    path('groups/', views.GroupListView.as_view(), name='groups'),#list of all groups
    path('groups/create/', views.GroupCreateView.as_view(), name='group_create'),
    path('groups/<int:pk>/members/', views.GroupMemberListView.as_view(), name='group_members'),
    
    path('groups/<int:pk>/edit/', views.GroupUpdateView.as_view(), name='group_edit'),
    path('groups/<int:pk>/delete/', views.group_delete, name='group_delete'),
    
    # Expenses
    path('expenses/', views.ExpenseListView.as_view(), name='expense_list'),
    path('expenses/create/', views.ExpenseCreateView.as_view(), name='expense_create'),
    path('expenses/load-participant-forms/', load_participant_forms, name='load_participant_forms'),
    path('expenses/<int:pk>/', views.ExpenseDetailView.as_view(), name='expense-detail'),
    
    
    # Payments
    path('payment-methods/', views.PaymentMethodListView.as_view(), name='payment_method_list'),
    path('payment-methods/create/', views.PaymentMethodCreateView.as_view(), name='payment_method_create'),
    path('payments/', views.PaymentListView.as_view(), name='payment_list'),
    path('payments/create/', views.PaymentCreateView.as_view(), name='payment_create'),
    path('make-payment/', make_payment, name='make_payment'),
    path('api/group-members/', group_members_api, name='group_members_api'),
    path('pending-payments/', pending_payments, name='pending_payments'),
    
    #notifications
    path('notifications/', notifications_view, name='notifications'),
    path('expenses/unpaid/', unpaid_expenses, name='unpaid_expenses'),
    
    #profile
    path('profile/', profile, name='profile'),
    
    #user report
     path('user-report/', views.user_report, name='user_report'),
     path('download-report/', views.download_report, name='download_report'),

]