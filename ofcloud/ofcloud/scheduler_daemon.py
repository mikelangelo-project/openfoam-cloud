import os
import signal
import threading
import time
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
        'run': None
    }

    while True:
        if not threads['shutdown'] or not threads['shutdown'].isAlive():
            threads['shutdown'] = threading.Thread(target=__poll_and_shutdown_instances, args=(simulation_providers,))
            threads['shutdown'].start()

        if not threads['run'] or not threads['run'].isAlive():
            threads['run'] = threading.Thread(target=__poll_and_run_instances, args=(simulation_providers,))
            threads['run'].start()

        time.sleep(sleep_interval)


def __poll_and_shutdown_instances(simulation_providers):
    print "Polling instances for shutdown"
    for provider in simulation_providers:
        provider_id = provider.get_provider_id()
        print "Using provider %s" % provider_id

        running_instances, orphaned_instances = provider.split_running_and_orphaned_instances(
            Instance.objects.filter(status=Instance.Status.RUNNING.name, provider=provider_id))

        # Mark any orphaned instance objects as complete
        utils.update_instance_status(orphaned_instances, Instance.Status.COMPLETE.name)
        finished_instances = utils.get_instances_of_finished_simulations(running_instances)

        if len(finished_instances) or len(running_instances) or len(orphaned_instances):
            print "Running/Finished/Orphaned: %d/%d/%d" % (
                len(running_instances), len(finished_instances), len(orphaned_instances))

        provider.shutdown_instances(finished_instances)
        utils.update_instance_status(finished_instances, Instance.Status.COMPLETE.name)


def __poll_and_run_instances(simulation_providers):
    pending_instances = Instance.objects.filter(status=Instance.Status.PENDING.name)
    print('Found %d instances in PENDING state.' % len(pending_instances))

    for pending_instance in pending_instances:
        utils.launch_simulation_instance(pending_instance, simulation_providers)


def run(sleep_interval):
    pidfile = daemon.pidfile.PIDLockFile(path="/tmp/scheduler_daemon.pid")

    if pidfile.is_locked():
        print("Killing previous scheduler_daemon instance (pid = %s)" % pidfile.read_pid())
        os.kill(pidfile.read_pid(), signal.SIGTERM)

    now_seconds = str(time.time())
    stdout = open("/tmp/scheduler_daemon_%s.log" % now_seconds, "w+")
    stderr = open("/tmp/scheduler_daemon_error_%s.log" % now_seconds, "w+")

    daemon_context = daemon.DaemonContext(stdout=stdout, stderr=stderr, detach_process=True, pidfile=pidfile)

    with daemon_context:
        do_work(sleep_interval)


def shutdown():
    pidfile = daemon.pidfile.PIDLockFile(path="/tmp/scheduler_daemon.pid")

    pid = pidfile.read_pid()
    print "Shutting down scheduler daemon with pid %d" % pid
    os.kill(pid, signal.SIGTERM)
    print "Scheduler daemon (%d) successfully terminated" % pid
