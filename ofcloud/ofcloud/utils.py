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


import json
import logging
import tempfile
import traceback

import requests
from django.conf import settings

from ofcloud import capstan_utils, case_utils, openstack_utils
from ofcloud.models import Instance, Simulation
from ofcloud.provider.dto import ProviderLaunchDto
from snap import api as snap_api

logger = logging.getLogger(__name__)


def rest_api_for(ip):
    return "http://%s:8000" % ip


def create_simulation(simulation_serializer):
    simulation = simulation_serializer.create(simulation_serializer.validated_data)

    if not simulation.cases or len(simulation.cases) == 0:
        simulation.cases = json.dumps([{"name": simulation.simulation_name, "updates": {}}])

    instances = __create_simulation_instances(simulation)

    for instance in instances:
        simulation.instance_set.create(name=instance['name'],
                                       config=instance['config'])

    return simulation


def __create_simulation_instances(simulation):
    instances = []

    simulation_cases = json.loads(simulation.cases)

    for case in simulation_cases:
        instances.append({
            'name': '%s-%s' % (simulation.simulation_name, case['name']),
            'config': json.dumps(case['updates'])
        })
    return instances


def prepare_simulation_instance(simulation_instance, simulation_providers):
    is_runnable = False
    for provider in simulation_providers:
        if provider.is_simulation_instance_runnable(simulation_instance):
            is_runnable = True

            simulation = Simulation.objects.get(id=simulation_instance.simulation_id)
            simulation.status = Simulation.Status.DEPLOYING.name
            simulation.save()

            simulation_instance.provider = provider.get_provider_id()
            simulation_instance.status = Instance.Status.DEPLOYING.name
            simulation_instance.save()

            try:
                print "Launching instance %s with provider %s" % (simulation_instance.id, provider.get_provider_id())

                simulation_instance.parallelisation = provider.get_instance_cpus(simulation_instance.simulation)
                simulation_instance.save()

                # START preparing local files (OSv image, case files ...)
                case_folder = case_utils.prepare_case_files(simulation, simulation_instance.parallelisation)

                case_utils.copy_case_files_to_nfs_location(
                    simulation_instance,
                    case_folder,
                    provider.local_nfs_mount_location,
                    provider.nfs_server_mount_folder)

                capstan_package_folder = tempfile.mkdtemp(prefix='ofcloud-capstan-')

                image_name = capstan_utils.init_and_compose_capstan_package(
                    simulation.simulation_name,
                    capstan_package_folder,
                    simulation.solver
                )
                # FINISH preparing local files (OSv image, case files ...)

                launch_dto = ProviderLaunchDto(
                    simulation_instance=simulation_instance,
                    image_name=image_name,
                    capstan_package_folder=capstan_package_folder
                )

                # Prepare instances
                provider.prepare_instance(launch_dto)

                # Customize with case parameters
                provider.prepare_instance_env(launch_dto)
                return launch_dto.simulation_instance

            except:
                print traceback.format_exc()
                __handle_launch_instance_exception(simulation, simulation_instance, provider)

            break
        else:
            print "No more free quotas!"

    if not is_runnable:
        print("Maximum number of simulation instances already running! "
              "Pending instances will be run after currently running instances finish")


def destroy_simulation(simulation):
    nova = openstack_utils.get_nova_client()

    for instance in simulation.instance_set.all():
        try:
            server = nova.servers.get(instance.instance_id)
            nova.servers.delete(server)

            snap_api.stop_openfoam_task(instance.snap_task_id)
        except:
            print "Instance not found"


def update_instance_status(instances, status):
    """
    Updates all the instances corresponding to the ids in instance_ids to the provided status

    :param instances: List of instances
    :param status: Instance.Status value. Should be string value, not Enum. Example: Instance.Status.PENDING.name
    :return:
    """
    Instance.objects.filter(id__in=[instance.id for instance in instances]).update(status=status)


def get_instances_with_finished_openfoam_thread(instances):
    """
    Takes the provided running_instance_ids and filters out the instances which have the openFOAM thread still running.
    
    :param instances: List of instances with a nova server running.
    :return: List of instances which have finished their simulation calculations
    """

    finished_instances = []
    for instance in instances:
        try:
            if __is_openfoam_thread_finished(instance):
                finished_instances.append(instance)
        except:
            print "Could not determine status of openFOAM thread on instance %s" % instance.id
            print traceback.format_exc()
    if len(finished_instances):
        print "Instances with finished openFOAM thread: %s" % [instance.id for instance in finished_instances]
    return finished_instances


def mount_instance_case_folder(instance_api, nfs_address, simulation_instance, simulation_instance_case_folder):
    nfs_mount = 'nfs://%s%s %s' % (nfs_address, simulation_instance.nfs_case_location, simulation_instance_case_folder)
    print "\t\tmounting network file storage with %s" % nfs_mount
    mount_command = "/tools/mount-nfs.so %s" % nfs_mount
    requests.put(
        "%s/app" % instance_api,
        data={"command": mount_command}
    )


def __handle_launch_instance_exception(simulation, simulation_instance, provider):
    simulation_instance.retry_attempts += 1
    print "Setting instance %s retry attempts to %d/%d" % \
          (simulation_instance.id, simulation_instance.retry_attempts, settings.OPENFOAM_SIMULATION_MAX_RETRIES)

    if simulation_instance.instance_id:
        provider.shutdown_instances([simulation_instance])

    max_retries = settings.OPENFOAM_SIMULATION_MAX_RETRIES
    if simulation_instance.retry_attempts < max_retries:
        simulation_instance.status = Instance.Status.PENDING.name
        simulation_instance.save()
    else:
        print "Max retries reached, sending instance to FAILED"
        simulation_instance.status = Instance.Status.FAILED.name
        simulation_instance.save()

        simulation_instances = Instance.objects.filter(simulation=simulation.id)

        all_failed = True
        for simulation_instance in simulation_instances:
            print "%s is in status %s" % (simulation_instance.id, simulation_instance.status)
            if simulation_instance.status != Instance.Status.FAILED.name:
                all_failed = False
                break

        if all_failed:
            print(
                "All underlying instances have failed, "
                "sending simulation %s to FAILED state" % simulation.id)
            simulation.status = Instance.Status.FAILED.name
            simulation.save()


def __get_instance_thread_info(instance):
    """
    Retrieves the OSv VM thread info through its REST api.

    :param instance: Instance object of the simulation we are querying for thread info. The instance should contain the
    IP field.
    :return: A list of thread info objects.
    """
    try:
        threads_rest_api = "%s/os/threads" % rest_api_for(instance.ip)
        print "Querying threads api on %s" % threads_rest_api
        response = requests.get(threads_rest_api)
        json_response = json.loads(response.text)

        thread_list = json_response['list']
        return thread_list
    except:
        print "Instance api not available"
        print traceback.format_exc()


def __is_openfoam_thread_finished(instance):
    """
    Takes a OSv VM thread list and checks if the OpenFOAM solver thread is still executing.

    :param instance: Instance object of the simulation we query for thread info
    :return: True if the thread is terminated or not present, False if it is still executing
    """
    thread_list = __get_instance_thread_info(instance)
    openfoam_threads = filter(lambda t: t['id'] == instance.thread_id, thread_list)

    if len(openfoam_threads) == 0:
        return True
    else:
        return openfoam_threads[0]['status'] == 'terminated'
