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


import requests
from django.conf import settings


def create_openfoam_task(target_ip):
    task_manifest = {
        "version": 1,
        "schedule": {
            "type": "simple",
            "interval": "10s"
        },
        "max-failures": 30,
        "workflow": {
            "collect": {
                "metrics": {
                    "/intel/openfoam/Ux/final": {},
                    "/intel/openfoam/Ux/initial": {},
                    "/intel/openfoam/Uz/final": {},
                    "/intel/openfoam/Uz/initial": {},
                    "/intel/openfoam/p/final": {},
                    "/intel/openfoam/p/initial": {},
                    "/intel/openfoam/Uy/final": {},
                    "/intel/openfoam/Uy/initial": {}
                },
                "config": {
                    "/intel": {
                        "webServerIP": target_ip,
                        "webServerPort": 8000,
                        "webServerFilePath": "file/run.log?op=GET",
                        "timeot": 20
                    }
                },
                "process": None,
                "publish": [
                    {
                        "plugin_name": "influxdb",
                        "config": {
                            "host": settings.INFLUX_DB_HOST,
                            "port": settings.INFLUX_DB_PORT,
                            "database": settings.INFLUX_DB_NAME,
                            "user": settings.INFLUX_DB_USER,
                            "password": settings.INFLUX_DB_PASS
                        }

                    }
                ],
            }
        }
    }

    # Create the task
    r = requests.post(settings.SNAP_SERVICE + "tasks", json=task_manifest)
    if r.status_code >= 400:
        raise requests.RequestException("Error accessing Snap API, status_code = %s" % r.status_code, r.content)
    else:
        task_id = r.json()["body"]["id"]
        # Start the task
        r = requests.put(settings.SNAP_SERVICE + "tasks/%s/start" % task_id)
        return task_id


def stop_openfoam_task(task_id):
    # Stop the task
    r = requests.put(settings.SNAP_SERVICE + "tasks/%s/stop" % task_id)

    # Remove the task
    r = requests.delete(settings.SNAP_SERVICE + "tasks/%s" % task_id)

    return task_id
