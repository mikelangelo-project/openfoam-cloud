import os
import os.path
import re
import shutil
import tarfile
import tempfile
from os import path

import boto
import boto.s3.connection
from django.conf import settings


def prepare_case_files(simulation):
    # Connect to s3
    s3_conn = boto.connect_s3(
        aws_access_key_id=settings.S3_ACCESS_KEY_ID,
        aws_secret_access_key=settings.S3_SECRET_ACCESS_KEY,
        host=settings.S3_HOST,
        port=settings.S3_PORT,
        calling_format=boto.s3.connection.OrdinaryCallingFormat(),
    )
    case_folder = tempfile.mkdtemp(prefix='ofcloud-case-')
    case_path = path.join(case_folder, "case")
    os.makedirs(case_path)
    # Get the bucket for the input data.
    bucket = s3_conn.get_bucket(simulation.container_name)
    # Get the key from the bucket.
    input_key = bucket.get_key(simulation.input_data_object)
    casefile = path.join(case_path, os.path.basename(simulation.input_data_object))

    input_key.get_contents_to_filename(casefile)
    # Unpack the input case.
    tar = tarfile.open(casefile, 'r')
    tar.extractall(case_path)
    tar.close()
    # Remove the downloaded file
    os.remove(casefile)
    return case_folder


def copy_case_files_to_nfs_location(simulation_instance, case_folder):
    # TODO provider specific
    local_nfs_mount_location = settings.LOCAL_NFS_MOUNT_LOCATION
    nfs_mount_folder = settings.NFS_SERVER_MOUNT_FOLDER

    simulation_instance_id = simulation_instance.id
    local_instance_files_location = "%s/%s" % (
        local_nfs_mount_location, str(simulation_instance_id))

    if os.path.exists(local_instance_files_location):
        shutil.rmtree(local_instance_files_location)

    print "Copying src=%s, dst=%s" % (case_folder, local_instance_files_location)
    shutil.copytree(src=case_folder, dst=local_instance_files_location)

    # TODO maybe just return the data, and save outside this function?
    # Save storage information to model
    simulation_instance.local_case_location = '%s/case' % local_instance_files_location
    simulation_instance.nfs_case_location = '%s/%s/case' % (
        nfs_mount_folder, str(simulation_instance_id))
    simulation_instance.save()

    # Delete temporary case data
    shutil.rmtree(case_folder)


def update_case_files(case_path, case_updates):
    input_files = {}

    # First, get a list of files that need to be modified
    for key in case_updates:
        file_end_index = key.rfind('/')
        file_path = key[0:file_end_index]
        variable = key[file_end_index + 1:]

        if file_path not in input_files:
            input_files[file_path] = {}

        input_files[file_path][variable] = case_updates[key]

    output_files = {}

    # Now loop through files and update them.
    for input_file, variables in input_files.iteritems():
        file_path = os.path.join(case_path, input_file)

        f = open(file_path, 'r')
        data = f.read()
        f.close()

        for var, value in variables.iteritems():
            data = re.sub(re.compile('^[ \t]*%s\s+.*$' % var, re.MULTILINE), '%s %s;' % (var, value), data)

        output_files[input_file] = file_path

        f = open(file_path, 'w')
        f.write(data)
        f.close()

    return output_files
