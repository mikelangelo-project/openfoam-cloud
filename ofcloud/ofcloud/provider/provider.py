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


import abc
import json
import traceback
from os import environ as env

import requests

from ofcloud import capstan_utils
from ofcloud import case_utils
from ofcloud import utils
from ofcloud.models import Instance, Simulation
from snap import api as snap_api

SIMULATION_INSTANCE_CASE_FOLDER = "/case"


class Provider:
    __metaclass__ = abc.ABCMeta

    NOT_IMPLEMENTED_MSG = "Exception raised, BaseSimulationLauncher is supposed to be an interface / abstract class!"

    def __init__(self, provider_id, provider_config):
        self.id = provider_id
        self.local_nfs_mount_location = provider_config.get('LOCAL_NFS_MOUNT_LOCATION')
        self.nfs_server_mount_folder = provider_config.get('NFS_SERVER_MOUNT_FOLDER')
        self.nfs_address = provider_config.get('NFS_ADDRESS')
        self.max_cpu_usage = provider_config.get('MAX_CPU_USAGE')
        self.max_instance_usage = provider_config.get('MAX_INSTANCE_USAGE')

    @abc.abstractmethod
    def prepare_instance(self, simulation_launch_dto):
        raise NotImplementedError(self.NOT_IMPLEMENTED_MSG)

    @abc.abstractmethod
    def is_simulation_instance_runnable(self, simulation_instance):
        raise NotImplementedError(self.NOT_IMPLEMENTED_MSG)

    @abc.abstractmethod
    def get_running_server_ids(self):
        raise NotImplementedError(self.NOT_IMPLEMENTED_MSG)

    @abc.abstractmethod
    def shutdown_instances(self, instances):
        raise NotImplementedError(self.NOT_IMPLEMENTED_MSG)

    @abc.abstractmethod
    def get_instance_cpus(self, instance_simulation):
        raise NotImplementedError(self.NOT_IMPLEMENTED_MSG)

    def get_provider_id(self):
        return self.id

    def get_local_nfs_mount_location(self):
        return self.local_nfs_mount_location

    def split_running_and_orphaned_instances(self, instances):
        server_ids = self.get_running_server_ids()
        running_instances = []
        orphaned_instances = []
        for instance in instances:
            if instance.instance_id in server_ids:
                running_instances.append(instance)
            else:
                orphaned_instances.append(instance)
        return running_instances, orphaned_instances

    def prepare_instance_env(self, launch_dto):
        # START modifying the running server, setup nfs mount, snap collector, some ENV variables and
        # start the simulation

        print "Customising simulations"
        instance_api = utils.rest_api_for(launch_dto.simulation_instance.ip)
        # Request input case update given the provided customisations.
        case_utils.update_case_files(launch_dto.simulation_instance.local_case_location,
                                     json.loads(launch_dto.simulation_instance.config))

        print("Mounting NFS")
        nfs_address = self.nfs_address
        utils.mount_instance_case_folder(instance_api, nfs_address, launch_dto.simulation_instance,
                                         SIMULATION_INSTANCE_CASE_FOLDER)

        print "\t\tsetting up the execution environment"

        # Now we need to setup some env variables.
        requests.post("%s/env/OPENFOAM_CASE" % instance_api,
                      data={"val": '%s-%s' % (
                          launch_dto.unique_server_name, launch_dto.simulation_instance.name)})
        requests.post("%s/env/TENANT" % instance_api, data={"val": env['OS_TENANT_NAME']})
        requests.post("%s/env/WM_PROJECT_DIR" % instance_api, data={"val": '/openfoam'})

        requests.post("%s/env/LD_LIBRARY_PATH" % instance_api, data={"val": '/usr/bin/'})
        requests.post("%s/env/PATH" % instance_api, data={"val": '/usr/bin/'})

        requests.post("%s/env/MPI_BUFFER_SIZE" % instance_api, data={"val": '1000000'})

        self.start_snap_collector(launch_dto)

        if launch_dto.simulation_instance.multicore:
            # if we plan running on multiple cpus run decomposePar first
            decompose_command = "/usr/bin/decomposePar -case %s" % SIMULATION_INSTANCE_CASE_FOLDER
            launch_dto.simulation_instance.status = Instance.Status.DECOMPOSING.name
            req = requests.put("%s/app/" % instance_api, data={"command": decompose_command}, timeout=30)
            # strip double quotes, because request returns '"200"' which fails when parsing to int
            launch_dto.simulation_instance.thread_id = int(req.text.strip('"'))
        else:
            launch_dto.simulation_instance.status = Instance.Status.READY.name

        launch_dto.simulation_instance.save()
        launch_dto.simulation_instance.simulation.status = Simulation.Status.RUNNING.name
        launch_dto.simulation_instance.simulation.save()

        return launch_dto

    def run_simulation(self, simulation_instance):
        print "Starting OpenFOAM simulations"
        instance_api = utils.rest_api_for(simulation_instance.ip)
        solver_so = capstan_utils.get_solver_so(simulation_instance.simulation.solver)

        if simulation_instance.multicore:
            solver_command = "/usr/bin/mpirun -n %d --allow-run-as-root /usr/bin/%s -parallel -case %s" % (
                simulation_instance.parallelisation, solver_so, SIMULATION_INSTANCE_CASE_FOLDER)
            simulation_instance.status = Instance.Status.RUNNING_MPI.name
        else:
            solver_command = "/usr/bin/%s -case %s" % (solver_so, SIMULATION_INSTANCE_CASE_FOLDER)
            simulation_instance.status = Instance.Status.RUNNING.name

        print 'Sending request with solver command: %s' % solver_command
        req = requests.put("%s/app/" % instance_api, data={"command": solver_command}, timeout=30)
        simulation_instance.thread_id = int(req.text.strip('"'))
        simulation_instance.save()

    def run_reconstruction(self, simulation_instance):
        instance_api = utils.rest_api_for(simulation_instance.ip)
        reconstruct_command = "/usr/bin/reconstructPar -case %s" % SIMULATION_INSTANCE_CASE_FOLDER
        req = requests.put("%s/app/" % instance_api, data={"command": reconstruct_command}, timeout=30)
        simulation_instance.thread_id = int(req.text.strip('"'))
        simulation_instance.status = Instance.Status.RECONSTRUCTING.name
        simulation_instance.save()

    def start_snap_collector(self, simulation_launch_dto):
        try:
            print "Starting snap collector"
            t = snap_api.create_openfoam_task(simulation_launch_dto.simulation_instance.ip)
            simulation_launch_dto.simulation_instance.snap_task_id = t
            print "\ttask id %s" % t
        except requests.RequestException:
            print traceback.format_exc()
            print "Snap collector could not be started. Simulation will be ran despite this error."
