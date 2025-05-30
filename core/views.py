
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import login
from .forms import CustomUserCreationForm,  PaymentMethodForm, PaymentForm, GroupForm,ExpenseParticipantForm, ExpenseForm, CustomUserUpdateForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, CreateView, DetailView, UpdateView
from .models import Group, Expense, PaymentMethod, Payment, ExpenseParticipant, Notification
from django.urls import reverse_lazy
from django.views import View
from django.http import JsonResponse
from django.db import transaction
from django.db.models import Sum, Count, Q, Prefetch
from django.contrib.auth.decorators import login_required
from django.forms import inlineformset_factory,modelformset_factory
from django.core.exceptions import ObjectDoesNotExist
import uuid
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.timezone import now
import time
import threading
from decimal import Decimal
from datetime import timedelta
from django.db.models.functions import TruncMonth
import csv
from django.http import HttpResponse,HttpResponseForbidden
from django.db.models import Exists, OuterRef, Prefetch
from django.contrib import messages

def signup_view(request):#signup view for new users
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)  # Automatically log in the user
            return redirect('home')  
    else:
        form = CustomUserCreationForm()
    return render(request, 'registration/signup.html', {'form': form}) #GET request and page to be displayed

def landing_page(request):
    return render(request, 'core/landing.html')
def home_page(request):
    user = request.user
    
    # Active Groups Card
    active_groups = user.user_groups.all().order_by('-created_at')[:5]#latest 5 created groups for user
    group_count = user.user_groups.count()
    
    # Total Group Expenses
    total_group_expenses = Expense.objects.filter( #select all expenses 4 users group
        group__members=user
    ).aggregate(total=Sum('amount'))['total'] or 0
    
    # Settlement Progress
    settled_amount = ExpenseParticipant.objects.filter( #how much settled by user
        expense__group__members=user,
        settled=True
    ).aggregate(total=Sum('share'))['total'] or 0
    settlement_percentage = (settled_amount / total_group_expenses * 100) if total_group_expenses else 0
    
    # User Balance Calculation
    owed_to_user = ExpenseParticipant.objects.filter( #how much owed to user
        expense__paid_by=user,
        settled=False
    ).aggregate(total=Sum('share'))['total'] or 0
    
    user_owes = ExpenseParticipant.objects.filter( #how much user owes
        user=user,
        settled=False
    ).aggregate(total=Sum('share'))['total'] or 0
    
    net_balance = owed_to_user - user_owes
    
    # Recent Expenses
    recent_expenses = Expense.objects.filter( #select all expenses for user
        group__members=user
    ).order_by('-date')[:2]
    
    recent_payments = Payment.objects.filter(# latest 3 payments 
    Q(payer=user) | Q(expense__paid_by=user)
    ).order_by('-timestamp')[:3]

    #pending_payments = Payment.objects.filter( #payments with status pending
     #   Q(payer=user) | Q(expense__paid_by=user), #Q -> where clause
     #   status='PENDING'
    #)[:5]
    
    # Group Balances
    group_balances = []
    for group in user.user_groups.all():
        group_owed = ExpenseParticipant.objects.filter(
            expense__group=group,
            expense__paid_by=user,
            settled=False
        ).aggregate(total=Sum('share'))['total'] or 0
        
        group_owes = ExpenseParticipant.objects.filter(
            expense__group=group,
            user=user,
            settled=False
        ).aggregate(total=Sum('share'))['total'] or 0
        
        group_balances.append({
            'group': group,
            'owed': group_owed,
            'owes': group_owes,
            'net': group_owed - group_owes# net balance for each group
        })
    
    context = { #how is passed to the template
        'active_groups': active_groups,
        'group_count': group_count,
        'total_group_expenses': total_group_expenses,
        'settlement_percentage': settlement_percentage,
        'owed_to_user': owed_to_user,
        'user_owes': user_owes,
        'net_balance': net_balance,
        'recent_expenses': recent_expenses,
        'pending_payments': pending_payments,
        'recent_payments':recent_payments, 
        'group_balances': group_balances,
    }
    
    return render(request, 'core/home.html', context)

class GroupListView(LoginRequiredMixin, ListView):
    model = Group
    template_name = 'core/group_list.html'
    context_object_name = 'groups'
    
    def get_queryset(self):
     return self.request.user.user_groups.all()
    

class GroupCreateView(LoginRequiredMixin, CreateView):
    model = Group
    form_class = GroupForm
    template_name = 'core/group_form.html'
    success_url = reverse_lazy('core:groups')

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)
    
class GroupMemberListView(LoginRequiredMixin, DetailView):
    model = Group
    template_name = 'core/group_members.html'
    context_object_name = 'group'

    def dispatch(self, request, *args, **kwargs):
        obj = self.get_object()
        if request.user != obj.created_by and request.user not in obj.members.all():
            return self.handle_no_permission()
        return super().dispatch(request, *args, **kwargs)

class ExpenseListView(LoginRequiredMixin, ListView):
    model = Expense
    form_class = ExpenseForm
    template_name = 'core/expense_list.html'
    context_object_name = 'expenses'

    def get_queryset(self):
        return Expense.objects.filter(group__members=self.request.user).order_by('-date') # - for latest
    
class ExpenseCreateView(CreateView):
    model = Expense
    form_class = ExpenseForm
    success_url = reverse_lazy('core:expense_list')
    template_name = 'core/expense_form.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user  # Pass current user to the form
        return kwargs

    def get_formset(self, group, data=None):
        if not group:
            return None
        members = group.members.all()
        initial_data = [{'user': member, 'email': member.email} for member in members]

        ExpenseParticipantFormSet = modelformset_factory(
            ExpenseParticipant,
            form=ExpenseParticipantForm,
            extra=len(initial_data),
            can_delete=False
        )
        return ExpenseParticipantFormSet(
            data or None,
            queryset=ExpenseParticipant.objects.none(),
            form_kwargs={'group': group},
            initial=initial_data
        )

    def get(self, request, *args, **kwargs):
        self.object = None
        form = self.get_form()
        group = None
        if 'group' in request.GET:
            group = Group.objects.filter(id=request.GET['group']).first()
        elif form.initial.get('group'):
            group = form.initial['group']
        formset = self.get_formset(group) if group else None
        return self.render_to_response(self.get_context_data(form=form, formset=formset))

    def post(self, request, *args, **kwargs):
        self.object = None
        group_id = request.POST.get('group')

        # Handle "Create New Group" option
        if group_id == 'create_new':
            return redirect('core:group_create')  # Redirect to group creation page

        # Validate group existence
        group = Group.objects.filter(id=group_id).first()
        if not group:
            form = self.get_form()
            form.add_error('group', 'Please select a valid group.')
            # No valid group, no participants formset either
            return self.form_invalid(form)

        # Get form and formset now with valid group
        form = self.get_form()
        formset = self.get_formset(group, data=request.POST)

        if form.is_valid() and (formset is None or formset.is_valid()):
            expense = form.save(commit=False)
            expense.group = group
            expense.paid_by = request.user
            expense.save()

            participants = []
            total_share = 0
            if formset:
                for participant_form in formset:
                    participant = participant_form.save(commit=False)
                    participant.expense = expense
                    total_share += participant.share or 0
                    participant.save()
                    participants.append(participant.user)

                expense.participants.set(participants)

                if total_share != expense.amount:
                    form.add_error(None, "Total shares must equal the expense amount.")
                    expense.delete()  # Rollback
                    return self.form_invalid(form)

            return self.form_valid(form)




def load_participant_forms(request):
    group_id = request.GET.get('group')
    group = Group.objects.get(pk=group_id)
    members = group.members.all()

    initial_data = [{'user': member, 'email': member.email} for member in members]

    ExpenseParticipantFormSet = modelformset_factory(
        ExpenseParticipant,
        form=ExpenseParticipantForm,
        extra=len(initial_data),
        can_delete=False
    )
    formset = ExpenseParticipantFormSet(
        queryset=ExpenseParticipant.objects.none(),
        form_kwargs={'group': group},
        initial=initial_data
    )
    return render(request, 'core/participant_forms.html', {'formset': formset})

class ExpenseDetailView(DetailView):
    model = Expense
    template_name = 'core/expense_detail.html' 
    context_object_name = 'expense'

class PaymentMethodCreateView(LoginRequiredMixin, CreateView):
    model = PaymentMethod
    form_class = PaymentMethodForm
    template_name = 'core/payment_method_form.html'
    success_url = reverse_lazy('core:payment_method_list')

    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)


class PaymentMethodListView(LoginRequiredMixin, ListView):
    model = PaymentMethod
    template_name = 'core/payment_method_list.html'
    context_object_name = 'methods'

    def get_queryset(self):
        return PaymentMethod.objects.filter(user=self.request.user)


class PaymentCreateView(LoginRequiredMixin, CreateView):
    model = Payment
    form_class = PaymentForm
    template_name = 'core/payment_form.html'
    success_url = reverse_lazy('core:payment_list')

    def form_valid(self, form):
        form.instance.payer = self.request.user
        return super().form_valid(form)


class PaymentListView(LoginRequiredMixin, ListView):
    model = Payment
    template_name = 'core/payment_list.html'
    context_object_name = 'payments'

    def get_queryset(self):
        return Payment.objects.filter(payer=self.request.user).order_by('-timestamp')
    
#view that returns JSON with the members of a given group
@login_required
def group_members_api(request):
    group_id = request.GET.get('group_id')
    if not group_id:
        return JsonResponse({'error': 'Missing group_id'}, status=400)

    try:
        group = Group.objects.get(id=group_id)
    except Group.DoesNotExist:
        return JsonResponse({'error': 'Group not found'}, status=404)

    members = group.members.values('id', 'email')  
    return JsonResponse(list(members), safe=False)


@csrf_exempt
def make_payment(request):
    if request.method != 'POST':
        return redirect('core:expense_list')  # fallback page

    user = request.user
    expense_id = request.POST.get('expense_id')
    provider = request.POST.get('provider')  # 'MPESA', 'PAYPAL', 'STRIPE'

    if not expense_id or not provider:
        # Redirect to a failure page or back to expense list with message
        return redirect('core:expense_list')

    expense = get_object_or_404(Expense, id=expense_id)

    try:
        participant = ExpenseParticipant.objects.get(expense=expense, user=user)
    except ExpenseParticipant.DoesNotExist:
        return redirect('core:expense_list')  # or show an error page

    if participant.settled:
        return redirect('core:expense-detail', pk=expense.id)

    try:
        payment_method = PaymentMethod.objects.get(user=user, provider=provider)
    except PaymentMethod.DoesNotExist:
        return redirect('core:payment_method_create')  # or show an error page

    payment = Payment.objects.create(
        expense=expense,
        payer=user,
        amount=participant.share,
        payment_method=payment_method,
        status='PENDING',
        transaction_id='TXN-' + str(uuid.uuid4())[:10]
    )

    def simulate_payment_success():
        time.sleep(2)
        payment.status = 'COMPLETED'
        payment.save()
        participant.settled = True
        participant.save()

    if provider == 'MPESA':
        threading.Thread(target=simulate_payment_success).start()
    else:
        payment.status = 'COMPLETED'
        payment.save()
        participant.settled = True
        participant.save()

    # ✅ Redirect after success
    return redirect('core:expense-detail', pk=expense.id)

@login_required
def notifications_view(request):
    notifications = Notification.objects.filter(user=request.user).order_by('-created_at')
    context = {
        'notifications': notifications
    }
    return render(request, 'core/notifications.html', context)

def unpaid_expenses(request):
    user = request.user

    # Query expenses paid by this user
    expenses = Expense.objects.filter(paid_by=user).prefetch_related(
        Prefetch(
            'expenseparticipant_set',
            queryset=ExpenseParticipant.objects.filter(settled=False).select_related('user'),
            to_attr='unpaid_participants'  # Custom attribute on each Expense object
        )
    )

    # Filter to only those expenses that have unpaid participants
    expenses_with_unpaid = [expense for expense in expenses if expense.unpaid_participants]

    context = {
        'expenses_with_unpaid': expenses_with_unpaid,
    }
    return render(request, 'core/unpaid_expenses.html', context)


@login_required
def profile(request):
    user = request.user

    if request.method == 'POST':
        form = CustomUserUpdateForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            return redirect('core:profile')
    else:
        form = CustomUserUpdateForm(instance=user)

    return render(request, 'core/profile.html', {'form': form, 'user': user})

@login_required
def user_report(request):
    user = request.user
    
    # Summary stats
    total_expenses = Expense.objects.filter(paid_by=user).aggregate(total=Sum('amount'))['total'] or 0
    total_groups = user.user_groups.count()
    total_payments = Payment.objects.filter(payer=user).count()
    total_pending_payments = Payment.objects.filter(payer=user, status='PENDING').count()
    
    # Recent expenses with status
    recent_expenses = Expense.objects.filter(paid_by=user).order_by('-date')[:5]
    
    # Recent payments
    recent_payments = Payment.objects.filter(payer=user).order_by('-timestamp')[:5]

    # Groups user belongs to
    groups = user.user_groups.all()
    
    # Prepare data for Chart: sum of expenses by month for last 6 months
    
    six_months_ago = now() - timedelta(days=180)
    expenses_by_month = (
        Expense.objects
        .filter(paid_by=user, date__gte=six_months_ago)
        .annotate(month=TruncMonth('date'))
        .values('month')
        .annotate(total=Sum('amount'))
        .order_by('month')
    )

    # Format data for Chart.js
    chart_labels = [e['month'].strftime('%b %Y') for e in expenses_by_month]
    chart_data = [float(e['total']) for e in expenses_by_month]

    context = {
        'total_expenses': total_expenses,
        'total_groups': total_groups,
        'total_payments': total_payments,
        'total_pending_payments': total_pending_payments,
        'recent_expenses': recent_expenses,
        'recent_payments': recent_payments,
        'groups': groups,
        'chart_labels': chart_labels,
        'chart_data': chart_data,
    }
    
    return render(request, 'core/user_report.html', context)

@login_required
def download_report(request):
    user = request.user

    # Gather data for the report (similar to your user_report view)
    expenses = Expense.objects.filter(paid_by=user).order_by('-date')

    # Create the HttpResponse object with CSV headers.
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="report.csv"'

    writer = csv.writer(response)
    # Write headers
    writer.writerow(['Description', 'Amount', 'Category', 'Group', 'Date'])

    # Write data rows
    for expense in expenses:
        writer.writerow([
            expense.description,
            expense.amount,
            expense.category,
            expense.group.name,
            expense.date.strftime('%Y-%m-%d'),
        ])

    return response

#pending payments 
@login_required
def pending_payments(request):
    user = request.user
    
    
    
    # Get expenses where user is owed money (they paid and others haven't settled)
    expenses_owed = Expense.objects.filter(
        paid_by=user
    ).prefetch_related(
        Prefetch(
            'expenseparticipant_set',
            queryset=ExpenseParticipant.objects.filter(settled=False),
            to_attr='unpaid_particips'
        )
    ).annotate(
        has_unpaid=Exists(
            ExpenseParticipant.objects.filter(
                expense=OuterRef('pk'),
                settled=False
            )
        )
    ).filter(has_unpaid=True)
    
    # Get expenses where user owes money (they're an unpaid participant)
    expenses_owing = Expense.objects.filter(
        expenseparticipant__user=user,
        expenseparticipant__settled=False
    ).distinct().select_related('paid_by')
    
    # Calculate totals
    total_owed = sum(
        p.share for e in expenses_owed 
        for p in e.unpaid_particips
    ) if expenses_owed else 0
    
    total_owing = sum(
        ep.share for e in expenses_owing
        for ep in e.expenseparticipant_set.filter(user=user, settled=False)
    ) if expenses_owing else 0
    
    context = {
        'expenses_owed': expenses_owed,
        'expenses_owing': expenses_owing,
        'total_owed': total_owed,
        'total_owing': total_owing,
    }
    return render(request, 'core/pending_payments.html', context)

@login_required
def homepending(request):
    user = request.user

    # Fetch latest 1 pending payment for the card
    pending_payments = Payment.objects.filter(
        Q(payer=user) | Q(expense__paid_by=user),
        status='PENDING'
    ).order_by('-timestamp')[:1]

    # Add other context as needed...

    context = {
        'pending_payments': pending_payments,
        # other context
    }
    return render(request, 'core/home.html', context)

class GroupUpdateView(LoginRequiredMixin, UpdateView):
    model = Group
    form_class = GroupForm
    template_name = 'core/group_form.html'  # reuse your create group form template or create one
    success_url = reverse_lazy('core:groups')  # redirect after successful edit

    def get_queryset(self):
        # Optional: restrict editing to groups created by the user
        return Group.objects.filter(created_by=self.request.user)

    def form_valid(self, form):
        messages.success(self.request, "Group updated successfully.")
        return super().form_valid(form)
    
@login_required
def group_delete(request, pk):
    group = get_object_or_404(Group, pk=pk)

    # Optional: restrict delete to group creator only
    if group.created_by != request.user:
        return HttpResponseForbidden("You do not have permission to delete this group.")

    if request.method == 'POST':
        group.delete()
        messages.success(request, "Group deleted successfully.")
        return redirect('core:groups')

    # Optionally handle GET to show confirmation (if not handled in template)
    return redirect('core:groups')