# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('ofcloud', '0006_simulation_status'),
    ]

    operations = [
        migrations.AlterField(
            model_name='instance',
            name='status',
            field=models.CharField(default=b'PENDING', max_length=100),
        ),
    ]
