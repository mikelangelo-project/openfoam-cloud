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


import json
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

# Replacements dict defines keywords in decomposeParDict template to be replaced with the corresponding value
# from decompose_dict, which is generated from the form inputs in horizon-openfoam dashboard.
# First level defines the decomposition method used. In each dictionary entry there are mappings defined as:
# "{template_keyword}" : ("decompose_dict_field", optional)
# If a template keyword is found in the decomposeParDict template file it is replaced with the value of field
# 'decompose_dict_field' in decompose_dict. If the field is marked as optional, it will be uncommented in
# the final decomposeParDict
DECOMPOSE_PAR_DICT_REPLACEMENTS = {
    "simple": {
        "{number_of_subdomains}": ("subdomains", False),
        "{coeffs_n}": ("n", False),
        "{coeffs_delta}": ("delta", False),
    },
    "hierarchical": {
        "{number_of_subdomains}": ("subdomains", False),
        "{coeffs_n}": ("n", False),
        "{coeffs_delta}": ("delta", False),
        "{coeffs_order}": ("order", False)
    },
    "scotch": {
        "{number_of_subdomains}": ("subdomains", False),
        "{coeffs_processor_weights}": ("processor_weights", True),
        "{coeffs_strategy}": ("strategy", True)
    },
    "manual": {
        "{number_of_subdomains}": ("subdomains", False),
        "{coeffs_datafile}": ("datafile", False)
    }
}


def prepare_case_files(simulation, instance_cpus):
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

    # If any parallelisation, use the corresponding decomposeParDict
    if instance_cpus > 1:
        decomposition_dict = json.loads(simulation.decomposition)
        decomposition_method = decomposition_dict['decomposition_method']

        decompose_par_dict_path = path.join(case_path, "system/decomposeParDict")
        os.remove(decompose_par_dict_path)

        with open("ofcloud/templates/decomposeParDict_%s" % decomposition_method, ) as infile, open(
                decompose_par_dict_path, "w") as outfile:
            for line in infile:
                for src, target in DECOMPOSE_PAR_DICT_REPLACEMENTS[decomposition_method].iteritems():
                    # if the parameter is defined as optional we have to remove comment annotations from those lines
                    is_optional = target[1]
                    target = decomposition_dict[target[0]]
                    line = line.replace(str(src), str(target))
                    if is_optional and len(target) > 0:
                        line = line.replace("//", "")
                outfile.write(line)
    return case_folder


def copy_case_files_to_nfs_location(simulation_instance,
                                    case_folder,
                                    local_nfs_mount_location,
                                    nfs_server_mount_folder):
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
        nfs_server_mount_folder, str(simulation_instance_id))
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
