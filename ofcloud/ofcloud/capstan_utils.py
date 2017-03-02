import os
import tempfile
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
    os.chdir(capstan_package_folder)
    image_name = "temp/%s" % (os.path.basename(capstan_package_folder))
    # Now we are ready to compose the package into a VM
    p = Popen([
        "capstan", "package", "compose",
        "--size", "500M",
        "--run", "--redirect=/case/run.log /cli/cli.so",
        "--pull-missing",
        image_name])
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
            (["eu.mikelangelo-project.openfoam.pimplefoam"], "pimpleFoam.so"),
        "openfoam.pisofoam":
            (["eu.mikelangelo-project.openfoam.pisofoam"], "pisoFoam.so"),
        "openfoam.poroussimplefoam":
            (["eu.mikelangelo-project.openfoam.poroussimplefoam"], "poroussimpleFoam.so"),
        "openfoam.potentialfoam":
            (["eu.mikelangelo-project.openfoam.potentialfoam"], "potentialFoam.so"),
        "openfoam.rhoporoussimplefoam":
            (["eu.mikelangelo-project.openfoam.rhoporoussimplefoam"], "rhoporoussimpleFoam.so"),
        "openfoam.rhosimplefoam":
            (["eu.mikelangelo-project.openfoam.rhosimplefoam"], "rhosimpleFoam.so"),
        "openfoam.simplefoam":
            (["eu.mikelangelo-project.openfoam.simplefoam"], "simpleFoam.so")
    }


def __get_common_deps():
    return [
        "eu.mikelangelo-project.osv.cli",
        "eu.mikelangelo-project.osv.nfs"
    ]