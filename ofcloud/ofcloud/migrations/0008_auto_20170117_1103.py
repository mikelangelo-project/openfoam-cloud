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


# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import ofcloud.models


class Migration(migrations.Migration):

    dependencies = [
        ('ofcloud', '0007_auto_20170116_1507'),
    ]

    operations = [
        migrations.AlterField(
            model_name='instance',
            name='id',
            field=models.UUIDField(default=ofcloud.models.make_uuid_ac, serialize=False, editable=False, primary_key=True),
        ),
        migrations.AlterField(
            model_name='simulation',
            name='id',
            field=models.UUIDField(default=ofcloud.models.make_uuid_ac, serialize=False, editable=False, primary_key=True),
        ),
    ]
