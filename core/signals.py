from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.contenttypes.models import ContentType
from core.models import Expense,ExpenseParticipant,Notification,PaymentMethod, Payment
from datetime import timedelta
from dateutil.relativedelta import relativedelta  # pip install python-dateutil

@receiver(post_save, sender=Expense)
def create_initial_payment(sender, instance, created, **kwargs):
    if created:
        payment_method = PaymentMethod.objects.filter(user=instance.paid_by, provider='MPESA').first()
        if not payment_method:
            # Optional: you can log, raise error, or skip creating payment here
            return

        Payment.objects.create(
            expense=instance,
            payer=instance.paid_by,
            amount=instance.amount,
            payment_method=payment_method,  # Must be PaymentMethod instance
            status='PENDING',
        )


@receiver(post_save, sender=Expense)
def create_expense_notification(sender, instance, created, **kwargs):
    if created:
        # Get content type for Expense model
        content_type = ContentType.objects.get_for_model(instance)
        
        # Get all participants except the payer
        participants = instance.participants.exclude(id=instance.paid_by.id)
        
        message = (
            f"New expense '{instance.description}' of {instance.amount} {instance.currency} "
            f"added to {instance.group.name} by {instance.paid_by.email}"
        )
        
        for user in participants:
            Notification.objects.create(
                user=user,
                message=message,
                notification_type='EXPENSE_CREATED',
                related_object_id=instance.id,
                related_content_type=content_type
            )
        
        # Also notify group creator if they're not the payer or already a participant
        group_creator = instance.group.created_by
        if (group_creator != instance.paid_by and 
            group_creator not in participants):
            Notification.objects.create(
                user=group_creator,
                message=message,
                notification_type='EXPENSE_CREATED',
                related_object_id=instance.id,
                related_content_type=content_type
            )
            
@receiver(post_save, sender=ExpenseParticipant)
def notify_pending_payment(sender, instance, created, **kwargs):
    # Only notify if expense participant is not settled
    if not instance.settled:
        user = instance.user
        expense = instance.expense
        content_type = ContentType.objects.get_for_model(expense)
        
        message = (
            f"You have a pending payment of {instance.share} {expense.currency} "
            f"for '{expense.description}' in group '{expense.group.name}'."
        )
        
        # Check if a similar notification already exists to avoid duplicates
        exists = Notification.objects.filter(
            user=user,
            notification_type='PENDING_PAYMENT',
            related_object_id=expense.id,
            related_content_type=content_type,
            is_read=False,
        ).exists()
        
        if not exists:
            Notification.objects.create(
                user=user,
                message=message,
                notification_type='PENDING_PAYMENT',
                related_object_id=expense.id,
                related_content_type=content_type,
            )
            
@receiver(post_save, sender=Expense)
def create_recurring_expenses(sender, instance, created, **kwargs):
    if not created:
        return  # Only act on newly created expenses
    
    if instance.is_generated:
        return  # Skip generated expenses to avoid recursion
    
    if instance.type != 'RECURRING':
        return  # Only for recurring expenses
    
    # Get tracking period settings (with defaults for backward compatibility)
    tracking_duration = getattr(instance, 'tracking_duration', 3)  # Default 3 periods
    tracking_period = getattr(instance, 'tracking_period', 'MONTHLY')  # Default MONTHLY
    custom_period_days = getattr(instance, 'custom_period_days', None)
    
    freq_map = {
        'DAILY': timedelta(days=1),
        'WEEKLY': timedelta(weeks=1),
        'MONTHLY': relativedelta(months=1),
    }
    
    # Calculate how far ahead to track
    def get_tracking_limit():
        if tracking_period == 'DAILY':
            return timedelta(days=tracking_duration)
        elif tracking_period == 'WEEKLY':
            return timedelta(weeks=tracking_duration)
        elif tracking_period == 'MONTHLY':
            return relativedelta(months=tracking_duration)
        elif tracking_period == 'CUSTOM' and custom_period_days:
            # Custom period: tracking_duration * custom_period_days
            return timedelta(days=tracking_duration * custom_period_days)
        else:
            # Fallback to original behavior (3 instances)
            return None
    
    recurrence_delta = freq_map.get(instance.frequency)
    tracking_limit = get_tracking_limit()
    
    if not recurrence_delta:
        return  # Invalid frequency or none selected
    
    next_date = instance.date + recurrence_delta
    expenses_to_create = []
    
    if tracking_limit:
        # New behavior: create based on tracking period
        end_date = instance.date + tracking_limit
        
        while next_date <= end_date:
            expenses_to_create.append(Expense(
                group=instance.group,
                amount=instance.amount,
                currency=instance.currency,
                description=instance.description,
                category=instance.category,
                paid_by=instance.paid_by,
                date=next_date,
                type='RECURRING',
                frequency=instance.frequency,
                is_generated=True,  # This prevents infinite recursion
                # Copy tracking settings if they exist
                tracking_duration=tracking_duration if hasattr(instance, 'tracking_duration') else None,
                tracking_period=tracking_period if hasattr(instance, 'tracking_period') else None,
                custom_period_days=custom_period_days if hasattr(instance, 'custom_period_days') else None,
            ))
            next_date += recurrence_delta
    else:
        # Fallback to original behavior: create 3 future instances
        for _ in range(3):
            expenses_to_create.append(Expense(
                group=instance.group,
                amount=instance.amount,
                currency=instance.currency,
                description=instance.description,
                category=instance.category,
                paid_by=instance.paid_by,
                date=next_date,
                type='RECURRING',
                frequency=instance.frequency,
                is_generated=True,  # This prevents infinite recursion
            ))
            next_date += recurrence_delta
    
    # Bulk create for better performance
    if expenses_to_create:
        Expense.objects.bulk_create(expenses_to_create)