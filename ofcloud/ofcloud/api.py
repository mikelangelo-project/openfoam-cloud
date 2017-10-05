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


import traceback

from rest_framework import viewsets, status
from rest_framework.response import Response

from ofcloud.models import Simulation, Instance
from ofcloud.serializers import SimulationSerializer, InstanceSerializer
from ofcloud.utils import destroy_simulation, create_simulation


class SimulationViewSet(viewsets.ModelViewSet):
    queryset = Simulation.objects.all()
    serializer_class = SimulationSerializer

    def create(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # create and save simulation and instances to DB
        try:
            simulation = create_simulation(serializer)
            simulation.save()
            headers = self.get_success_headers(serializer.validated_data)
        except:
            print traceback.format_exc()
            return Response(serializer.data, status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, pk=None):
        simulation = self.get_object()

        destroy_simulation(simulation)

        self.perform_destroy(simulation)

        return Response(status=status.HTTP_204_NO_CONTENT)


class InstanceViewSet(viewsets.ModelViewSet):
    queryset = Instance.objects.all()
    serializer_class = InstanceSerializer
