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
import time
import traceback
from os import environ as env

import glanceclient.v2.client as glclient
import novaclient.client as nvclient
from keystoneauth1 import session
from keystoneauth1.identity import v2

from ofcloud import network_utils
from ofcloud import openstack_utils
from ofcloud.models import Instance, Simulation
from provider import Provider


class OpenstackProvider(Provider):
    def __init__(self, provider_id, provider_config):
        # TODO validation, raise errors if properties missing from config
        super(OpenstackProvider, self).__init__(provider_id, provider_config)

    def prepare_instance(self, launch_dto):
        sess = self.__authenticate()

        # Authenticate against required services
        glance_client = glclient.Client(session=sess)
        nova_client = nvclient.Client("2", session=sess)

        # TODO see if already there, import build and import if necessary
        image, unique_image_name = self.__import_image_into_glance(
            glance_client,
            launch_dto.image_name,
            launch_dto.simulation_instance.simulation,
            launch_dto.capstan_package_folder)

        # Get data for the new server we are about to create.
        of_image = nova_client.images.get(image.id)

        flavor = nova_client.flavors.find(id=launch_dto.simulation_instance.simulation.flavor)

        unique_server_name = '%s-%s' % (
            launch_dto.simulation_instance.name, str(launch_dto.simulation_instance.id))

        print "Creating required instance %s" % unique_server_name

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

        launch_dto.simulation_instance.instance_id = nova_server_list[0].id
        launch_dto.unique_server_name = unique_server_name

        # Wait for the instance to become active
        while True:
            nova_server = nova_client.servers.get(launch_dto.simulation_instance.instance_id)

            if nova_server.status == 'ACTIVE':
                launch_dto.simulation_instance.status = Instance.Status.UP.name
                launch_dto.simulation_instance.instance_id = nova_server.id
                launch_dto.simulation_instance.save()
                break
            time.sleep(0.5)

        # Remove the uploaded image as it is no longer required
        glance_client.images.delete(image.id)

        # should return something like an address (in nova case this would be the floating ip), and associate
        # that with an instance
        print "Associating floating IPs"
        nova_server = nova_client.servers.get(launch_dto.simulation_instance.instance_id)
        floating_ip = self.__get_floating_ip(nova_client)
        nova_server.add_floating_ip(floating_ip.ip)

        launch_dto.simulation_instance.ip = floating_ip.ip
        launch_dto.simulation_instance.save()

        print "\tInstance %s accessible at %s" % (nova_server.name, floating_ip.ip)

        print "Wait 5s for the router to setup floating IPs"
        time.sleep(5)

    def is_simulation_instance_runnable(self, simulation_instance):
        """
        Checks whether the simulation can be run at this moment.

        :param simulation_instance: instance object
        :type simulation_instance: Instance object ofcloud.models.Instance
        :return: Boolean
        """

        print "Checking if instance is runnable on OPENSTACK/NOVA"
        # get nova client
        nova = openstack_utils.get_nova_client()
        neutron = openstack_utils.get_neutron_client()

        # get required data
        flavor_dict = openstack_utils.build_flavor_dict(nova.flavors.list())

        floating_ips = filter(lambda f_ip: f_ip['fixed_ip_address'] is not None,
                              neutron.list_floatingips(retrieve_all=True)['floatingips'])

        deploying_simulation_instances = Instance.objects.filter(status=Instance.Status.DEPLOYING.name,
                                                                 provider=self.id)
        simulation = Simulation.objects.get(id=simulation_instance.simulation_id)
        simulation_flavor = flavor_dict[simulation.flavor]

        servers = nova.servers.list()
        total_quotas = nova.quotas.get(tenant_id=env['OS_TENANT_ID'])

        # Check which limits are stricter, and use those
        total_quotas.cores = min(self.max_cpu_usage, total_quotas.cores)
        total_quotas.instances = min(self.max_instance_usage, total_quotas.instances)

        # build our own quotas and usages, because nova can not do this at the moment
        available_resources = openstack_utils.get_available_resources(total_quotas,
                                                                      servers,
                                                                      deploying_simulation_instances,
                                                                      flavor_dict,
                                                                      floating_ips)

        available_resources.cores -= simulation_flavor.vcpus
        # Here we actually do not know, how many of these instances will have a floating ip assigned,
        # so to be safe we assume they will all have one
        available_resources.floating_ips -= 1
        available_resources.instances -= 1
        available_resources.ram -= simulation_flavor.ram

        # Configure logging in the future
        # logging.debug(str(available_resources))

        return \
            available_resources.cores >= 0 \
            and available_resources.floating_ips >= 0 \
            and available_resources.instances >= 0 \
            and available_resources.ram >= 0

    def get_running_server_ids(self):
        nova = openstack_utils.get_nova_client()
        nova_server_ids = {nova_server.id: True for nova_server in nova.servers.list()}
        return nova_server_ids

    def shutdown_instances(self, instances):
        """
        Shuts down nova servers with provided ids.

        :param instances: A list of instances
        :return:
        """
        nova = openstack_utils.get_nova_client()

        for instance in instances:
            try:
                print "Shutting down instances with ids %s" % str(instance.instance_id)
                server = nova.servers.get(instance.instance_id)
                nova.servers.delete(server.id)
            except:
                print "Could not shutdown nova server %s" % instance.instance_id
                print traceback.format_exc()

    def get_instance_cpus(self, instance_simulation):
        """
        Returns number of cpus this simulation instance will have/does have

        :param instance_simulation: Instance simulation
        :return:
        """
        nova = openstack_utils.get_nova_client()

        try:
            return nova.flavors.get(instance_simulation.flavor).vcpus
        except:
            print "Could not get flavor VCPUs for flavor_id %s, using single threaded mode" % instance_simulation.flavor
            return 1

    def __import_image_into_glance(self, glance_client, image_name, simulation, capstan_package_folder):
        # Import image into Glance
        mpm_image = os.path.expanduser(os.path.join("~", ".capstan", "repository",
                                                    image_name, "%s.qemu" % (os.path.basename(capstan_package_folder))))
        print str(mpm_image)
        print "Image name = %s" % str(image_name)
        print "Capstan package folder = %s" % str(capstan_package_folder)

        unique_image_name = simulation.image + '_' + str(simulation.id)
        print "Uploading image %s to Glance" % unique_image_name
        image = glance_client.images.create(name=unique_image_name, disk_format="qcow2", container_format="bare")
        glance_client.images.upload(image.id, open(mpm_image, 'rb'))
        return image, unique_image_name

    def __get_floating_ip(self, nova):
        # Find the first available floating IP
        for fip in nova.floating_ips.list():
            if fip.instance_id is None:
                return fip

        # If there was no available floating IP, create and return new
        return nova.floating_ips.create('external_network')

    def __authenticate(self):
        # Authenticate using ENV variables
        auth = v2.Password(
            auth_url=env['OS_AUTH_URL'],
            username=env['OS_USERNAME'],
            password=env['OS_PASSWORD'],
            tenant_id=env['OS_TENANT_ID'])
        # Open auth session
        sess = session.Session(auth=auth)
        return sess
