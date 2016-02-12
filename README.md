# Installing

Install required Python packages

    pip install -r requirements.txt

Install 

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

# Running

Ensure snap, influxdb and grafana are running. Define a datasource for influxdb
in grafana.

* snap: `/opt/snap/bin/snapd -t 0 -a /opt/snap/plugin`
* influxdb: `/etc/init.d/influxdb start`
* grafana: `/etc/init.d/grafana-server start`

Then launch the OpenFOAM backend

    python manage.py runserver 0.0.0.0:8008
