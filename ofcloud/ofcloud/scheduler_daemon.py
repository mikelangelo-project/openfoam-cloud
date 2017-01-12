import os
import signal
import time

import daemon
import daemon.pidfile

from ofcloud.models import Simulation
from utils import launch_simulation
from utils import is_simulation_runnable


def do_work(sleep_interval):
    import django
    django.setup()

    while True:
        __poll_and_run_simulations()
        time.sleep(sleep_interval)


def __poll_and_run_simulations():
    pending_simulations = Simulation.objects.filter(status=Simulation.Status.PENDING.name)
    print("Found %d simulations in PENDING state." % len(pending_simulations))

    for pending_simulation in pending_simulations:
        if is_simulation_runnable(pending_simulation):
            launch_simulation(pending_simulation)
        else:
            print("Maximum number of simulations already running! "
                  "Pending simulations will be run when currently running finish")


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
