from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from invoices.models import UserProfile

class Command(BaseCommand):
    help = 'Create profiles for existing users who don\'t have one'

    def handle(self, *args, **options):
        users_without_profile = User.objects.filter(profile__isnull=True)
        count = users_without_profile.count()

        if count == 0:
            self.stdout.write(self.style.SUCCESS('All users already have profiles.'))
            return

        for user in users_without_profile:
            UserProfile.objects.create(user=user)
            self.stdout.write(f'Created profile for {user.username}')

        self.stdout.write(self.style.SUCCESS(f'Successfully created {count} profile(s).'))