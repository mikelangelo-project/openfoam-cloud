class ProviderLaunchDto:
    def __init__(self, simulation_instance, image_name, capstan_package_folder):
        self.simulation_instance = simulation_instance
        self.image_name = image_name
        self.capstan_package_folder = capstan_package_folder
        self.unique_server_name = None