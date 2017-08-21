import uuid
from enum import Enum

from django.db import models


def make_uuid_ac():
    return uuid.uuid4()


class Simulation(models.Model):
    Status = Enum("Status", "PENDING DEPLOYING RUNNING COMPLETE FAILED")

    id = models.UUIDField(primary_key=True, default=make_uuid_ac, editable=False)

    simulation_name = models.CharField(max_length=200)
    image = models.CharField(max_length=100)
    flavor = models.CharField(max_length=100)
    solver = models.CharField(max_length=100, default='')
    instance_count = models.IntegerField(default=1)

    container_name = models.CharField(max_length=50)
    input_data_object = models.CharField(max_length=100)

    cases = models.TextField(blank=True)

    status = models.CharField(max_length=100, default=Status.PENDING.name)


class Instance(models.Model):
    Status = Enum("Status", "PENDING DEPLOYING UP RUNNING COMPLETE FAILED")

    id = models.UUIDField(primary_key=True, default=make_uuid_ac, editable=False)

    name = models.CharField(max_length=100)
    config = models.TextField(blank=True)
    ip = models.TextField(max_length=15, blank=True)
    instance_id = models.TextField(max_length=100, blank=True)
    provider = models.TextField(max_length=100, blank=True)

    simulation = models.ForeignKey(Simulation, on_delete=models.CASCADE)

    snap_task_id = models.CharField(max_length=100, blank=True)

    status = models.CharField(max_length=100, default=Status.PENDING.name)

    local_case_location = models.CharField(max_length=100, blank=True)
    nfs_case_location = models.CharField(max_length=100, blank=True)

    retry_attempts = models.IntegerField(default=0)

    thread_id = models.IntegerField(null=True)

    class Meta:
        ordering = ('name',)
