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
    license='BSD License',
    description='OpenFOAM Cloud backend application',
    long_description=README,
    url='https://www.xlab.si/',
    author='XLAB d.o.o.',
    author_email='pypi@xlab.si',
    classifiers=[
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
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
