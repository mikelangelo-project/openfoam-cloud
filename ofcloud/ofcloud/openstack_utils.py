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

import neutronclient.v2_0.client as neutron_client
import novaclient.client as nvclient
import glanceclient.v2.client as glclient
from keystoneauth1 import session
from keystoneauth1.identity import v2

from models import Simulation


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


def get_nova_client():
    return nvclient.Client("2", session=authenticate())


def get_neutron_client():
    return neutron_client.Client(session=authenticate())


def get_glance_client():
    return glclient.Client(session=authenticate())


def get_available_resources(quotas_set, servers_list, deploying_simulation_instances, flavor_dict, floating_ips):
    """
    Returns a quota set containing only available resources.

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

    return quotas_set


def build_flavor_dict(flavor_list):
    """
    Returns a dictionary of flavors. Key - flavor id, value - flavor object.

    :param flavor_list: a list of flavors as returned from nova client.
    :type flavor_list: list
    :return: Dictionary containing flavors. Key - flavor id, value - flavor object
    """

    flavor_dict = {}

    for flavor in flavor_list:
        flavor_dict[flavor.id] = flavor

    return flavor_dict
