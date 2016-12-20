from django.apps import AppConfig

from ofcloud import network_utils


class OfcloudAppConfig(AppConfig):
    name = 'ofcloud'
    verbose_name = 'OpenFOAM cloud application'

    def ready(self):
        network_utils.setup_openfoam_network()
