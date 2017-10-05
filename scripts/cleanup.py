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


import glob
import os
import shutil
import tempfile
from os import environ as env

import glanceclient.v2.client as glclient
import novaclient.client as nvclient
from keystoneauth1 import session
from keystoneauth1.identity import v2

IMAGE = "openfoam.cases"
FLAVOR = "of.small"

# Authenticate using ENV variables
auth = v2.Password(
    auth_url=env['OS_AUTH_URL'],
    username=env['OS_USERNAME'],
    password=env['OS_PASSWORD'],
    tenant_id=env['OS_TENANT_ID'])
# Open auth session
sess = session.Session(auth=auth)

nova = nvclient.Client("2", session=sess)
glance = glclient.Client(session=sess)

for instance in nova.servers.list():
    print "Removing instance %s" % (instance.name)
    instance.delete()

for img in glance.images.list():
    if img.name.startswith("mik3d"):
        print "Removing image %s" % (img.name)
        glance.images.delete(img.id)

    # Do not remove floating IPs for now.
    # for fip in nova.floating_ips.list():
    # print "Removing floating ip %s" % fip.ip
    # nova.floating_ips.delete(fip)

os.chdir(tempfile.gettempdir())
for temp in glob.glob("ofcloud*"):
    print "Removing temp folder %s" % temp
    shutil.rmtree(temp)
