# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ofcloud', '0013_auto_20170317_0956'),
    ]

    operations = [
        migrations.AddField(
            model_name='instance',
            name='thread_id',
            field=models.IntegerField(null=True),
        ),
    ]
