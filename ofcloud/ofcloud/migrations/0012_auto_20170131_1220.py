# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ofcloud', '0011_instance_retry_attempts'),
    ]

    operations = [
        migrations.RenameField(
            model_name='instance',
            old_name='instance_id',
            new_name='nova_server_id',
        ),
    ]
