from django.conf import settings

from os import environ as env, path
import json
import os, os.path
import re
import subprocess
import tempfile
import tarfile
import time
import keystoneclient.v2_0.client as ksclient
import glanceclient.v2.client as glclient
import novaclient.client as nvclient
import swiftclient as swclient
import requests

from keystoneauth1.identity import v2
from keystoneauth1 import session

from snap import api as snap_api

import boto
import boto.s3.connection


def update_case(case_path, updates):
    input_files = {} 

    # First, get a list of files that need to be modified
    for key in updates:
        fileEndIndex = key.rfind('/')
        filepath = key[0:fileEndIndex]
        variable = key[fileEndIndex+1:]

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


def launch_simulation(config):
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
            aws_access_key_id = settings.S3_ACCESS_KEY_ID,
            aws_secret_access_key = settings.S3_SECRET_ACCESS_KEY,
            host = settings.S3_HOST,
            port = settings.S3_PORT,
            calling_format = boto.s3.connection.OrdinaryCallingFormat(),
            )

    temppath = tempfile.mkdtemp(prefix='ofcloud-')
    casepath = path.join(temppath, "case")

    os.makedirs(casepath)
    # with open(casefile, 'w') as f:
        # f.write(obj[1])

    # Get the bucket for the input data.
    bucket = s3_conn.get_bucket(config['container'])
    # Get the key from the bucket.
    input_key = bucket.get_key(config['input_case'])

    casefile = path.join(casepath, os.path.basename(config['input_case']))
    input_key.get_contents_to_filename(casefile)

    # Unpack the input case.
    tar = tarfile.open(casefile, 'r')
    tar.extractall(casepath)
    tar.close()

    # Remove the downloaded file
    os.remove(casefile)

    # Initialise MPM package
    cmd = ["capstan", "package", "init",
            "--name", config['project_name'],
            "--title", config['project_name'],
            "--author", env['OS_TENANT_NAME']]

    # We have to include the required packages in the command.
    for d in config['deps']:
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
        image_name])
    # Wait for the image to be built.
    p.wait()

    # Import image into Glance
    mpm_image = os.path.expanduser(os.path.join("~", ".capstan", "repository", 
        image_name, "%s.qemu" % (os.path.basename(temppath))))

    print "Uploading image %s to Glance" % (config['project_name'])
    image = glance.images.create(name=config['project_name'], disk_format="qcow2", container_format="bare")
    glance.images.upload(image.id, open(mpm_image, 'rb'))

    # Get data for the new server we are about to create.
    of_image = nova.images.find(name=config['project_name'])
    flavor = nova.flavors.find(id=config['flavor'])

    # Create a new instance
    server_count = len(config['cases']) if 'cases' in config else 1
    if server_count == 1:
        print "Creating required instance %s" % (config['project_name'])
    else:
        print "Creating required instances %s-1...%s-%d" % (config['project_name'], config['project_name'], server_count)

    nova.servers.create(name=config['project_name'], 
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

        for s in nova.servers.list(search_opts={'name': config['project_name']}):
            if s.status == 'BUILD':
                all_up = False
            elif s.status == 'ACTIVE':
                active_count = active_count + 1

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
    for instance in nova.servers.list(search_opts={'name': config['project_name']}):
        floating_ip = get_floating_ip(nova)
        instance.add_floating_ip(floating_ip)

        instance_ips[instance.id] = floating_ip.ip

        print "\tInstance %s accessible at %s" % (instance.name, floating_ip.ip)

    print "Wait 5s for the router to setup floating IPs"
    time.sleep(5)

    # print "Associating floating IPs"
    # rest_apis = {}
    # for instance in nova.servers.list(search_opts={'name': config['project_name']}):
        # # Since devstack has some issues with nova-network, we have to try this several times
        # prev_floating_ip = None
        # for i in range(0, 5):
            # floating_ip = get_floating_ip(nova)
            # instance.add_floating_ip(floating_ip)

            # if prev_floating_ip:
                # nova.floating_ips.delete(prev_floating_ip)
                # prev_floating_ip = None

            # api_url = "http://%s:8000" % (floating_ip.ip)

            # # Test the connection
            # try:
                # response = requests.get(url=api_url,
                        # timeout=(0.1, 10))

                # print "Instance %s accessible at %s" % (instance.name, floating_ip.ip)
                # rest_apis[instance.id] = api_url

                # break

            # except:
# #                 # Release floating IP
# #                 nova.floating_ips.delete(floating_ip)
                # prev_floating_ip = floating_ip

                # time.sleep(0.5)

    if len(instance_ips) != server_count:
        print "Some instances failed to obtain valid IP"
        # TODO: stop & cleanup

    instances = []

    print "Customising simulations"
    for idx, instance in enumerate(nova.servers.list(search_opts={'name': config['project_name']})):
        instance_api = rest_api_for(instance_ips[instance.id])
        print "\t%s" % instance.name

        # Request input case update given the provided customisations.
        modified_files = update_case(casepath, config['cases'][idx]['updates'])

        for srcfile, destfile in modified_files.iteritems():
            files = {'file': open(destfile, 'rb')}
            upload_url = '%s/file/case/%s' % (instance_api, srcfile)

            print '\t\tuploading file %s to %s' % (upload_url, destfile)

            requests.post(upload_url, files=files)

        print "\t\tsetting up the execution environment"

        # Now we need to setup some env variables.
        requests.post("%s/env/OPENFOAM_CASE" % instance_api, 
                data={ "val": '%s-%s' % (config['project_name'], config['cases'][idx]['name']) })
        requests.post("%s/env/TENANT" % instance_api, data={ "val": env['OS_TENANT_NAME'] })
        requests.post("%s/env/WM_PROJECT_DIR" % instance_api, data={ "val": '/openfoam' })

        print "Starting snap collector"
        t = snap_api.create_openfoam_task(instance_ips[instance.id])
        print "\ttask id %s" % t

        instances.append({
            'name': '%s-%s' % (config['project_name'], config['cases'][idx]['name']),
            'config': json.dumps(config['cases'][idx]['updates']),
            'ip': instance_ips[instance.id],
            'instance_id': instance.id,
            'snap_task_id': t
            })


    print "Starting OpenFOAM simulations"
    for idx, instance in enumerate(nova.servers.list(search_opts={'name': config['project_name']})):
        instance_api = rest_api_for(instance_ips[instance.id])

        requests.put("%s/app/" % instance_api, data={ "command": "/usr/bin/simpleFoam -case /case" })
    

    return instances


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
