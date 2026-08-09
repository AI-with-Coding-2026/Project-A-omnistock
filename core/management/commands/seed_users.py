from django.core.management.base import BaseCommand
from core.models import User


class Command(BaseCommand):
    help = 'Seed the database with sample user accounts'

    def handle(self, *args, **options):
        users = [
            {'username': 'admin', 'email': 'admin@example.com', 'role': User.ROLE_ADMIN},
            {'username': 'inventory_mgr', 'email': 'inventory@example.com', 'role': User.ROLE_INVENTORY_MANAGER},
            {'username': 'sales_rep', 'email': 'sales@example.com', 'role': User.ROLE_SALES_REP},
        ]

        for data in users:
            user, created = User.objects.get_or_create(
                username=data['username'],
                defaults={'email': data['email'], 'role': data['role']},
            )
            if created:
                user.set_password('password123')  # dev-only default
                user.save()
                self.stdout.write(f"Created: {user.username} ({user.role})")
            else:
                self.stdout.write(f"Already exists: {user.username}")

        self.stdout.write(self.style.SUCCESS('Seeded users'))