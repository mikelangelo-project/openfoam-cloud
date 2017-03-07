# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ofcloud', '0012_auto_20170131_1220'),
    ]

    operations = [
        migrations.RenameField(
            model_name='instance',
            old_name='nova_server_id',
            new_name='instance_id',
        ),
        migrations.AddField(
            model_name='instance',
            name='provider',
            field=models.TextField(max_length=100, blank=True),
        ),
    ]
