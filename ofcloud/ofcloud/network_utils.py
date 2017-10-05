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

from django.conf import settings
from keystoneauth1 import session
from keystoneauth1.identity import v2
from neutronclient.v2_0 import client as ntclient


def get_openfoam_network_id():
    neutron = __get_neutron_client()
    network_name = settings.OPENFOAM_NETWORK_PREFIX + "_network"
    networks = __get_openfoam_network(neutron, network_name)

    networks_found = len(networks)
    if networks_found == 1:
        return networks[0]['id']
    else:
        raise RuntimeError("%d networks with \'%s\' name found. There should be only one" % networks_found,
                           network_name)


def setup_openfoam_network():
    neutron = __get_neutron_client()

    network_prefix = settings.OPENFOAM_NETWORK_PREFIX
    router_name = network_prefix + "_router"
    network_name = network_prefix + "_network"
    subnet_name = network_prefix + "_subnet"

    network_cidr = settings.OPENFOAM_NETWORK_CIDR
    allocation_pool_start = settings.OPENFOAM_NETWORK_ALLOCATION_POOL_START
    allocation_pool_end = settings.OPENFOAM_NETWORK_ALLOCATION_POOL_END
    gateway_ip = settings.OPENFOAM_NETWORK_GATEWAY_IP

    # get or create network and subnet
    network_id = __get_or_create_openfoam_network(neutron=neutron, network_name=network_name)
    subnet_id, is_new_network = __get_or_create_openfoam_subnet(neutron=neutron,
                                                                network_id=network_id,
                                                                subnet_name=subnet_name,
                                                                subnet_cidr=network_cidr,
                                                                allocation_pool_start=allocation_pool_start,
                                                                allocation_pool_end=allocation_pool_end,
                                                                gateway_ip=gateway_ip)

    if is_new_network:
        router_id = __get_or_create_openfoam_router(neutron=neutron, router_name=router_name)
        __add_router_interface(neutron=neutron, router_id=router_id, subnet_id=subnet_id)

    return network_id


def __get_or_create_openfoam_router(neutron, router_name):
    routers = neutron.list_routers(name=router_name)['routers']

    if len(routers) > 0:
        return routers[0]['id']
    else:
        public_networks = __get_public_networks(neutron)
        public_network = public_networks[0]
        create_router_request = {
            'router':
                {
                    'name': router_name,
                    'admin_state_up': True,
                    'tenant_id': env['OS_TENANT_ID'],
                    'external_gateway_info': {
                        'network_id': public_network['id']
                    }
                }
        }
        router = neutron.create_router(create_router_request)
        router_id = router['router']['id']
        return router_id


def __get_openfoam_network(neutron, network_name):
    networks = neutron.list_networks(name=network_name)
    return networks['networks']


def __get_or_create_openfoam_network(neutron, network_name):
    networks = __get_openfoam_network(neutron, network_name)
    networks_found = len(networks)

    if networks_found == 1:
        return networks[0]["id"]
    elif networks_found == 0:
        network_body = {
            "network": {
                "name": network_name,
                "admin_state_up": True,
                "tenant_id": env['OS_TENANT_ID']
            }
        }
        network = neutron.create_network(body=network_body)
        return network['network']['id']
    else:
        raise RuntimeError("Multiple networks with name \'%s\' found" % network_name)


def __get_or_create_openfoam_subnet(
        neutron,
        network_id,
        subnet_name,
        subnet_cidr,
        allocation_pool_start,
        allocation_pool_end,
        gateway_ip):
    subnets = neutron.list_subnets(name=subnet_name)['subnets']

    if len(subnets) > 0:
        subnet_id = subnets[0]["id"]
        is_new_network = False
    else:
        subnet_body = {
            'subnet': {
                'name': subnet_name,
                'enable_dhcp': True,
                'network_id': network_id,
                'tenant_id': env['OS_TENANT_ID'],
                'allocation_pools': [
                    {
                        'start': allocation_pool_start,
                        'end': allocation_pool_end
                    }
                ],
                'gateway_ip': gateway_ip,
                'ip_version': 4,
                'cidr': subnet_cidr
            }
        }
        subnet = neutron.create_subnet(body=subnet_body)
        subnet_id = subnet['subnet']['id']
        is_new_network = True
    return subnet_id, is_new_network


def __add_router_interface(neutron, router_id, subnet_id):
    add_interface_router_body = {
        'subnet_id': subnet_id
    }
    router_interface = neutron.add_interface_router(router=router_id, body=add_interface_router_body)
    return router_interface


def __get_public_networks(neutron):
    neutron_repsonse = neutron.list_networks()
    return filter(lambda x: x["router:external"] == True, neutron_repsonse["networks"])


def __get_neutron_client():
    auth = v2.Password(
        auth_url=env['OS_AUTH_URL'],
        username=env['OS_USERNAME'],
        password=env['OS_PASSWORD'],
        tenant_id=env['OS_TENANT_ID'])
    # Open auth session
    sess = session.Session(auth=auth)

    # Authenticate against required services
    return ntclient.Client(session=sess)
