from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.contrib.contenttypes.fields import GenericForeignKey

class CustomUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError(_('The Email must be set'))
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(email, password, **extra_fields)

class CustomUser(AbstractUser):
    username = None  # Remove username field
    email = models.EmailField(_('email address'), unique=True)
    age = models.PositiveIntegerField(null=True, blank=True)
    national_id = models.CharField(max_length=50, blank=True)
    GENDER_CHOICES = (
        ('M', 'Male'),
        ('F', 'Female'),
        ('O', 'Other'),
    )
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES, blank=True)
    contact = models.CharField(max_length=20, blank=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    objects = CustomUserManager()

    def __str__(self):
        return self.email

class Group(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    members = models.ManyToManyField(
        CustomUser, 
        related_name='user_groups',  # Changed from default 'groups'
        blank=True
    )
    created_by = models.ForeignKey(
        CustomUser, 
        on_delete=models.CASCADE,
        related_name='created_groups'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class Expense(models.Model):
    CURRENCIES = (('USD', 'USD'), ('KES', 'KES'), ('EUR', 'EUR'))#select dropdowns
    CATEGORIES = (('FOOD', 'Food'), ('TRAVEL', 'Travel'), ('RENT', 'Rent'),('BUSINESS','Business'), ('OTHER', 'Other'))

    group = models.ForeignKey(Group, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, choices=CURRENCIES)
    description = models.TextField()
    category = models.CharField(max_length=20, choices=CATEGORIES)
    paid_by = models.ForeignKey( #whoever is logged in
        CustomUser,
        on_delete=models.CASCADE,
        related_name='expenses_paid'  
    )
    date = models.DateTimeField(auto_now_add=True)
    participants = models.ManyToManyField(  #many participants in a many diff expenses
        CustomUser, 
        through='ExpenseParticipant',  #expense created , expense participants table created 
        related_name='expenses_participated'  
    )

    def __str__(self):
        return f"{self.description} - {self.amount}"

class ExpenseParticipant(models.Model):
    expense = models.ForeignKey(Expense, on_delete=models.CASCADE)
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='expense_shares'  
    )
    share = models.DecimalField(max_digits=10, decimal_places=2)
    settled = models.BooleanField(default=False) #paid or not paid

    class Meta: # expense and user are both unique together
        unique_together = ('expense', 'user') 

class PaymentMethod(models.Model):
    PROVIDERS = (('STRIPE', 'Stripe'), ('PAYPAL', 'PayPal'), ('MPESA', 'M-Pesa'))
    
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='payment_methods'  
    )
    provider = models.CharField(max_length=20, choices=PROVIDERS)
    details = models.JSONField()  # Store provider-specific data , 
    is_default = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.user}'s {self.provider}"

class Payment(models.Model):
    STATUS_CHOICES = (('PENDING', 'Pending'), ('COMPLETED', 'Completed'), ('FAILED', 'Failed'))
    
    expense = models.ForeignKey(Expense, on_delete=models.CASCADE) #which expense is being paid
    payer = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.ForeignKey(PaymentMethod, on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    transaction_id = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return f"{self.payer} paid {self.amount}"
    
class Notification(models.Model):
    NOTIFICATION_TYPES = (
        ('EXPENSE_ADDED', 'New Expense Added'),
        ('PAYMENT_RECEIVED', 'Payment Received'),
        ('SETTLEMENT_REMINDER', 'Settlement Reminder'),
        ('GROUP_INVITE', 'Group Invitation'),
        ('PENDING_PAYMENT', 'Pending Payment'),
    )
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    message = models.TextField()
    notification_type = models.CharField(max_length=50, choices=NOTIFICATION_TYPES)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    # Optionally link to related objects (expense, payment, etc.)
    related_object_id = models.PositiveIntegerField(null=True, blank=True)
    related_content_type = models.ForeignKey(
        'contenttypes.ContentType',
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )
    content_object = GenericForeignKey('related_content_type', 'related_object_id')

    def mark_as_read(self):
        self.is_read = True
        self.save()
