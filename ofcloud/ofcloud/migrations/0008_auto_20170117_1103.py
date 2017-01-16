# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import ofcloud.models


class Migration(migrations.Migration):

    dependencies = [
        ('ofcloud', '0007_auto_20170116_1507'),
    ]

    operations = [
        migrations.AlterField(
            model_name='instance',
            name='id',
            field=models.UUIDField(default=ofcloud.models.make_uuid_ac, serialize=False, editable=False, primary_key=True),
        ),
        migrations.AlterField(
            model_name='simulation',
            name='id',
            field=models.UUIDField(default=ofcloud.models.make_uuid_ac, serialize=False, editable=False, primary_key=True),
        ),
    ]
