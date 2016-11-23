# -*- coding: utf-8 -*-
# Generated by Django 1.9.2 on 2016-04-11 03:57
from __future__ import unicode_literals

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    replaces = [(b'ofcloud', '0001_initial'), (b'ofcloud', '0002_simulation_cases'),
                (b'ofcloud', '0003_simulationinstance'), (b'ofcloud', '0004_auto_20160219_0401'),
                (b'ofcloud', '0005_auto_20160219_0438'), (b'ofcloud', '0006_instance_instance_id'),
                (b'ofcloud', '0007_instance_snap_task_id')]

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Simulation',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('simulation_name', models.CharField(max_length=200)),
                ('image', models.CharField(max_length=100)),
                ('flavor', models.CharField(max_length=100)),
                ('container_name', models.CharField(max_length=50)),
                ('input_data_object', models.CharField(max_length=100)),
                ('cases', models.TextField(blank=True)),
            ],
        ),
        migrations.CreateModel(
            name='SimulationInstance',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('config', models.TextField(blank=True)),
                ('ip', models.TextField(max_length=15)),
            ],
        ),
        migrations.AlterModelOptions(
            name='simulationinstance',
            options={'ordering': ('name',)},
        ),
        migrations.AddField(
            model_name='simulationinstance',
            name='simulation',
            field=models.ForeignKey(default=-1, on_delete=django.db.models.deletion.CASCADE, to='ofcloud.Simulation'),
            preserve_default=False,
        ),
        migrations.RenameModel(
            old_name='SimulationInstance',
            new_name='Instance',
        ),
        migrations.AddField(
            model_name='instance',
            name='instance_id',
            field=models.TextField(default='', max_length=100),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='instance',
            name='snap_task_id',
            field=models.CharField(default='', max_length=100),
            preserve_default=False,
        ),
    ]
