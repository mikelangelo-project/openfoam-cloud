# Copyright (C) 2015-2017 XLAB, Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


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
