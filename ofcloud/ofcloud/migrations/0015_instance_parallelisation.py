# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ofcloud', '0014_instance_thread_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='instance',
            name='parallelisation',
            field=models.IntegerField(default=1),
        ),
    ]
