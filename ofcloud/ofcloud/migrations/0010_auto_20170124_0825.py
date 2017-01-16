# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ofcloud', '0008_auto_20170117_1103'),
    ]

    operations = [
        migrations.AddField(
            model_name='instance',
            name='local_case_location',
            field=models.CharField(max_length=100, blank=True),
        ),
        migrations.AddField(
            model_name='instance',
            name='nfs_case_location',
            field=models.CharField(max_length=100, blank=True),
        ),
    ]
