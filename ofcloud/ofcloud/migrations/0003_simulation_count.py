# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ofcloud', '0002_simulation_solver'),
    ]

    operations = [
        migrations.AddField(
            model_name='simulation',
            name='instance_count',
            field=models.IntegerField(default=1),
        ),
    ]
