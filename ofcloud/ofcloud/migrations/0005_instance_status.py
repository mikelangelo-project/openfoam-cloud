# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ofcloud', '0004_auto_20161213_2030'),
    ]

    operations = [
        migrations.AddField(
            model_name='instance',
            name='status',
            field=models.CharField(default=b'INIT', max_length=100),
        ),
    ]
