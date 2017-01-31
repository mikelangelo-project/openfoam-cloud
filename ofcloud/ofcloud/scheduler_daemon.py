import os
import signal
import time

import daemon
import daemon.pidfile

import utils
from ofcloud.models import Instance


def do_work(sleep_interval):
    import django
    django.setup()

    while True:
        __poll_and_shutdown_instances()
        __poll_and_run_instances()
        time.sleep(sleep_interval)


def __poll_and_shutdown_instances():
    running_instances = Instance.objects.filter(status=Instance.Status.RUNNING.name)
    print "Instances with status RUNNING %s" % str(running_instances)

    # split instances regarding they still have a server running or not (orphaned)
    running_instances, orphaned_instances = utils.split_running_and_orphaned_instances(running_instances)

    # print "Running instance ids %s" % running_instance_ids
    # print "Orphaned instance ids %s" % orphaned_instance_ids

    # mark orphaned instances as completed
    utils.set_instance_status(orphaned_instances, Instance.Status.COMPLETE.name)

    # get instances of finished simulations
    finished_instances = utils.get_instances_of_finished_simulations(running_instances)

    # shutdown
    utils.shutdown_nova_servers(finished_instances)
    utils.set_instance_status(finished_instances, Instance.Status.COMPLETE.name)


def __poll_and_run_instances():
    pending_instances = Instance.objects.filter(status=Instance.Status.PENDING.name)
    print('Found %d instances in PENDING state.' % len(pending_instances))

    for pending_instance in pending_instances:
        if utils.is_simulation_instance_runnable(pending_instance):
            utils.launch_simulation_instance(pending_instance)
        else:
            print("Maximum number of simulation instances already running! "
                  "Pending instances will be run after currently running instances finish")


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
