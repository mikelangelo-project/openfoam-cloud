# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ofcloud', '0010_auto_20170124_0825'),
    ]

    operations = [
        migrations.AddField(
            model_name='instance',
            name='retry_attempts',
            field=models.IntegerField(default=0),
        ),
    ]
