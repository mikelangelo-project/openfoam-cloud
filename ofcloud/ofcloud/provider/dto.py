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


class ProviderLaunchDto:
    def __init__(self, simulation_instance, image_name, capstan_package_folder):
        self.simulation_instance = simulation_instance
        self.image_name = image_name
        self.capstan_package_folder = capstan_package_folder
        self.unique_server_name = None