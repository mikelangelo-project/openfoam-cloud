import json
import logging
import os
import os.path
import tempfile
import time
import traceback
from os import environ as env

import requests
from django.conf import settings

from ofcloud import network_utils, capstan_utils, case_utils, openstack_utils
from ofcloud.models import Instance, Simulation
from snap import api as snap_api

logger = logging.getLogger(__name__)


def get_floating_ip(nova):
    # Find the first available floating IP
    for fip in nova.floating_ips.list():
        if fip.instance_id is None:
            return fip

    # If there was no available floating IP, create and return new
    return nova.floating_ips.create('external_network')


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


def launch_simulation_instance(simulation_instance):
    simulation = Simulation.objects.get(id=simulation_instance.simulation_id)
    simulation.status = Simulation.Status.DEPLOYING.name
    simulation.save()
    simulation_instance.status = Instance.Status.DEPLOYING.name
    simulation_instance.save()

    try:
        print "Launching instance %s" % simulation_instance.id

        # Authenticate against required services
        glance_client = openstack_utils.get_glance_client()
        nova_client = openstack_utils.get_nova_client()

        case_folder = case_utils.prepare_case_files(simulation)
        case_utils.copy_case_files_to_nfs_location(simulation_instance, case_folder)

        # TODO have an image ready on glance, as now we don't compile the case folder into the OSv image
        capstan_package_folder = tempfile.mkdtemp(prefix='ofcloud-capstan-')
        image_name = capstan_utils.init_and_compose_capstan_package(simulation.simulation_name,
                                                                    capstan_package_folder,
                                                                    simulation.solver)
        image, unique_image_name = __import_image_into_glance(
            glance_client,
            image_name,
            simulation,
            capstan_package_folder)

        # Get data for the new server we are about to create.
        # of_image = nova_client.images.find(name=unique_image_name)
        of_image = nova_client.images.get(image.id)
        flavor = nova_client.flavors.find(id=simulation.flavor)

        unique_server_name = '%s-%s' % (simulation_instance.name, str(simulation_instance.id))

        print "Creating required instance %s" % unique_server_name

        # setup network
        openfoam_network = network_utils.get_openfoam_network_id()
        nics = [{'net-id': openfoam_network}]

        nova_client.servers.create(name=unique_server_name,
                                   image=of_image,
                                   flavor=flavor,
                                   nics=nics
                                   )

        nova_server_list = nova_client.servers.list(search_opts={'name': unique_server_name})

        if len(nova_server_list) != 1:
            # TODO handle this, do not allow multiple servers with the same unique name
            #  it would be best if we destroy all we find before spawning a new one
            raise RuntimeError("Expected 1 server with unique name '%s', instead found %d" % (
                unique_server_name, len(nova_server_list)))

        simulation_instance.nova_server_id = nova_server_list[0].id

        # Wait for the instance to become active
        while True:
            nova_server = nova_client.servers.get(simulation_instance.nova_server_id)

            if nova_server.status == 'ACTIVE':
                simulation_instance.status = Instance.Status.UP.name
                simulation_instance.save()
                break
            time.sleep(0.5)

        # Remove the uploaded image as it is no longer required
        glance_client.images.delete(image.id)

        print "Associating floating IPs"
        nova_server = nova_client.servers.get(simulation_instance.nova_server_id)
        floating_ip = get_floating_ip(nova_client)
        nova_server.add_floating_ip(floating_ip.ip)
        simulation_instance.ip = floating_ip.ip

        print "\tInstance %s accessible at %s" % (nova_server.name, floating_ip.ip)

        print "Wait 5s for the router to setup floating IPs"
        time.sleep(5)

        simulation_instance_case_folder = "/ofcloud_results"
        print "Customising simulations"

        instance_api = rest_api_for(simulation_instance.ip)

        # Request input case update given the provided customisations.
        case_utils.update_case_files(simulation_instance.local_case_location, json.loads(simulation_instance.config))

        nfs_ip = settings.NFS_IP

        __mount_instance_case_folder(instance_api, nfs_ip, simulation_instance, simulation_instance_case_folder)

        print "\t\tsetting up the execution environment"

        # Now we need to setup some env variables.
        requests.post("%s/env/OPENFOAM_CASE" % instance_api,
                      data={"val": '%s-%s' % (unique_server_name, simulation_instance.name)})
        requests.post("%s/env/TENANT" % instance_api, data={"val": env['OS_TENANT_NAME']})
        requests.post("%s/env/WM_PROJECT_DIR" % instance_api, data={"val": '/openfoam'})

        try:
            print "Starting snap collector"
            t = snap_api.create_openfoam_task(simulation_instance.ip)
            simulation_instance.snap_task_id = t
            print "\ttask id %s" % t
        except requests.ConnectionError, requests.Timeout:
            print traceback.format_exc()
            print "Snap collector request timed out. Simulation will be ran despite this error."

        simulation_instance.nova_server_id = nova_server.id

        print "Starting OpenFOAM simulations"
        solver_command = "/usr/bin/%s -case %s" % (
            capstan_utils.get_solver_so(simulation.solver), simulation_instance_case_folder)
        instance_api = rest_api_for(simulation_instance.ip)
        requests.put("%s/app/" % instance_api, data={"command": solver_command})

        simulation_instance.status = Instance.Status.RUNNING.name
        simulation_instance.save()
        simulation.status = Simulation.Status.RUNNING.name
        simulation.save()

        return simulation, simulation_instance
    except:
        print traceback.format_exc()
        __handle_launch_instance_exception(simulation, simulation_instance)


def shutdown_nova_servers(instances):
    """
    Shuts down nova servers with provided ids.

    :param instances: A list of instances
    :return:
    """

    nova = openstack_utils.get_nova_client()

    for instance in instances:
        try:
            print "Shutting down instances with ids %s" % str(instance.nova_server_id)
            server = nova.servers.get(instance.nova_server_id)
            nova.servers.delete(server.id)
        except:
            print "Could not shutdown nova server %s" % instance.nova_server_id
            print traceback.format_exc()


def split_running_and_orphaned_instances(instances):
    """
    Takes the provided Instance list and separates the containing instances regarding they still have a nova server
    running or not.

    :param instances: A list of Instance objects
    :return: tuple, first element is a list of instances with running servers, second element is a list of
    instances without running servers (orphaned)
    """
    running_instances = []
    orphaned_instances = []

    nova = openstack_utils.get_nova_client()

    # TODO when deciding on writing unit tests (we really should), this should be a function parameter
    nova_server_ids = {nova_server.id: True for nova_server in nova.servers.list()}

    for instance in instances:
        if instance.nova_server_id in nova_server_ids:
            running_instances.append(instance)
        else:
            orphaned_instances.append(instance)

    return running_instances, orphaned_instances


def set_instance_status(instances, status):
    """
    Updates all the instances corresponding to the ids in instance_ids to the provided status

    :param instances: List of instances
    :param status: Instance.Status value. Should be string value, not Enum. Example: Instance.Status.PENDING.name
    :return:
    """
    Instance.objects.filter(id__in=[instance.id for instance in instances]).update(status=status)


def get_instances_of_finished_simulations(running_instances):
    """
    Takes the provided running_instance_ids and filters out the instances which have the openFOAM solver thread still
    running.

    :param running_instances: List of instances with a nova server running.
    :return: Two lists, the first containing nova server IDs and the second instance IDs of running and finished
    simulation nova servers and instances
    """

    finished_instances = []
    print "Filtering servers with finished calculations ..."
    for instance in running_instances:
        try:
            if __is_openfoam_thread_finished(instance):
                finished_instances.append(instance)
        except:
            print "Could not determine status of openFOAM thread on instance %s" % instance.id

    print "Instances with finished calculations %s" % [instance.id for instance in finished_instances]
    return finished_instances


def destroy_simulation(simulation):
    nova = openstack_utils.get_nova_client()

    for instance in simulation.instance_set.all():
        try:
            server = nova.servers.get(instance.nova_server_id)
            nova.servers.delete(server)

            snap_api.stop_openfoam_task(instance.snap_task_id)
        except:
            print "Instance not found"


def is_simulation_instance_runnable(simulation_instance):
    """
    Checks whether the simulation can be run at this moment.

    :param simulation_instance: instance object
    :type simulation_instance: Instance object ofcloud.models.Instance
    :return: Boolean
    """

    # get nova client
    nova = openstack_utils.get_nova_client()
    neutron = openstack_utils.get_neutron_client()

    # get required data
    flavor_dict = openstack_utils.build_flavor_dict(nova.flavors.list())

    floating_ips = filter(lambda f_ip: f_ip['fixed_ip_address'] is not None,
                          neutron.list_floatingips(retrieve_all=True)['floatingips'])

    deploying_simulation_instances = Instance.objects.filter(status=Instance.Status.DEPLOYING.name)
    simulation = Simulation.objects.get(id=simulation_instance.simulation_id)
    simulation_flavor = flavor_dict[simulation.flavor]

    servers = nova.servers.list()
    total_quotas = nova.quotas.get(tenant_id=env['OS_TENANT_ID'])

    # Check which limits are stricter, and use those
    total_quotas.cores = min(settings.OPENFOAM_MAX_CPU_USAGE, total_quotas.cores)
    total_quotas.instances = min(settings.OPENFOAM_MAX_INSTANCE_USAGE, total_quotas.instances)

    # build our own quotas and usages, because nova can not do this at the moment
    available_quotas = openstack_utils.get_available_resources(total_quotas,
                                                               servers,
                                                               deploying_simulation_instances,
                                                               flavor_dict,
                                                               floating_ips)

    available_quotas.cores -= simulation_flavor.vcpus
    # Here we actually do not know, how many of these instances will have a floating ip assigned,
    # so to be safe we assume they will all have one
    available_quotas.floating_ips -= 1
    available_quotas.instances -= 1
    available_quotas.ram -= simulation_flavor.ram

    # Configure logging in the future
    # logging.debug(str(available_resources))

    return \
        available_quotas.cores >= 0 \
        and available_quotas.floating_ips >= 0 \
        and available_quotas.instances >= 0 \
        and available_quotas.ram >= 0


def __import_image_into_glance(glance_client, image_name, simulation, capstan_package_folder):
    # Import image into Glance
    mpm_image = os.path.expanduser(os.path.join("~", ".capstan", "repository",
                                                image_name, "%s.qemu" % (os.path.basename(capstan_package_folder))))
    unique_image_name = simulation.image + '_' + str(simulation.id)
    print "Uploading image %s to Glance" % unique_image_name
    image = glance_client.images.create(name=unique_image_name, disk_format="qcow2", container_format="bare")
    glance_client.images.upload(image.id, open(mpm_image, 'rb'))
    return image, unique_image_name


def __mount_instance_case_folder(instance_api, nfs_ip, simulation_instance, simulation_instance_case_folder):
    nfs_mount = 'nfs://%s%s %s' % (nfs_ip, simulation_instance.nfs_case_location, simulation_instance_case_folder)
    print "\t\tmounting network file storage with %s" % nfs_mount
    mount_command = "/tools/mount-nfs.so %s" % nfs_mount
    requests.put(
        "%s/app" % instance_api,
        data={"command": mount_command}
    )


def __handle_launch_instance_exception(simulation, simulation_instance):
    simulation_instance.retry_attempts += 1
    print "Setting instance %s retry attempts to %d/%d" % \
          (simulation_instance.id, simulation_instance.retry_attempts, settings.OPENFOAM_SIMULATION_MAX_RETRIES)

    max_retries = settings.OPENFOAM_SIMULATION_MAX_RETRIES
    if simulation_instance.retry_attempts < max_retries:
        simulation_instance.status = Instance.Status.PENDING.name
        simulation_instance.save()
    else:
        print "Max retries reached, sending instance to FAILED"
        simulation_instance.status = Instance.Status.FAILED.name
        simulation_instance.save()

        simulation_instances = Instance.objects.filter(simulation=simulation.id)
        print "Other instances in this simulation %s" % str(simulation_instances)

        all_failed = True
        for simulation_instance in simulation_instances:
            print "%s is in status %s" % (simulation_instance.id, simulation_instance.status)
            if simulation_instance.status != Instance.Status.FAILED.name:
                all_failed = False
                break

        if all_failed:
            print("All underlying instances have failed, sending simulation %s to FAILED state" % simulation.id)
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
    openfoam_thread_present = False
    thread_list = __get_instance_thread_info(instance)

    for thread in thread_list:
        if thread['name'] == '/usr/bin/simple':
            print "Found openFOAM thread! %s" % thread
            openfoam_thread_present = True
            if thread['status'] == 'terminated':
                return True

    return not openfoam_thread_present
