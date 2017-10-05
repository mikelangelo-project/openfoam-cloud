# Copyright (C) 2015-2017 XLAB, Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import uuid

from django.db import models
from enum import Enum


def make_uuid_ac():
    return uuid.uuid4()


class Simulation(models.Model):
    """
    Simulation model representing one OpenFOAM simulation. One simulation can be calculated on one or more instances
    (see below).

    Simulation can be in one of the following states:
    PENDING - waiting for the scheduler to start preparing case files, instances, etc.
    DEPLOYING - in deploying procedure, case files and instances are being prepared, but the simulation has not yet
        started
    RUNNING - simulation is currently running on the underlying instances
    COMPLETE - simulation calculation is complete and was successful
    FAILED - simulation calculation has failed, see log files for stack trace

    """
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
    decomposition = models.TextField(blank=True)


class Instance(models.Model):
    """
    Instance model representing one VM where an OpenFOAM simulation is calculated. Instance contains all the info 
    necessary for running a calculation (simulation config, case directory location, IP of the VM, etc). 
    
    An instance can be in one of the following states:
    PENDING - waiting for the scheduler to start preparing case files and then start this instance
    DEPLOYING - instance is in deployament procedure, preparing case files, starting instance, mounting nfs, etc.
    UP - instance VM is UP, but still not configured completely (usually needs ENV variables set, floating_ip 
        assigned, etc.)
    READY - instance is UP and its environment configured and ready for calculation/decomposition
    DECOMPOSING - instance is running `decomposePar` which prepares case files for multi threaded execution. Only 
        instances running on a flavor with multiple VCPUs can be in this state
    RUNNING - instance VM is executing OpenFOAM calculation on a single thread. Usually instances with only one VCPU 
        will be in this state, but in case we can not retrieve instance info on VCPUs even multi-VCPU instances can be 
        in this state
    RUNNING_MPI - instance VM is executing OpenFOAM calculation via the `mpirun` command (multi threaded execution).
        Only multi-VCPU instances can be in this state.
    RECONSTRUCTING - instance VM is executing OpenFOAMs `reconstructPar` command. Only multi-VCPU instances who ran the 
        simulation calculation via the `mpirun` command can be in this state.
    COMPLETE - simulation calculation is complete and was successful
    FAILED - simulation calculation failed. See logs for more info
    
    """

    Status = Enum("Status",
                  "PENDING "
                  "DEPLOYING "
                  "UP "
                  "READY "
                  "DECOMPOSING "
                  "RUNNING "
                  "RUNNING_MPI "
                  "RECONSTRUCTING "
                  "COMPLETE "
                  "FAILED ")
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

    parallelisation = models.IntegerField(default=1)

    @property
    def multicore(self):
        return self.parallelisation > 1

    class Meta:
        ordering = ('name',)
