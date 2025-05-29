from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.contenttypes.models import ContentType
from core.models import Expense,ExpenseParticipant,Notification


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