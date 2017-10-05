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


from django.conf import settings
from rest_framework import serializers

from ofcloud import models


class InstanceSerializer(serializers.ModelSerializer):
    grafana_url = serializers.SerializerMethodField()
    download_case_url = serializers.SerializerMethodField()

    class Meta:
        model = models.Instance
        fields = (
            'id',
            'name',
            'config',
            'ip',
            'instance_id',
            'provider',
            'simulation',
            'snap_task_id',
            'status',
            'local_case_location',
            'nfs_case_location',
            'retry_attempts',
            'grafana_url',
            'download_case_url'
        )

    def get_grafana_url(self, obj):
        return "%s/dashboard/db/snappy-openfoam?var-measurement=intel\/openfoam\/Ux\/initial&var-measurement=intel\/openfoam\/Uy\/initial&var-measurement=intel\/openfoam\/Uz\/initial&var-source=%s" % (
            settings.GRAFANA_BASENAME, obj.ip)

        # return 'http://10.211.55.101:3000/dashboard/db/openfoam?var-experiment=%s&var-parameter=Ux_0&var-parameter=Uy_0&var-parameter=Uz_0' % obj.name

    def get_download_case_url(self, obj):
        return '%s/ofcloud/instances/%s/download' % (settings.OPENFOAM_BASENAME, obj.id)


class SimulationSerializer(serializers.ModelSerializer):
    instances = InstanceSerializer(many=True, read_only=True, source='instance_set')

    class Meta:
        model = models.Simulation
        fields = (
            'id',
            'simulation_name',
            'image',
            'flavor',
            'solver',
            'instance_count',
            'container_name',
            'input_data_object',
            'cases',
            'status',
            'instances',
            'decomposition'
        )
