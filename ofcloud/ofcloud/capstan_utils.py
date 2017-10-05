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
from os import environ as env
from subprocess import Popen


def init_and_compose_capstan_package(simulation_name, capstan_package_folder, solver):
    # Initialise MPM package
    cmd = ["capstan", "package", "init",
           "--name", simulation_name,
           "--title", simulation_name,
           "--author", env['OS_TENANT_NAME']]
    # We have to include the required packages in the command.

    for d in get_solver_deps(solver):
        cmd.append("--require")
        cmd.append(d)

    # Initialise MPM package at the given path.
    cmd.append(capstan_package_folder)
    # Invoke capstan tool.
    p = Popen(cmd)
    p.wait()
    image_name = "temp/%s" % (os.path.basename(capstan_package_folder))
    # Now we are ready to compose the package into a VM
    p = Popen([
        "capstan", "package", "compose",
        "--size", "500M",
        "--run", "--redirect=>>/run.log /cli/cli.so",
        "--pull-missing",
        image_name], cwd=capstan_package_folder)
    # Wait for the image to be built.
    p.wait()
    return image_name


def get_solver_deps(solver):
    solver_deps, _ = __get_solver_config()[solver]
    return solver_deps + __get_common_deps()


def get_solver_so(solver):
    _, solver_so = __get_solver_config()[solver]
    return solver_so


def __get_solver_config():
    # Value for each solver consist of a tuple. The first tuple object is the dependency
    # of the solver, the second one is the command with which we run the simulation using the selected solver.

    # TODO predefined image name for each solver
    # in case we will have images ready on openstack/amazon we must define names of those images
    # If solver image won't exist we will still create it with capstan
    return {
        "openfoam.pimplefoam":
            (["openfoam.pimplefoam-2.4.0"], "pimpleFoam.so"),
        "openfoam.pisofoam":
            (["openfoam.pisofoam-2.4.0"], "pisoFoam.so"),
        "openfoam.poroussimplefoam":
            (["openfoam.poroussimplefoam-2.4.0"], "poroussimpleFoam.so"),
        "openfoam.potentialfoam":
            (["openfoam.potentialfoam-2.4.0"], "potentialFoam.so"),
        "openfoam.rhoporoussimplefoam":
            (["openfoam.rhoporoussimplefoam-2.4.0"], "rhoporoussimpleFoam.so"),
        "openfoam.rhosimplefoam":
            (["openfoam.rhosimplefoam-2.4.0"], "rhosimpleFoam.so"),
        "openfoam.simplefoam":
            (["openfoam.simplefoam-2.4.0"], "simpleFoam.so")
    }


def __get_common_deps():
    return [
        "osv.cli",
        "osv.nfs",
        "ompi-1.10"
    ]
