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


import os
import os.path
import re
import subprocess
import tarfile
import tempfile
import time
from os import environ as env, path

import glanceclient.v2.client as glclient
import keystoneclient.v2_0.client as ksclient
import novaclient.client as nvclient
import requests
import swiftclient as swclient
from keystoneauth1 import session
from keystoneauth1.identity import v2

config = {
    "project_name": "mik3d_15min",
    "image": "openfoam.cases",
    "flavor": "of.small",

    "container": "inputs",
    "input_case": "mik3d_15min.tar.gz",

    "deps": [
        "eu.mikelangelo-project.openfoam.simplefoam",
        "eu.mikelangelo-project.openfoam.core",
        "eu.mikelangelo-project.osv.cli"
    ],

    "cases": [
        {"name": "mik3d_15min-angle_0", "updates": {'0/conditions/flowVelocity': '(20 0 0)', }, },
        {"name": "mik3d_15min-angle_2", "updates": {'0/conditions/flowVelocity': '(19.98782   0.00000 0.69799)', }, },
        # { "name": "mik3d_15min-angle_4", "updates": { '0/conditions/flowVelocity': '(19.95128   0.00000 1.39513)', }, },
        # { "name": "mik3d_15min-angle_10", "updates": { '0/conditions/flowVelocity': '(19.69616   0.00000 3.47296)', }, },
        # { "name": "mik3d_15min-angle_20", "updates": { '0/conditions/flowVelocity': '(18.79385   0.00000 6.84040)', }, },
        # { "name": "mik3d_15min-angle_-20", "updates": { '0/conditions/flowVelocity': '(18.79385   0.00000 -6.84040)', }, },
        # { "name": "mik3d_15min-angle_45", "updates": { '0/conditions/flowVelocity': '(14.14214  0.00000 14.14214)', }, },
    ]
}


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


def get_floating_ip():
    # Find the first available floating IP
    for fip in nova.floating_ips.list():
        if fip.instance_id == None:
            return fip

    # If there was no available floating IP, create and return new
    return nova.floating_ips.create('external_network')


if __name__ == "__main__":
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
    swift = swclient.Connection(
        user=env['OS_USERNAME'],
        key=env['OS_PASSWORD'],
        authurl=env['OS_AUTH_URL'],
        auth_version="2",
        tenant_name=env['OS_TENANT_NAME'])

    # Try to download the given input case from Swift.
    obj = swift.get_object(config['container'], config['input_case'])
    temppath = tempfile.mkdtemp(prefix='ofcloud-')
    casepath = path.join(temppath, "case")

    os.makedirs(casepath)
    casefile = path.join(casepath, config['input_case'])
    with open(casefile, 'w') as f:
        f.write(obj[1])

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
        "--cmd", "--redirect=/case/run.log /cli/cli.so",
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
    flavor = nova.flavors.find(name=config['flavor'])

    # Create a new instance
    server_count = len(config['cases']) if 'cases' in config else 1
    if server_count == 1:
        print "Creating required instance %s" % (config['project_name'])
    else:
        print "Creating required instances %s-1...%s-%d" % (
        config['project_name'], config['project_name'], server_count)

    nics = [{
        'net-id': 'a722fe23-0e73-43dd-a3fc-378d44ad9199',
        'v4-fixed-up': ''
    }]

    nova.servers.create(name=config['project_name'],
                        image=of_image,
                        flavor=flavor,
                        min_count=server_count,
                        max_count=server_count,
                        nics=nics)

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

    print "Associating floating IPs"
    rest_apis = {}
    for instance in nova.servers.list(search_opts={'name': config['project_name']}):
        floating_ip = get_floating_ip()
        instance.add_floating_ip(floating_ip)

        api_url = "http://%s:8000" % (floating_ip.ip)
        rest_apis[instance.id] = api_url

        # print api_url

        # # Test the connection
        # # try:
        # response = requests.get(api_url)

        # print "Instance %s accessible at %s" % (instance.name, floating_ip.ip)
        # rest_apis[instance.id] = api_url

        # break

        # # except:
        # # # Release floating IP
        # # nova.floating_ips.delete(floating_ip)

        # # time.sleep(0.5)

    print "Wait 5s for the router to setup floating IPs"
    time.sleep(5)

    if len(rest_apis) != server_count:
        print "Some instances failed to obtain valid IP"
        # TODO: stop & cleanup

    print "Customising simulations"
    for idx, instance in enumerate(nova.servers.list(search_opts={'name': config['project_name']})):
        instance_api = rest_apis[instance.id]
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
        requests.post("%s/env/OPENFOAM_CASE" % instance_api, data={"val": config['cases'][idx]['name']})
        requests.post("%s/env/TENANT" % instance_api, data={"val": env['OS_TENANT_NAME']})
        requests.post("%s/env/WM_PROJECT_DIR" % instance_api, data={"val": '/openfoam'})

    print "Staring OpenFOAM simulations"
    for idx, instance in enumerate(nova.servers.list(search_opts={'name': config['project_name']})):
        instance_api = rest_apis[instance.id]

        requests.put("%s/app/" % instance_api, data={"command": "/usr/bin/simpleFoam -case /case"})
