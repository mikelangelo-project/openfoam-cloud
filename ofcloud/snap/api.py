from django.conf import settings

import requests

def create_openfoam_task(target_ip):
    task_manifest = {
            "version": 1,
            "schedule": {
                "type": "simple",
                "interval": "10s"
                },
            "workflow": {
                "collect": {
                    "metrics": {
                        "/intel/openfoam/Ux/final": {},
                        "/intel/openfoam/Ux/initial": {},
                        "/intel/openfoam/Uz/final": {},
                        "/intel/openfoam/Uz/initial": {},
                        "/intel/openfoam/p/final": {},
                        "/intel/openfoam/p/initial": {},
                        "/intel/openfoam/k/final": {},
                        "/intel/openfoam/k/initial": {},
                        "/intel/openfoam/omega/final": {},
                        "/intel/openfoam/omega/initial": {},
                        "/intel/openfoam/Uy/final": {},
                        "/intel/openfoam/Uy/initial": {}
                        },
                    "config": {
                        "/intel": {
                            "swagIP": target_ip,
                            "swagPort": 8000,
                            "swagFile": "%2Fcase%2Frun.log?op=GET"
                            }
                        },
                    "process": [
                        {
                            "plugin_name": "passthru",
                            "plugin_version": 1,
                            "process": None,
                            "publish": [
                                {
                                    "plugin_name": "influx",
                                    "config": {
                                        "host": settings.INFLUX_DB_HOST,
                                        "port": settings.INFLUX_DB_PORT,
                                        "database": settings.INFLUX_DB_NAME,
                                        "user": settings.INFLUX_DB_USER,
                                        "password": settings.INFLUX_DB_PASS
                                        }

                                    }
                                ],
                            "config": None
                            }
                        ],
                    "publish": None
                    }
                }
            }

    # Create the task
    r = requests.post(settings.SNAP_SERVICE + "tasks", json=task_manifest)
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
