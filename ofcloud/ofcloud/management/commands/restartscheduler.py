import os
import traceback

from django.conf import settings
from django.core.management import BaseCommand

from ofcloud import scheduler_daemon


def restart_scheduler():
    scheduler_daemon.restart(settings.SCHEDULER_REFRESH_INTERVAL_SECONDS)


class Command(BaseCommand):
    help = 'Restarts the OpenFOAM cloud simulation scheduler daemon'

    def add_arguments(self, parser):
        pass

    def handle(self, *args, **options):
        try:
            os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ofcloud.settings")
            restart_scheduler()
        except:
            print traceback.format_exc()