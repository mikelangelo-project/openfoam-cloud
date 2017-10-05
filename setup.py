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


import os
from setuptools import find_packages, setup

with open(os.path.join(os.path.dirname(__file__), './README.rst')) as readme:
    README = readme.read()

# allow setup.py to be run from any path
os.chdir(os.path.normpath(os.path.join(os.path.abspath(__file__), os.pardir)))

print find_packages()

setup(
    name='openfoam-cloud',
    version='1.0',
    packages=find_packages(exclude=['']),
    include_package_data=True,
    license='Apache Software License',
    description='OpenFOAM Cloud backend application',
    long_description=README,
    url='https://www.xlab.si/',
    author='XLAB d.o.o.',
    author_email='pypi@xlab.si',
    classifiers=[
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: Apache Software License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.7',
    ],
    install_requires=[
        'Django',
        'djangorestframework',
        'python-openstackclient',
        'python-swiftclient',
        'requests',
        'Jinja2==2.0',
        'libvirt-python',
        'boto',
        'python-daemon==2.1.2'
    ]
)
