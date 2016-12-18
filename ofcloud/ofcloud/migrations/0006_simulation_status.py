# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ofcloud', '0005_instance_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='simulation',
            name='status',
            field=models.CharField(default=b'PENDING', max_length=100),
        ),
    ]
