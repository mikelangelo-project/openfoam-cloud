import json
import os
import os.path
import re
import subprocess
import tarfile
import tempfile
import time
import uuid
from os import environ as env, path

import boto
import boto.s3.connection
import glanceclient.v2.client as glclient
import keystoneclient.v2_0.client as ksclient
import novaclient.client as nvclient
import requests
from django.conf import settings
from keystoneauth1 import session
from keystoneauth1.identity import v2

from ofcloud.models import Instance
from snap import api as snap_api


def update_case(case_path, updates):
    input_files = {}

    # First, get a list of files that need to be modified
    for key in updates:
        fileEndIndex = key.rfind('/')
        filepath = key[0:fileEndIndex]
        variable = key[fileEndIndex + 1:]

        if not filepath in input_files:
            input_files[filepath] = {}

        input_files[filepath][variable] = updates[key]

    output_files = {}

    # Now loop through files and update them.
    for file, variables in input_files.iteritems():
        filepath = os.path.join(case_path, file)

        f = open(filepath, 'r')
        data = f.read()
        f.close()

        for var, value in variables.iteritems():
            data = re.sub(re.compile('^[ \t]*%s\s+.*$' % var, re.MULTILINE), '%s %s;' % (var, value), data)

        ofile = filepath + ".custom"
        output_files[file] = ofile

        f = open(ofile, 'w')
        f.write(data)
        f.close()

    return output_files


def get_floating_ip(nova):
    # Find the first available floating IP
    for fip in nova.floating_ips.list():
        if fip.instance_id == None:
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


def launch_simulation(simulation):
    # Authenticate using ENV variables
    auth = v2.Password(
        auth_url=env['OS_AUTH_URL'],
        username=env['OS_USERNAME'],
        password=env['OS_PASSWORD'],
        tenant_id=env['OS_TENANT_ID'])
    # Open auth session
    sess = session.Session(auth=auth)

    # Authenticate against required services
    keystone = ksclient.Client(session=sess)
    glance = glclient.Client(session=sess)
    nova = nvclient.Client("2", session=sess)
    # swift = swclient.Connection(
    # user=env['OS_USERNAME'],
    # key=env['OS_PASSWORD'],
    # authurl=env['OS_AUTH_URL'],
    # auth_version="2",
    # tenant_name=env['OS_TENANT_NAME'])

    # # Try to download the given input case from Swift.
    # obj = swift.get_object(config['container'], config['input_case'])

    s3_conn = boto.connect_s3(
        aws_access_key_id=settings.S3_ACCESS_KEY_ID,
        aws_secret_access_key=settings.S3_SECRET_ACCESS_KEY,
        host=settings.S3_HOST,
        port=settings.S3_PORT,
        calling_format=boto.s3.connection.OrdinaryCallingFormat(),
    )

    temppath = tempfile.mkdtemp(prefix='ofcloud-')
    casepath = path.join(temppath, "case")

    os.makedirs(casepath)
    # with open(casefile, 'w') as f:
    # f.write(obj[1])

    # Get the bucket for the input data.
    bucket = s3_conn.get_bucket(simulation.container_name)
    # Get the key from the bucket.
    input_key = bucket.get_key(simulation.input_data_object)

    casefile = path.join(casepath, os.path.basename(simulation.input_data_object))
    input_key.get_contents_to_filename(casefile)

    # Unpack the input case.
    tar = tarfile.open(casefile, 'r')
    tar.extractall(casepath)
    tar.close()

    # Remove the downloaded file
    os.remove(casefile)

    # Initialise MPM package
    cmd = ["capstan", "package", "init",
           "--name", simulation.simulation_name,
           "--title", simulation.simulation_name,
           "--author", env['OS_TENANT_NAME']]

    # We have to include the required packages in the command.
    solver_deps, solver_so = get_solver_config()[simulation.solver]
    deps = solver_deps + get_common_deps()

    for d in deps:
        cmd.append("--require")
        cmd.append(d)

    # Initialise MPM package at the given path.
    cmd.append(temppath)

    # Invoke capstan tool.
    p = subprocess.Popen(cmd)
    p.wait()

    os.chdir(temppath)

    image_name = "temp/%s" % (os.path.basename(temppath))
    # Now we are ready to compose the package into a VM
    p = subprocess.Popen([
        "capstan", "package", "compose",
        "--size", "500M",
        "--run", "--redirect=/case/run.log /cli/cli.so",
        "--pull-missing",
        image_name])
    # Wait for the image to be built.
    p.wait()

    # Import image into Glance
    mpm_image = os.path.expanduser(os.path.join("~", ".capstan", "repository",
                                                image_name, "%s.qemu" % (os.path.basename(temppath))))

    unique_image_name = __generate_unique_name(simulation.image)
    print "Uploading image %s to Glance" % unique_image_name
    image = glance.images.create(name=unique_image_name, disk_format="qcow2", container_format="bare")
    glance.images.upload(image.id, open(mpm_image, 'rb'))

    # Get data for the new server we are about to create.
    of_image = nova.images.find(name=unique_image_name)
    flavor = nova.flavors.find(id=simulation.flavor)

    simulation_instances = simulation.instance_set.all()

    unique_server_name = __generate_unique_name(simulation.simulation_name)

    server_count = len(simulation_instances)
    if server_count == 1:
        print "Creating required instance %s" % unique_server_name
    else:
        print "Creating required instances %s-1...%s-%d" % (
            unique_server_name, unique_server_name, server_count)

    nova.servers.create(name=unique_server_name,
                        image=of_image,
                        flavor=flavor,
                        min_count=server_count,
                        max_count=server_count
                        )

    # Ensure that all required instances are active.
    active_count = 0
    while True:
        all_up = True
        active_count = 0

        for s in nova.servers.list(search_opts={'name': unique_server_name}):
            if s.status == 'BUILD':
                all_up = False
            elif s.status == 'ACTIVE':
                active_count += 1

        if all_up:
            break

        time.sleep(0.5)

    if active_count == server_count:
        print "All instances up and running"
    else:
        print "Some instances failed to boot"
        # TODO: stop & cleanup

    # Remove the uploaded image as it is no longer required
    glance.images.delete(image.id)

    print "Associating floating IPs"
    instance_ips = {}
    nova_servers_list = nova.servers.list(search_opts={'name': unique_server_name})

    if len(nova_servers_list) != len(simulation_instances):
        print "Configured instance number and nova created instance number differ!"
        # exception maybe ?

    for instance in nova_servers_list:
        floating_ip = get_floating_ip(nova)
        instance.add_floating_ip(floating_ip)

        instance_ips[instance.id] = floating_ip.ip

        print "\tInstance %s accessible at %s" % (instance.name, floating_ip.ip)

    print "Wait 5s for the router to setup floating IPs"
    time.sleep(5)

    if len(instance_ips) != server_count:
        print "Some instances failed to obtain valid IP"
        # TODO: stop & cleanup

    simulation_cases = json.loads(simulation.cases)
    print "Customising simulations"
    for idx, instance in enumerate(nova_servers_list):
        instance_api = rest_api_for(instance_ips[instance.id])
        print "\t%s" % instance.name

        # Request input case update given the provided customisations.
        simulation_case = simulation_cases[idx]
        modified_files = update_case(casepath, simulation_case['updates'])

        for srcfile, destfile in modified_files.iteritems():
            files = {'file': open(destfile, 'rb')}
            upload_url = '%s/file/case/%s' % (instance_api, srcfile)

            print '\t\tuploading file %s to %s' % (upload_url, destfile)

            requests.post(upload_url, files=files)

        print "\t\tsetting up the execution environment"

        # Now we need to setup some env variables.
        requests.post("%s/env/OPENFOAM_CASE" % instance_api,
                      data={"val": '%s-%s' % (unique_server_name, simulation_case['name'])})
        requests.post("%s/env/TENANT" % instance_api, data={"val": env['OS_TENANT_NAME']})
        requests.post("%s/env/WM_PROJECT_DIR" % instance_api, data={"val": '/openfoam'})

        print "Starting snap collector"
        t = snap_api.create_openfoam_task(instance_ips[instance.id])
        print "\ttask id %s" % t

        simulation_instance = simulation_instances[idx]
        simulation_instance.name = '%s-%s' % (unique_server_name, simulation_case['name'])
        simulation_instance.config = json.dumps(simulation_case['updates'])
        simulation_instance.ip = instance_ips[instance.id]
        simulation_instance.instance_id = instance.id
        simulation_instance.snap_task_id = t
        simulation_instance.status = Instance.Status.UP.name
        simulation_instance.save()

    print "Starting OpenFOAM simulations"
    solver_command = "/usr/bin/%s -case /case" % solver_so
    for idx, instance in enumerate(nova.servers.list(search_opts={'name': unique_server_name})):
        instance_api = rest_api_for(instance_ips[instance.id])

        requests.put("%s/app/" % instance_api, data={"command": solver_command})

        simulation_instances[idx].status = Instance.Status.RUNNING.name
        simulation_instances[idx].save()

    return simulation_instances


def destroy_simulation(simulation):
    # Authenticate using ENV variables
    auth = v2.Password(
        auth_url=env['OS_AUTH_URL'],
        username=env['OS_USERNAME'],
        password=env['OS_PASSWORD'],
        tenant_id=env['OS_TENANT_ID'])
    # Open auth session
    sess = session.Session(auth=auth)

    # Authenticate against required services
    nova = nvclient.Client("2", session=sess)

    for instance in simulation.instance_set.all():
        try:
            server = nova.servers.get(instance.instance_id)
            nova.servers.delete(server)

            snap_api.stop_openfoam_task(instance.snap_task_id)
        except:
            print "Instance not found"


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
        "eu.mikelangelo-project.osv.cli"
    ]


def __generate_unique_name(name):
    return name + '-' + str(uuid.uuid4())
