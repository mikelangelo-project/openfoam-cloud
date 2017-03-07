import abc
import traceback

import requests

from snap import api as snap_api


class Provider:
    __metaclass__ = abc.ABCMeta

    NOT_IMPLEMENTED_MSG = "Exception raised, BaseSimulationLauncher is supposed to be an interface / abstract class!"

    @abc.abstractmethod
    def prepare_instance(self, simulation_launch_dto):
        raise NotImplementedError(self.NOT_IMPLEMENTED_MSG)

    @abc.abstractmethod
    def modify_and_run_instance(self, simulation_launch_dto):
        raise NotImplementedError(self.NOT_IMPLEMENTED_MSG)

    @abc.abstractmethod
    def get_local_nfs_mount_location(self):
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
    def get_provider_id(self):
        raise NotImplementedError(self.NOT_IMPLEMENTED_MSG)

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

    def start_snap_collector(self, simulation_launch_dto):
        try:
            print "Starting snap collector"
            t = snap_api.create_openfoam_task(simulation_launch_dto.simulation_instance.ip)
            simulation_launch_dto.simulation_instance.snap_task_id = t
            print "\ttask id %s" % t
        except requests.ConnectionError, requests.Timeout:
            print traceback.format_exc()
            print "Snap collector request timed out. Simulation will be ran despite this error."


class ProviderLaunchDto:
    def __init__(self, simulation_instance, image_name, capstan_package_folder):
        self.simulation_instance = simulation_instance
        self.image_name = image_name
        self.capstan_package_folder = capstan_package_folder
        self.unique_server_name = None
