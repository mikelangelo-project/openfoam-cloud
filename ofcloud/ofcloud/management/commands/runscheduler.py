import os
import traceback

from django.conf import settings
from django.core.management.base import BaseCommand

from ofcloud import scheduler_daemon


def run_scheduler():
    print "Running scheduler daemon with refresh interval %s seconds" % settings.SCHEDULER_REFRESH_INTERVAL_SECONDS
    scheduler_daemon.run(settings.SCHEDULER_REFRESH_INTERVAL_SECONDS)


class Command(BaseCommand):
    help = 'Starts the OpenFOAM cloud simulation scheduler daemon'

    def add_arguments(self, parser):
        pass

    def handle(self, *args, **options):
        try:
            os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ofcloud.settings")
            run_scheduler()
        except:
            print traceback.format_exc()
