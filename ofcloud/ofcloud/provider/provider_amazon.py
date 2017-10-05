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


import time

import boto.ec2

from ofcloud.models import Instance
from provider import Provider


class AmazonProvider(Provider):
    AMI_ID = 'ami-114ef271'
    INSTANCE_TYPE = 't2.small'
    INSTANCE_CPUS = 1
    SECURITY_GROUPS = ["All Open"]

    def __init__(self, provider_id, provider_config):
        super(AmazonProvider, self).__init__(provider_id, provider_config)
        self.region = provider_config.get('REGION')

    def prepare_instance(self, launch_dto):
        client = boto.ec2.connect_to_region(self.region)

        # res = client.run_instances(AMI_ID, instance_type=INSTANCE_TYPE, security_groups=SECURITY_GROUPS)
        res = client.run_instances(self.AMI_ID, instance_type=self.INSTANCE_TYPE, security_groups=self.SECURITY_GROUPS)
        instance = res.instances[0]
        self.__wait_for(instance, 'running')

        instance.add_tags({"Name": "simpleFoam", "Type": "simpleFoam"})

        # TODO try using IP
        print "Amazon instance IP = %s" % instance.ip_address

        launch_dto.simulation_instance.instance_id = instance.id
        launch_dto.simulation_instance.ip = instance.ip_address
        launch_dto.unique_server_name = self.AMI_ID
        return launch_dto

    def is_simulation_instance_runnable(self, simulation_instance):
        # TODO we currently only check if there is space for one more, hence we actually do not need any info from the
        # instance itself, as it does not use nova flavors. When we will choose amazon flavors, then we have to take
        # those into account
        print "Checking if instance is runnable on %s" % self.id

        deploying_simulation_instances = len(
            Instance.objects.filter(status=Instance.Status.DEPLOYING.name, strategy=self.id))

        up_simulation_instances = len(
            Instance.objects.filter(status=Instance.Status.UP.name, strategy=self.id))

        running_simulation_instances = len(
            Instance.objects.filter(status=Instance.Status.RUNNING.name, strategy=self.id))

        amazon_simulation_instances = \
            deploying_simulation_instances + up_simulation_instances + running_simulation_instances

        return amazon_simulation_instances < self.max_instance_usage

    def get_running_server_ids(self):
        server_ids = {}

        conn = boto.ec2.connect_to_region(self.region)
        of_instances_running = conn.get_only_instances(
            filters={"tag:type": "simpleFoam", "instance-state-code": 16})
        of_instances_pending = conn.get_only_instances(
            filters={"tag:type": "simpleFoam", "instance-state-code": 0})

        of_instances = of_instances_pending + of_instances_running
        for instance in of_instances:
            server_ids[instance.id] = True

        return server_ids

    def shutdown_instances(self, instances):
        """
        Shuts down nova servers with provided ids.

        :param instances: A list of instances
        :return:
        """
        running_server_ids = self.get_running_server_ids()
        server_ids = [instance.instance_id for instance in instances if instance.instance_id in running_server_ids]
        if len(server_ids):
            try:
                conn = boto.ec2.connect_to_region(self.region)
                conn.terminate_instances(server_ids)
            except Exception as ex:
                print "Failed shutting down instances %s, msg: %s" % (instances, ex.message)

    def get_instance_cpus(self, instance_simulation):
        """
        Returns number of cpus this simulation instance will have/does have

        :param instance_simulation: Instance simulation
        :return:
        """
        return self.INSTANCE_CPUS

    def __wait_for(self, ec2_obj, status='available'):
        while ec2_obj.state != status:
            time.sleep(1)
            ec2_obj.update()
