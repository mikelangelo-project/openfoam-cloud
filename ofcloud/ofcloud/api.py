import traceback

from rest_framework import viewsets, status
from rest_framework.response import Response

from ofcloud.models import Simulation, Instance
from ofcloud.serializers import SimulationSerializer, InstanceSerializer
from ofcloud.utils import launch_simulation, destroy_simulation, create_simulation


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

        # launch the saved simulation, this will in future be done by a scheduler
        try:
            launch_simulation(simulation)
            return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
        except:
            print traceback.format_exc()
            return Response(serializer.data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def destroy(self, request, pk=None):
        simulation = self.get_object()

        destroy_simulation(simulation)

        self.perform_destroy(simulation)

        return Response(status=status.HTTP_204_NO_CONTENT)


class InstanceViewSet(viewsets.ModelViewSet):
    queryset = Instance.objects.all()
    serializer_class = InstanceSerializer
