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
import signal
import threading
import time
import traceback
from importlib import import_module

import daemon
import daemon.pidfile
from django.conf import settings

import utils
from ofcloud.models import Instance


def do_work(sleep_interval):
    import django
    django.setup()

    # create providers
    simulation_providers = []
    for provider_config in settings.PROVIDER_CONFIG:
        package, module = provider_config.get('TYPE').rsplit('.', 1)

        mod = import_module(package)
        provider = getattr(mod, module)
        simulation_providers.append(provider(provider_config.get('NAME'), provider_config))

    threads = {
        'shutdown': None,
        'reconstruct': None,
        'run': None,
        'prepare': None
    }

    while True:
        if not threads['shutdown'] or not threads['shutdown'].isAlive():
            threads['shutdown'] = threading.Thread(target=__poll_for_shutdown, args=(simulation_providers,))
            threads['shutdown'].start()

        if not threads['reconstruct'] or not threads['reconstruct'].isAlive():
            threads['reconstruct'] = threading.Thread(target=__poll_for_reconstruction, args=(simulation_providers,))
            threads['reconstruct'].start()

        if not threads['run'] or not threads['run'].isAlive():
            threads['run'] = threading.Thread(target=__poll_for_run, args=(simulation_providers,))
            threads['run'].start()

        if not threads['prepare'] or not threads['prepare'].isAlive():
            threads['prepare'] = threading.Thread(target=__poll_for_prepare, args=(simulation_providers,))
            threads['prepare'].start()

        time.sleep(sleep_interval)


def __poll_for_shutdown(simulation_providers):
    """
    Polls instances ready for shutdown. 
    
    Instances qualify for shutdown if they are either in Instance.Status.RUNNING or Instance.Status.RECONSTRUCTING
    state and the openFOAM thread is terminated. Orphaned instances are sent to Instance.Status.COMPLETE state.
    
    :param simulation_providers: 
    :return: 
    """

    print "Polling instances for shutdown"
    for provider in simulation_providers:
        provider_id = provider.get_provider_id()
        print "Using provider %s" % provider_id

        running_instances, orphans_1 = provider.split_running_and_orphaned_instances(
            Instance.objects.filter(status=Instance.Status.RUNNING.name, provider=provider_id))

        reconstructing_instances, orphans_2 = provider.split_running_and_orphaned_instances(
            Instance.objects.filter(status=Instance.Status.RECONSTRUCTING.name, provider=provider_id))

        orphaned_instances = orphans_1 + orphans_2

        # Mark any orphaned instance objects as complete
        utils.update_instance_status(orphaned_instances, Instance.Status.COMPLETE.name)

        finished_instances = utils.get_instances_with_finished_openfoam_thread(
            running_instances + reconstructing_instances)

        if len(finished_instances) or len(running_instances) or len(orphaned_instances):
            print "Running/Finished/Orphaned: %d/%d/%d" % (
                len(running_instances), len(finished_instances), len(orphaned_instances))

        provider.shutdown_instances(finished_instances)
        utils.update_instance_status(finished_instances, Instance.Status.COMPLETE.name)


def __poll_for_reconstruction(simulation_providers):
    """
    Polls instances ready for reconstruction and runs reconstructPar command on them.
    
    Instances qualify for reconstruction if they are in Instance.Status.RUNNING_MPI state and the openFOAM thread
    is terminated. Orphaned instances are sent to Instance.Status.COMPLETE state.
    
    :param simulation_providers: 
    :return: 
    """
    print "Polling instances for reconstruction"
    for provider in simulation_providers:
        provider_id = provider.get_provider_id()
        print "Using provider %s" % provider_id

        running_mpi_instances, orphaned_instances = provider.split_running_and_orphaned_instances(
            Instance.objects.filter(status=Instance.Status.RUNNING_MPI.name, provider=provider_id))

        utils.update_instance_status(orphaned_instances, Instance.Status.COMPLETE.name)

        ready_for_reconstruction = utils.get_instances_with_finished_openfoam_thread(running_mpi_instances)

        for instance in ready_for_reconstruction:
            provider.run_reconstruction(instance)


def __poll_for_prepare(simulation_providers):
    """
    Polls instances ready for preparation of openFOAM.
    
    Instances qualify for preparation if they are in Instance.Status.PENDING state.
    
    :param simulation_providers: 
    :return: 
    """
    print "Polling instances for preparation"

    pending_instances = Instance.objects.filter(status=Instance.Status.PENDING.name)
    print('Found %d instances in PENDING state.' % len(pending_instances))

    for instance in pending_instances:
        utils.prepare_simulation_instance(instance, simulation_providers)


def __poll_for_run(simulation_providers):
    """
    Polls instances ready to run openFOAM simulations. 
    
    Instances qualify for running if they are in Instance.Status.READY state or in Instance.Status.DECOMPOSING state
    with openFOAM thread terminated.
    
    :param simulation_providers: 
    :return: 
    """

    decomposing_instances = Instance.objects.filter(status=Instance.Status.DECOMPOSING.name)
    finished_decomposing_instances = utils.get_instances_with_finished_openfoam_thread(decomposing_instances)

    utils.update_instance_status(finished_decomposing_instances, Instance.Status.READY.name)

    print "Polling instances for run simulation"

    ready_instances = Instance.objects.filter(status=Instance.Status.READY.name)

    print('Found %d instances in READY state.' % len(ready_instances))

    for ready_instance in ready_instances:
        instance_provider = [provider for provider in simulation_providers if
                             provider.id == ready_instance.provider]
        instance_provider[0].run_simulation(ready_instance)


def __kill_and_wait(pid):
    os.kill(pid, signal.SIGTERM)
    i = 0
    while True:
        try:
            time.sleep(1)
            os.kill(pid, signal.SIG_DFL)
            i += 1
            # sometimes the process does not go down gracefully, try to kill it every 10 seconds
            if i % 10 == 0:
                os.kill(pid, signal.SIGKILL)
        except OSError:
            return


def run(sleep_interval):
    pidfile = daemon.pidfile.PIDLockFile(path="/tmp/scheduler_daemon.pid")

    if pidfile.is_locked():
        print "Existing lock file found"
        try:
            os.kill(pidfile.read_pid(), signal.SIG_DFL)
            print "An instance of scheduler daemon is already running. If you wish to restart, use the 'restart' " \
                  "command"
            return
        except:
            pidfile.break_lock()

    now_seconds = str(time.time())
    stdout = open("/tmp/scheduler_daemon_%s.log" % now_seconds, "w+")
    stderr = open("/tmp/scheduler_daemon_error_%s.log" % now_seconds, "w+")

    print "Running scheduler daemon with refresh interval of %s seconds" % sleep_interval
    daemon_context = daemon.DaemonContext(stdout=stdout,
                                          stderr=stderr,
                                          detach_process=True,
                                          pidfile=pidfile,
                                          working_directory=os.getcwd())

    with daemon_context:
        do_work(sleep_interval)


def shutdown():
    pidfile = daemon.pidfile.PIDLockFile(path="/tmp/scheduler_daemon.pid")
    if pidfile.is_locked():
        pid = pidfile.read_pid()
        try:
            os.kill(pid, signal.SIG_DFL)
        except OSError:
            print "There doesn't seem to be any instance of scheduler daemon running but the lock file exists"
            print "Breaking lock file"
            pidfile.break_lock()
            return 0

        try:
            print "Shutting down scheduler daemon (%d)" % pid
            __kill_and_wait(pid)
            pidfile.break_lock()
            print "Scheduler daemon (%d) successfully terminated" % pid
            return 1
        except OSError:
            print traceback.format_exc()
    else:
        print "There doesn't seem to be any instance of scheduler daemon running"
        return 0


def restart(sleep_interval):
    print "Restarting scheduler daemon with refresh interval of %s seconds" % sleep_interval
    shutdown_status = shutdown()
    if shutdown_status == 1:
        run(sleep_interval)
    else:
        print "To start a new instance use the 'runscheduler' command"
