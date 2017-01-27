import json
import logging
import os
import os.path
import re
import shutil
import tarfile
import tempfile
import time
import traceback
from os import environ as env, path
from subprocess import Popen

import boto
import boto.s3.connection
import glanceclient.v2.client as glclient
import neutronclient.v2_0.client as neutron_client
import novaclient.client as nvclient
import requests
from django.conf import settings
from keystoneauth1 import session
from keystoneauth1.identity import v2

from ofcloud import network_utils
from ofcloud.models import Instance, Simulation
from snap import api as snap_api

logger = logging.getLogger(__name__)


def update_case(case_path, updates):
    input_files = {}

    # First, get a list of files that need to be modified
    for key in updates:
        file_end_index = key.rfind('/')
        file_path = key[0:file_end_index]
        variable = key[file_end_index + 1:]

        if file_path not in input_files:
            input_files[file_path] = {}

        input_files[file_path][variable] = updates[key]

    output_files = {}

    # Now loop through files and update them.
    for input_file, variables in input_files.iteritems():
        file_path = os.path.join(case_path, input_file)

        f = open(file_path, 'r')
        data = f.read()
        f.close()

        for var, value in variables.iteritems():
            data = re.sub(re.compile('^[ \t]*%s\s+.*$' % var, re.MULTILINE), '%s %s;' % (var, value), data)

        output_files[input_file] = file_path

        f = open(file_path, 'w')
        f.write(data)
        f.close()

    return output_files


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

        sess = authenticate()

        # Authenticate against required services
        glance_client = glclient.Client(session=sess)
        nova_client = nvclient.Client("2", session=sess)

        capstan_package_folder, case_folder = __create_local_temp_folders(simulation)
        __copy_instance_case_files(case_folder, simulation_instance)

        solver_deps, solver_so = get_solver_config()[simulation.solver]

        # TODO have an image ready on glance, as now we don't compile the case folder into the OSv image
        image_name = __init_and_compose_capstan_package(simulation, capstan_package_folder, solver_deps)
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
            raise RuntimeError("Expected 1 server with unique name '%s', instead found %d" % (
                unique_server_name, len(nova_server_list)))

        simulation_instance.instance_id = nova_server_list[0].id

        # Wait for the instance to become active
        while True:
            nova_server = nova_client.servers.get(simulation_instance.instance_id)

            if nova_server.status == 'ACTIVE':
                simulation_instance.status = Instance.Status.UP.name
                simulation_instance.save()
                break
            time.sleep(0.5)

        # Remove the uploaded image as it is no longer required
        glance_client.images.delete(image.id)

        print "Associating floating IPs"
        nova_server = nova_client.servers.get(simulation_instance.instance_id)
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
        update_case(simulation_instance.local_case_location, json.loads(simulation_instance.config))

        nfs_ip = settings.NFS_IP

        __mount_instance_case_folder(instance_api, nfs_ip, simulation_instance, simulation_instance_case_folder)

        print "\t\tsetting up the execution environment"

        # Now we need to setup some env variables.
        requests.post("%s/env/OPENFOAM_CASE" % instance_api,
                      data={"val": '%s-%s' % (unique_server_name, simulation_instance.name)})
        requests.post("%s/env/TENANT" % instance_api, data={"val": env['OS_TENANT_NAME']})
        requests.post("%s/env/WM_PROJECT_DIR" % instance_api, data={"val": '/openfoam'})

        print "Starting snap collector"
        t = snap_api.create_openfoam_task(simulation_instance.ip)
        print "\ttask id %s" % t

        simulation_instance.instance_id = nova_server.id
        simulation_instance.snap_task_id = t

        print "Starting OpenFOAM simulations"
        solver_command = "/usr/bin/%s -case %s" % (solver_so, simulation_instance_case_folder)
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


def destroy_simulation(simulation):
    nova = __get_nova_client()

    for instance in simulation.instance_set.all():
        try:
            server = nova.servers.get(instance.instance_id)
            nova.servers.delete(server)

            snap_api.stop_openfoam_task(instance.snap_task_id)
        except:
            print "Instance not found"


def is_simulation_instance_runnable(simulation_instance):
    """Checks whether the simulation can be run at this moment.

    :param simulation_instance: instance object
    :type simulation_instance: Instance object ofcloud.models.Instance
    :return: Boolean
    """

    # get nova client
    nova = __get_nova_client()
    neutron = __get_neutron_client()

    # get required data
    flavor_dict = __build_flavor_dict(nova.flavors.list())
    quotas = nova.quotas.get(tenant_id=env['OS_TENANT_ID'])
    floating_ips = filter(lambda f_ip: f_ip['fixed_ip_address'] is not None,
                          neutron.list_floatingips(retrieve_all=True)['floatingips'])

    servers = nova.servers.list()

    deploying_simulation_instances = Instance.objects.filter(status=Instance.Status.DEPLOYING.name)
    # build our own quotas and usages, because nova can not do this at the moment
    available_resources = get_available_resources(quotas, servers, deploying_simulation_instances, flavor_dict,
                                                  floating_ips)

    simulation = Simulation.objects.get(id=simulation_instance.simulation_id)
    simulation_flavor = flavor_dict[simulation.flavor]

    available_resources.cores -= simulation_flavor.vcpus
    # Here we actually do not know, how many of these instances will have a floating ip assigned,
    # so to be safe we assume they will all have one
    available_resources.floating_ips -= 1
    available_resources.instances -= 1
    available_resources.ram -= simulation_flavor.ram

    # Configure logging in the future
    # logging.debug(str(available_resources))

    return available_resources.cores >= 0 \
           and available_resources.floating_ips >= 0 \
           and available_resources.instances >= 0 \
           and available_resources.ram >= 0


def get_solver_config():
    # Value for each solver consist of a tuple. The first tuple object is the dependency
    # of the solver, the second one is the command with which we run the simulation using the selected solver.
    return {
        "openfoam.pimplefoam":
            (["eu.mikelangelo-project.openfoam.pimplefoam"], "pimpleFoam.so"),
        "openfoam.pisofoam":
            (["eu.mikelangelo-project.openfoam.pisofoam"], "pisoFoam.so"),
        "openfoam.poroussimplefoam":
            (["eu.mikelangelo-project.openfoam.poroussimplefoam"], "poroussimpleFoam.so"),
        "openfoam.potentialfoam":
            (["eu.mikelangelo-project.openfoam.potentialfoam"], "potentialFoam.so"),
        "openfoam.rhoporoussimplefoam":
            (["eu.mikelangelo-project.openfoam.rhoporoussimplefoam"], "rhoporoussimpleFoam.so"),
        "openfoam.rhosimplefoam":
            (["eu.mikelangelo-project.openfoam.rhosimplefoam"], "rhosimpleFoam.so"),
        "openfoam.simplefoam":
            (["eu.mikelangelo-project.openfoam.simplefoam"], "simpleFoam.so")
    }


def get_common_deps():
    return [
        "eu.mikelangelo-project.osv.cli",
        "eu.mikelangelo-project.osv.nfs"
    ]


def get_available_resources(quotas_set, servers_list, deploying_simulation_instances, flavor_dict, floating_ips):
    """Returns a quota set containing only available resources.

    :param quotas_set: a set containing quota data. Should at least contain fields: 'cores', 'floating_ips',
    'instances', 'ram' and 'security_groups'
    :type quotas_set: Set
    :param servers_list: a list of running nova servers
    :type servers_list: List
    :param deploying_simulation_instances: List of Instance models representing simulation instances currently being
    deployed
    :type deploying_simulation_instances: List
    :param flavor_dict: a dictionary of available nova flavors. Keys in the dict must be flavor_ids, values
    must be flavor objects
    :type flavor_dict: dict
    :param floating_ips: a list of used floating ips as returned from nova
    :type floating_ips: List
    :return: Quota set of remaining resources
    """

    for server in servers_list:
        server_flavor = flavor_dict[server.flavor['id']]

        quotas_set.cores -= server_flavor.vcpus
        quotas_set.instances -= 1
        quotas_set.ram -= server_flavor.ram
        quotas_set.security_groups -= len(server.security_groups)

    quotas_set.floating_ips -= len(floating_ips)

    for simulation_instance in deploying_simulation_instances:
        simulation = Simulation.objects.get(id=simulation_instance.simulation_id)
        # instance_num = len(Instance.objects.filter(simulation_id=simulation.id))
        simulation_flavor = flavor_dict[simulation.flavor]

        quotas_set.cores -= simulation_flavor.vcpus
        # Here we actually do not know, how many of these instances will have a floating ip assigned,
        # so to be safe we assume they will all have one
        quotas_set.floating_ips -= 1
        quotas_set.instances -= 1
        quotas_set.ram -= simulation_flavor.ram
        # quotas_set.security_groups -= server.security_groups

    return quotas_set


def authenticate():
    # Authenticate using ENV variables
    auth = v2.Password(
        auth_url=env['OS_AUTH_URL'],
        username=env['OS_USERNAME'],
        password=env['OS_PASSWORD'],
        tenant_id=env['OS_TENANT_ID'])
    # Open auth session
    sess = session.Session(auth=auth)
    return sess


def __import_image_into_glance(glance_client, image_name, simulation, capstan_package_folder):
    # Import image into Glance
    mpm_image = os.path.expanduser(os.path.join("~", ".capstan", "repository",
                                                image_name, "%s.qemu" % (os.path.basename(capstan_package_folder))))
    unique_image_name = simulation.image + '_' + str(simulation.id)
    print "Uploading image %s to Glance" % unique_image_name
    image = glance_client.images.create(name=unique_image_name, disk_format="qcow2", container_format="bare")
    glance_client.images.upload(image.id, open(mpm_image, 'rb'))
    return image, unique_image_name


def __init_and_compose_capstan_package(simulation, capstan_package_folder, solver_deps):
    # Initialise MPM package
    cmd = ["capstan", "package", "init",
           "--name", simulation.simulation_name,
           "--title", simulation.simulation_name,
           "--author", env['OS_TENANT_NAME']]
    # We have to include the required packages in the command.
    deps = solver_deps + get_common_deps()
    for d in deps:
        cmd.append("--require")
        cmd.append(d)

    # Initialise MPM package at the given path.
    cmd.append(capstan_package_folder)
    # Invoke capstan tool.
    p = Popen(cmd)
    p.wait()
    os.chdir(capstan_package_folder)
    image_name = "temp/%s" % (os.path.basename(capstan_package_folder))
    # Now we are ready to compose the package into a VM
    p = Popen([
        "capstan", "package", "compose",
        "--size", "500M",
        "--run", "--redirect=/case/run.log /cli/cli.so",
        "--pull-missing",
        image_name])
    # Wait for the image to be built.
    p.wait()
    return image_name


def __create_local_temp_folders(simulation):
    # Connect to s3
    s3_conn = boto.connect_s3(
        aws_access_key_id=settings.S3_ACCESS_KEY_ID,
        aws_secret_access_key=settings.S3_SECRET_ACCESS_KEY,
        host=settings.S3_HOST,
        port=settings.S3_PORT,
        calling_format=boto.s3.connection.OrdinaryCallingFormat(),
    )
    capstan_package_folder = tempfile.mkdtemp(prefix='ofcloud-capstan-')
    case_folder = tempfile.mkdtemp(prefix='ofcloud-case-')
    case_path = path.join(case_folder, "case")
    os.makedirs(case_path)
    # Get the bucket for the input data.
    bucket = s3_conn.get_bucket(simulation.container_name)
    # Get the key from the bucket.
    input_key = bucket.get_key(simulation.input_data_object)
    casefile = path.join(case_path, os.path.basename(simulation.input_data_object))

    input_key.get_contents_to_filename(casefile)
    # Unpack the input case.
    tar = tarfile.open(casefile, 'r')
    tar.extractall(case_path)
    tar.close()
    # Remove the downloaded file
    os.remove(casefile)
    return capstan_package_folder, case_folder


def __copy_instance_case_files(case_folder, simulation_instance):
    local_nfs_mount_location = settings.LOCAL_NFS_MOUNT_LOCATION
    nfs_mount_folder = settings.NFS_SERVER_MOUNT_FOLDER

    local_instance_files_location = "%s/%s/" % (local_nfs_mount_location, str(simulation_instance.id))

    if os.path.exists(local_instance_files_location):
        shutil.rmtree(local_instance_files_location)

    shutil.copytree(src=case_folder, dst=local_instance_files_location)

    # Save storage information to model
    simulation_instance.local_case_location = '%s/case' % local_instance_files_location
    simulation_instance.nfs_case_location = '%s/%s/case' % (nfs_mount_folder, str(simulation_instance.id))
    simulation_instance.save()

    # Delete temporary case data
    shutil.rmtree(case_folder)


def __mount_instance_case_folder(instance_api, nfs_ip, simulation_instance, simulation_instance_case_folder):
    nfs_mount = 'nfs://%s%s %s' % (nfs_ip, simulation_instance.nfs_case_location, simulation_instance_case_folder)
    print "\t\tmounting network file storage with %s" % nfs_mount
    mount_command = "/tools/mount-nfs.so %s" % nfs_mount
    requests.put(
        "%s/app" % instance_api,
        data={"command": mount_command}
    )


def __get_nova_client():
    return nvclient.Client("2", session=authenticate())


def __get_neutron_client():
    return neutron_client.Client(session=authenticate())


def __build_flavor_dict(flavor_list):
    """Returns a dictionary of flavors. Key - flavor id, value - flavor object.

    :param flavor_list: a list of flavors as returned from nova client.
    :type flavor_list: list
    :return: Dictionary containing flavors. Key - flavor id, value - flavor object
    """

    flavor_dict = {}

    for flavor in flavor_list:
        flavor_dict[flavor.id] = flavor

    return flavor_dict


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
