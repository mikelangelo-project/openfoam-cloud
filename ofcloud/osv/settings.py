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
