# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ofcloud', '0003_simulation_count'),
    ]

    operations = [
        migrations.AlterField(
            model_name='instance',
            name='instance_id',
            field=models.TextField(max_length=100, blank=True),
        ),
        migrations.AlterField(
            model_name='instance',
            name='ip',
            field=models.TextField(max_length=15, blank=True),
        ),
        migrations.AlterField(
            model_name='instance',
            name='snap_task_id',
            field=models.CharField(max_length=100, blank=True),
        ),
    ]
