# OpenFOAM Cloud Backend
 
## Installing

Install required Python packages

    pip install -r requirements.txt

Install the following required packages

* [capstan](https://drive.google.com/drive/folders/0B4qi_kpom5ITZ0RCYUlFQUJhUVU)
* [snap](https://drive.google.com/drive/folders/0B4rwCneIeHMybmlENDNPYXJ3c3M)
* grafana: `sudo apt-get install grafana`
* influxdb: `sudo apt-get install influxdb`

Copy local settings

    cp ofcloud/ofcloud/local_settings.py{.example,}

Edit local settings to reflect your environment

    OPENFOAM_BASENAME       = 'http://openfoam.example.com'
    GRAFANA_BASENAME        = 'http://grafana.example.com'
    
    S3_ACCESS_KEY_ID        = 'your-s3-key'
    S3_SECRET_ACCESS_KEY    = 'your-s3-secret-key'
    S3_HOST                 = 's3-host'
    S3_PORT                 = 8443
    
    SNAP_SERVICE            = 'snap-api-root'
    INFLUX_DB_HOST          = 'influxdb-host'
    INFLUX_DB_PORT          = 8086
    INFLUX_DB_NAME          = 'snap'
    INFLUX_DB_USER          = 'admin'
    INFLUX_DB_PASS          = 'admin'

    # Dedicated openfoam network settings
    OPENFOAM_NETWORK_PREFIX = 'openfoam'
    OPENFOAM_NETWORK_CIDR = 'your desired network CIDR'
    OPENFOAM_NETWORK_ALLOCATION_POOL_START = 'your IP allocation range start'
    OPENFOAM_NETWORK_ALLOCATION_POOL_END = 'your IP allocation range end'
    OPENFOAM_NETWORK_GATEWAY_IP = 'your gateway IP usually the first IP in CIDR range'

    # Scheduler daemon settings
    SCHEDULER_REFRESH_INTERVAL_SECONDS = 'desired scheduler daemon refresh interval in seconds'

    # OpenFOAM simulations save their results on a NFS server as is evident from the NFS_IP setting. The
    # LOCAL_NFS_MOUNT_LOCATION setting tells the scheduler daemon where to prepare simulation case files, capstan package etc.
    # This folder should have the NFS location mounted (example /mnt/OpenFOAM_results) except when the scheduler runs on
    # the NFS machine itself, then this can point directly to the exported directory (for instance '/export/OpenFOAM_results/')
    LOCAL_NFS_MOUNT_LOCATION = 'path to folder with mounted NFS location'

    # Network file storage server ip address
    NFS_IP = 'nfs server ip'

    # Location on the NFS server where OpenFOAM case files and results will be saved
    NFS_SERVER_MOUNT_FOLDER = 'location on the nfs server, where simulation case files and results are saved'

    # Maximum number of launch retries of one instance. When this limit is reached, the simulation instance enters the
    # 'FAILED' state
    OPENFOAM_SIMULATION_MAX_RETRIES = 3


## Running

Ensure snap, influxdb and grafana are running. Define a datasource for influxdb
in grafana.

* snap: `/opt/snap/bin/snapd -t 0 -a /opt/snap/plugin`
* influxdb: `/etc/init.d/influxdb start`
* grafana: `/etc/init.d/grafana-server start`

Then launch the OpenFOAM backend

    python manage.py runserver 0.0.0.0:8008

Next launch the OpenFOAM scheduler daemon

    python manage.py runscheduler

## Acknowledgements

This project has been conducted within the RIA [MIKELANGELO
project](https://www.mikelangelo-project.eu) (no.  645402), started in January
2015, and co-funded by the European Commission under the H2020-ICT- 07-2014:
Advanced Cloud Infrastructures and Services programme.
