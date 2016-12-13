from enum import Enum

from django.db import models


class Simulation(models.Model):
    simulation_name = models.CharField(max_length=200)
    image = models.CharField(max_length=100)
    flavor = models.CharField(max_length=100)
    solver = models.CharField(max_length=100, default='')
    instance_count = models.IntegerField(default=1)

    container_name = models.CharField(max_length=50)
    input_data_object = models.CharField(max_length=100)

    cases = models.TextField(blank=True)


class Instance(models.Model):
    Status = Enum("Status", "INIT UP RUNNING")

    name = models.CharField(max_length=100)
    config = models.TextField(blank=True)
    ip = models.TextField(max_length=15, blank=True)
    instance_id = models.TextField(max_length=100, blank=True)

    simulation = models.ForeignKey(Simulation, on_delete=models.CASCADE)

    snap_task_id = models.CharField(max_length=100, blank=True)

    status = models.CharField(max_length=100, default=Status.INIT.name)

    class Meta:
        ordering = ('name',)
