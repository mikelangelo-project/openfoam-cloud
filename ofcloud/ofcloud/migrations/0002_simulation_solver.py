# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ofcloud', '0001_squashed_0007_instance_snap_task_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='simulation',
            name='solver',
            field=models.CharField(default=b'', max_length=100),
        ),
    ]
