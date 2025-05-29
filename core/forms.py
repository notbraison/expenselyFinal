from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.forms import ModelForm, inlineformset_factory,  BaseInlineFormSet

from .models import CustomUser, Expense, PaymentMethod, Payment, Group, ExpenseParticipant

class CustomUserCreationForm(UserCreationForm):
    class Meta:
        model = CustomUser
        fields = ('email', 'first_name', 'last_name','gender','national_id','contact')
        widgets = {
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Enter your email'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'First Name'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Last Name'}),
            'national_id': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'National ID'}),
            'contact': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Phone Number'}),
            'gender': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['password1'].widget.attrs.update({'class': 'form-control border-end-0', 'placeholder': '8+ character required'})
        self.fields['password2'].widget.attrs.update({'class': 'form-control border-end-0', 'placeholder': 'Re-enter Password'})

class CustomUserUpdateForm(forms.ModelForm):
    class Meta:
        model = CustomUser
        fields = ['email', 'first_name', 'last_name', 'gender', 'national_id', 'contact', 'age']
        widgets = {
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'gender': forms.Select(attrs={'class': 'form-control'}),
            'national_id': forms.TextInput(attrs={'class': 'form-control'}),
            'contact': forms.TextInput(attrs={'class': 'form-control'}),
            'age': forms.NumberInput(attrs={'class': 'form-control'}),
        }



class CustomAuthenticationForm(AuthenticationForm):
    username = forms.EmailField(label='Email')

class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = ['group', 'amount', 'currency', 'description', 'category','type','frequency']
        widgets = {
            'type': forms.Select(attrs={'class': 'form-control', 'id': 'id_type'}),
            'frequency': forms.Select(attrs={'class': 'form-control', 'id': 'id_frequency'}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user:
            # Get groups where user is a member
            self.fields['group'].queryset = user.user_groups.all()
class BaseExpenseParticipantFormSet(BaseInlineFormSet):
    def __init__(self, *args, **kwargs):
        self.group = kwargs.pop('group', None)
        super().__init__(*args, **kwargs)

    def _construct_form(self, i, **kwargs):
        kwargs['group'] = self.group
        return super()._construct_form(i, **kwargs)

class ExpenseParticipantForm(forms.ModelForm):
    email = forms.CharField(required=False, widget=forms.TextInput(attrs={'readonly': True}))

    class Meta:
        model = ExpenseParticipant
        fields = ['user', 'share', 'email']

    def __init__(self, *args, **kwargs):
        self.group = kwargs.pop('group', None)
        super().__init__(*args, **kwargs)
        
        if self.group:
            self.fields['user'].queryset = self.group.members.all()
            self.fields['user'].widget = forms.HiddenInput()

        if self.instance and hasattr(self.instance, 'user') and self.instance.user:
            self.fields['email'].initial = self.instance.user.email

ExpenseParticipantFormSet = inlineformset_factory(
    Expense,
    ExpenseParticipant,
    form=ExpenseParticipantForm,
    formset=BaseExpenseParticipantFormSet,
    fields=['user', 'share', 'email'],
    extra=1,
    can_delete=False
)

ExpenseParticipantFormSet = inlineformset_factory(
    Expense,
    ExpenseParticipant,
    form=ExpenseParticipantForm,
    formset=BaseExpenseParticipantFormSet, 
    fields=['user', 'email', 'share'],
    extra=1,
    can_delete=False
)


class PaymentMethodForm(forms.ModelForm):
    # This will be a plain CharField to take user input as text
    details_text = forms.CharField(
        label='Details',
        widget=forms.Textarea(attrs={'rows': 3, 'placeholder': 'Enter details here'}),
        help_text='Phone number for M-Pesa, Email for PayPal, Account ID for Stripe'
    )

    class Meta:
        model = PaymentMethod
        fields = ['provider', 'details_text', 'is_default']

    def __init__(self, *args, **kwargs):
        # On edit, populate details_text from JSON field
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.details:
            if self.instance.provider == 'MPESA':
                self.initial['details_text'] = self.instance.details.get('phone', '')
            elif self.instance.provider == 'PAYPAL':
                self.initial['details_text'] = self.instance.details.get('email', '')
            elif self.instance.provider == 'STRIPE':
                self.initial['details_text'] = self.instance.details.get('account_id', '')

    def clean(self):
        cleaned_data = super().clean()
        provider = cleaned_data.get('provider')
        details_text = cleaned_data.get('details_text')

        if provider == 'MPESA':
            # Simple validation for phone number (can be improved)
            if not details_text or not details_text.isdigit():
                self.add_error('details_text', 'Enter a valid phone number for M-Pesa.')
            else:
                cleaned_data['details'] = {'phone': details_text}

        elif provider == 'PAYPAL':
            # Simple email validation (you can use EmailField validator)
            if not details_text or '@' not in details_text:
                self.add_error('details_text', 'Enter a valid email address for PayPal.')
            else:
                cleaned_data['details'] = {'email': details_text}

        elif provider == 'STRIPE':
            # Assume account_id or other identifier
            if not details_text:
                self.add_error('details_text', 'Enter the Stripe account ID.')
            else:
                cleaned_data['details'] = {'account_id': details_text}

        return cleaned_data

    def save(self, commit=True):
        # Remove details_text before saving to model (details is JSONField)
        self.instance.details = self.cleaned_data.get('details', {})
        return super().save(commit=commit)


class PaymentForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = ['expense', 'payment_method', 'amount']

class GroupForm(forms.ModelForm):
    class Meta:
        model = Group
        fields = ['name', 'description', 'members']
        widgets = {
            'members': forms.SelectMultiple(attrs={'class': 'form-control'}),
        }