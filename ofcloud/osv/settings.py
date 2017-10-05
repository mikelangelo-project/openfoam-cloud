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


__author__ = 'justin_cinkelj'
'''
A few global settings
'''
import os

# where is OSv source code (scripts/run.py and friends)
OSV_SRC = '/opt/osv-src'
OSV_BRIDGE = 'virbr0'
OSV_CLI_APP = '/cli/cli.so'  # path to cli app inside OSv VMs
OSV_API_PORT = 8000

OSV_WORK_DIR = os.environ['HOME'] + '/osv-work'  # can be auto-generated
