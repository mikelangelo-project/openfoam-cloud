import json

from rest_framework import viewsets, status
from rest_framework.response import Response

from ofcloud.models import Simulation, Instance
from ofcloud.serializers import SimulationSerializer, InstanceSerializer
from ofcloud.utils import launch_simulation, destroy_simulation


class SimulationViewSet(viewsets.ModelViewSet):
    queryset = Simulation.objects.all()
    serializer_class = SimulationSerializer

    def create(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        simulation = serializer.save()
        headers = self.get_success_headers(serializer.data)

        try:
            cases = json.loads(serializer.data['cases'])
        except:
            cases = [{"name": serializer.data['simulation_name'], "updates": {}}]

        simulation_config = {
            "project_name": serializer.data['simulation_name'],
            "image": serializer.data['image'],
            "flavor": serializer.data['flavor'],
            "solver": serializer.data['solver'],
            "instance_count": serializer.data['instance_count'],
            "container": serializer.data['container_name'],
            "input_case": serializer.data['input_data_object'],
            "cases": cases
        }

        try:
            instances = launch_simulation(simulation_config)
            for instance in instances:
                simulation.instance_set.create(name=instance['name'],
                                               config=instance['config'],
                                               ip=instance['ip'],
                                               instance_id=instance['instance_id'],
                                               snap_task_id=instance['snap_task_id'])

            return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
        except KeyError:
            return Response(serializer.data, status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, pk=None):
        simulation = self.get_object()

        destroy_simulation(simulation)

        self.perform_destroy(simulation)

        return Response(status=status.HTTP_204_NO_CONTENT)


class InstanceViewSet(viewsets.ModelViewSet):
    queryset = Instance.objects.all()
    serializer_class = InstanceSerializer
