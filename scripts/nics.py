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
