import os
import traceback

from django.core.management.base import BaseCommand

from ofcloud import scheduler_daemon


def terminate_scheduler():
    scheduler_daemon.shutdown()


class Command(BaseCommand):
    help = 'Terminates OpenFOAM cloud simulation scheduler daemon'

    def add_arguments(self, parser):
        pass

    def handle(self, *args, **options):
        try:
            os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ofcloud.settings")
            terminate_scheduler()
        except:
            print traceback.format_exc()
