import abc
import json
import traceback
from os import environ as env

import requests

from ofcloud import case_utils
from ofcloud import utils, capstan_utils
from ofcloud.models import Instance, Simulation
from snap import api as snap_api


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

    def modify_and_run_instance(self, launch_dto):
        # START modifying the running server, setup nfs mount, snap collector, some ENV variables and
        # start the simulation

        print "Customising simulations"
        instance_api = utils.rest_api_for(launch_dto.simulation_instance.ip)
        # Request input case update given the provided customisations.
        case_utils.update_case_files(launch_dto.simulation_instance.local_case_location,
                                     json.loads(launch_dto.simulation_instance.config))

        print("Mounting NFS")
        nfs_address = self.nfs_address
        simulation_instance_case_folder = "/case"
        utils.mount_instance_case_folder(instance_api, nfs_address, launch_dto.simulation_instance,
                                         simulation_instance_case_folder)

        print "\t\tsetting up the execution environment"

        # Now we need to setup some env variables.
        requests.post("%s/env/OPENFOAM_CASE" % instance_api,
                      data={"val": '%s-%s' % (
                          launch_dto.unique_server_name, launch_dto.simulation_instance.name)})
        requests.post("%s/env/TENANT" % instance_api, data={"val": env['OS_TENANT_NAME']})
        requests.post("%s/env/WM_PROJECT_DIR" % instance_api, data={"val": '/openfoam'})

        self.start_snap_collector(launch_dto)

        print "Starting OpenFOAM simulations"
        solver_so = capstan_utils.get_solver_so(launch_dto.simulation_instance.simulation.solver)
        solver_command = "/usr/bin/%s -case %s" % (solver_so, simulation_instance_case_folder)
        requests.put("%s/app/" % instance_api, data={"command": solver_command}, timeout=30)

        launch_dto.simulation_instance.status = Instance.Status.RUNNING.name
        launch_dto.simulation_instance.save()
        launch_dto.simulation_instance.simulation.status = Simulation.Status.RUNNING.name
        launch_dto.simulation_instance.simulation.save()

        return launch_dto

    def start_snap_collector(self, simulation_launch_dto):
        try:
            print "Starting snap collector"
            t = snap_api.create_openfoam_task(simulation_launch_dto.simulation_instance.ip)
            simulation_launch_dto.simulation_instance.snap_task_id = t
            print "\ttask id %s" % t
        except requests.ConnectionError, requests.Timeout:
            print traceback.format_exc()
            print "Snap collector request timed out. Simulation will be ran despite this error."