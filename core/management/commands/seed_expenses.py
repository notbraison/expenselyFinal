import random
from datetime import datetime, timedelta
from django.core.management.base import BaseCommand
from django.utils.timezone import make_aware
from core.models import CustomUser, Group, Expense, ExpenseParticipant

class Command(BaseCommand):
    help = 'Seed expenses for one specific user'

    def add_arguments(self, parser):
        parser.add_argument('user_email', type=str, help='Email of the user to seed data for')

    def handle(self, *args, **options):
        user_email = options['user_email']
        try:
            user = CustomUser.objects.get(email=user_email)
        except CustomUser.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'User with email {user_email} does not exist.'))
            return
        
        groups = list(user.user_groups.all())
        if not groups:
            self.stdout.write(self.style.ERROR('User is not a member of any groups.'))
            return
        
        categories = [c[0] for c in Expense.CATEGORIES]
        currencies = [c[0] for c in Expense.CURRENCIES]

        now = datetime.now()
        total_expenses_created = 0

        for _ in range(20):  # Create 20 expenses for this user
            group = random.choice(groups)
            paid_by = user
            amount = round(random.uniform(100, 10000), 2)
            currency = random.choice(currencies)
            category = random.choice(categories)
            description = f"expense {_+1} for {user.email}"

            # Random date in last 6 months
            random_days = random.randint(0, 180)
            expense_date = make_aware(now - timedelta(days=random_days))

            expense = Expense.objects.create(
                group=group,
                amount=amount,
                currency=currency,
                description=description,
                category=category,
                paid_by=paid_by,
                date=expense_date,
                type='ONE_TIME',
            )

            participants = list(group.members.all())
            shares = self.random_shares(len(participants), amount)

            for participant, share in zip(participants, shares):
                ExpenseParticipant.objects.create(
                    expense=expense,
                    user=participant,
                    share=share,
                    settled=random.choice([True, False]),
                )

            total_expenses_created += 1
        
        self.stdout.write(self.style.SUCCESS(f'Successfully created {total_expenses_created} expenses for user {user_email}.'))

    def random_shares(self, n, total_amount):
        weights = [random.random() for _ in range(n)]
        total_weight = sum(weights)
        shares = [round(total_amount * (w / total_weight), 2) for w in weights]
        shares[-1] = round(total_amount - sum(shares[:-1]), 2)
        return shares
