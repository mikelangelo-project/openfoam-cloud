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


from os import environ as env

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

for nic in nova.networks.list():
    print nic.id + " " + nic.label
