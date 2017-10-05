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


from __future__ import print_function

__author__ = 'justin_cinkelj'

import logging
import os
import math
from uuid import uuid4
import settings
from subprocess import check_call
from time import sleep
from random import randint
import shutil
import sys
import libvirt
from jinja2 import Environment, PackageLoader
import argparse
import datetime


# for '192.168.1.2/24' return '192.168.1.2' and '255.255.255.0'
def cidr_to_ip_mask(cidr):
    ip, bits = cidr.split('/')
    n1 = int(bits)
    n0 = 32 - n1
    ss = '1' * n1 + '0' * n0
    nm = [ss[-32:-24], ss[-24:-16], ss[-16:-8], ss[-8:]]  # reversed order, nm[0] is highest byte
    nm2 = [int(nm_tmp, 2) for nm_tmp in nm]
    netmask = '%d.%d.%d.%d' % (nm2[0], nm2[1], nm2[2], nm2[3])
    return ip, netmask


class VMParam:
    NET_STATIC = 'static'
    NET_DHCP = 'dhcp'
    NET_NONE = 'net-none'

    '''
    Save parameters. Also create copy of VM image for this particular VM.
    '''

    def __init__(self,
                 command='',
                 image='',
                 use_image_copy=False,
                 cpus=1,
                 memory=512,

                 networking=True,
                 net_ip='',
                 net_mac='',  # '52:54:00:12:34:56' is default in run.py
                 net_gw='',
                 net_dns='',
                 bridge=settings.OSV_BRIDGE,

                 gdb_port=0,
                 cpu_pin=True,
                 unsafe_cache=False,
                 verbose=False,
                 debug=False
                 ):
        log = logging.getLogger(__name__)
        self._vm_name = 'osv-%09d' % randint(0, 1e9)
        self._command = command
        self._full_command_line = ''
        self._cpus = cpus
        self._memory = memory
        self._unsafe_cache = unsafe_cache
        self._cpu_pin = cpu_pin
        self._debug = debug
        self._verbose = verbose
        # image relative to OSV_SRC, or abs path
        if image:
            if os.path.isabs(image):
                self._image_orig = image
            else:
                self._image_orig = os.path.abspath(os.path.join(settings.OSV_SRC, image))
        else:
            mode = 'debug' if self._debug else 'release'
            image_rel_path = 'build/%s/usr.img' % mode
            self._image_orig = os.path.abspath(os.path.join(settings.OSV_SRC, image_rel_path))
        # self._image_orig now contains abs path to image
        self._use_image_copy = use_image_copy
        if self._use_image_copy:
            # Put image to directory owned by current user.
            # Image will be later owned by root, and we still have to remove it.
            self._in_use_image = '%s/%s-usr.img' % (settings.OSV_WORK_DIR, self._vm_name)
            log.info('Copy image %s -> %s', self._image_orig, self._in_use_image)
            shutil.copy(self._image_orig, self._in_use_image)
        else:
            self._in_use_image = self._image_orig

        self._gdb_port = gdb_port

        self._bridge = bridge
        self._net_ip = net_ip
        self._net_gw = net_gw
        self._net_dns = net_dns
        if net_ip:
            self._net_mode = VMParam.NET_STATIC
        elif networking:
            self._net_mode = VMParam.NET_DHCP
        else:
            self._net_mode = VMParam.NET_NONE

        if net_mac == 'rand':
            self._net_mac = '52:54:00:%02x:%02x:%02x' % (randint(0, 255), randint(0, 255), randint(0, 255))
        elif net_mac:
            self._net_mac = net_mac
        else:
            # self._net_mac = '52:54:00:12:34:56'
            self._net_mac = ''
        log.info('VM MAC %s', self._net_mac)

    def remove_image_copy(self):
        log = logging.getLogger(__name__)
        if self._use_image_copy:
            if self._in_use_image != self._image_orig:
                log.info("Remove image copy %s", self._in_use_image)
                # image file is now owned by root, or libvirt or whoever user
                # os.remove works if we own directory
                try:
                    os.remove(self._in_use_image)
                except Exception as ex:
                    log.info('Image %s remove failed (msg: %s)', self._in_use_image, ex.get_error_message())

    '''
    Build command for run.py.
    The full command line for OSv VM (including network settings) is stored in _full_command_line.
    '''

    def _build_run_command(self):
        log = logging.getLogger(__name__)
        arg = ['./scripts/run.py']
        if self._in_use_image:
            arg.extend(['--image', self._in_use_image])
        if self._cpus:
            arg.extend(['--vcpus', str(self._cpus)])
        if self._memory:
            arg.extend(['--memsize', str(self._memory)])
        if self._verbose:
            arg.append('--verbose')
        if self._debug:
            arg.append('--debug')

        cmd_net = ''
        if self._net_mode == VMParam.NET_NONE:
            # net disabled by default
            pass
        else:
            if self._net_mac:
                arg.extend(['--mac', str(self._net_mac)])

            if self._net_mode == VMParam.NET_DHCP:
                # -v for KVM vhost networking, requires root/sudo rights
                arg.extend(['-n', '-v'])
            elif self._net_mode == VMParam.NET_STATIC:
                # static network config is pushed in command param
                # ./scripts/run.py -n -e "--ip=eth0,10.0.0.2,255.255.255.0 \
                #  --defaultgw=10.0.0.1 --nameserver=10.0.0.1 `cat build/release/cmdline`"
                arg.extend(['-n', '-v'])
                ip, netmask = cidr_to_ip_mask(self._net_ip)
                cmd_net += '--ip=eth0,%s,%s' % (ip, netmask)
                if self._net_gw:
                    cmd_net += ' --defaultgw=%s' % self._net_gw
                if self._net_dns:
                    cmd_net += ' --nameserver=%s' % self._net_dns

        full_command = ''
        if cmd_net:
            # net_cmd for static ip must be passed as part of command (with default cli.so or with user-defined app)
            if self._command:
                full_command = '%s %s' % (cmd_net, self._command)
            else:
                full_command = '%s %s' % (cmd_net, settings.OSV_CLI_APP)
        elif self._command:
            full_command = self._command
        else:
            full_command = settings.OSV_CLI_APP
        if full_command:
            arg.extend(['-e', full_command])
        self._full_command_line = full_command

        return arg


class VM:
    """
    Create new VM.
    net_ip is in CIDR notation 'ip/bits'
    """

    def __init__(self, **kwargs):
        self._param = VMParam(**kwargs)

        # other vars
        self._child_cmdline_up = False
        self._ip = ''
        self._api_up = False  # set by first API call

        # libvirt
        self._vm = None
        self._console_log = ''
        self._console_log_fd = None

    def _log_name(self):
        if self._vm:
            name = 'vm=%s' % self._vm.name()
        else:
            name = 'vm=None'
        return name

    @classmethod
    def connect_to_existing(cls, ip, name=''):
        vm = VM()
        vm._ip = ip.split('/')[0]  # ip with or without netmask
        if (name):
            conn = VM._libvirt_conn()
            vm._vm = conn.lookupByName(name)
        return vm

    @classmethod
    def _libvirt_conn(cls):
        conn = libvirt.open("qemu:///system")
        return conn

    # use libvirt to start OSv VM
    def run(self, wait_up=False):
        # get full_command_line
        run_arg = self._param._build_run_command()
        full_command_line = self._param._full_command_line
        # full_command_line = '--verbose ' + full_command_line  # run OSv VM in verbose mode
        # image edit.
        cmd = [os.path.join(settings.OSV_SRC, 'scripts/imgedit.py'), 'setargs', self._param._in_use_image,
               full_command_line]
        print('Set cmd: %s' % ' '.join(cmd))
        check_call(cmd)

        name = str(uuid4())[:8]
        # what are valid cache/io mode combinations
        #   none + native, not available on all hosts/filesystems (err: file system may not support O_DIRECT)
        #   unsafe + native - rejected by libvirt, err: unsupported configuration: native I/O needs either no disk
        #   cache or directsync cache mode, QEMU will fallback to aio=threads
        #   unsafe + threads - is ok
        if self._param._unsafe_cache:
            image_cache_mode, image_io_mode = 'unsafe', 'threads'
        else:
            image_cache_mode, image_io_mode = 'none', 'native'

        self._console_log = '%s/%s-console.log' % (settings.OSV_WORK_DIR, self._param._vm_name)
        vm_param = {'name': self._param._vm_name,
                    'memory': self._param._memory,
                    'vcpu_count': self._param._cpus,
                    'image_file': self._param._in_use_image,
                    'image_cache_mode': image_cache_mode,
                    'image_io_mode': image_io_mode,
                    'net_mac': self._param._net_mac,
                    'net_bridge': self._param._bridge,
                    'console_log': self._console_log,
                    'cpu_pin': self._param._cpu_pin,
                    'gdb_port': self._param._gdb_port,
                    }
        tmpl_env = Environment(loader=PackageLoader('lin_proxy', 'templates'))
        template = tmpl_env.get_template('osv-libvirt.template.xml')
        xml = template.render(vm=vm_param)
        # print xml

        # make console_log file, so that we have permission to read it.
        open(self._console_log, 'w').close()
        conn = VM._libvirt_conn()
        self._vm = conn.defineXML(xml)
        self._vm.create()  # start vm
        self._console_log_fd = open(self._console_log)

        if self._param._net_mode == VMParam.NET_STATIC:
            self._ip = self._param._net_ip.split('/')[0]
        stdout_data = ''
        if wait_up:
            stdout_data = self.wait_up()
        return stdout_data

    def is_up(self):
        """
        Is VM still up, or did it already exit (kill to qemu, main app terminated)?
        """
        if self._vm:
            return self._vm.isActive()
        return False

    def terminate(self):
        log = logging.getLogger(__name__)
        if self._vm:
            log.info('Terminating libvirt vm %s', self._vm.name())
            if not self._vm.isActive():
                # Invalid param, run.py reported error.
                # Or normal termintaino of app started via command.
                log.info('VM %s already terminated', self._vm.name())
            else:
                self.os_api().shutdown()
                # check
                ii = 10.0
                while ii > 0:
                    if not self._vm.isActive():
                        log.info('VM %s terminated', self._vm.name())
                        break
                    else:
                        # poll_ret is None
                        log.info('VM %s still alive', self._vm.name())
                        sleep(0.5)
                        ii -= 0.5
                return
            try:
                if self._vm.isActive():
                    self._vm.destroy()
                sys.stdout.flush()
            except libvirt.libvirtError as ex:
                log.info('VM %s destroy failed: %s', self._log_name(), ex.get_error_message())
            try:
                self._vm.undefine()
                sys.stdout.flush()
            except libvirt.libvirtError as ex:
                log.info('VM %s destroy/undefine failed: %s', self._log_name(), ex.get_error_message())
            self._vm = None
        sys.stdout.flush()
        if self._console_log_fd:
            self._console_log_fd.close()
            self._console_log_fd = None
        self._param.remove_image_copy()
        # the console log file is left

    # read stdout, stderr
    # update child_cmdline_up when cmd prompt found
    def read_std(self):
        log = logging.getLogger(__name__)
        if not self._console_log_fd:
            return ''
        out = self._console_log_fd.read()
        if not self._child_cmdline_up or not self._ip:
            for cur_line in out.split('\r\n'):
                if not self._child_cmdline_up:
                    '''
                    ideal line == '/# '
                    but 'random: device unblocked.' might be there too.
                    or 'random' garbage can be prepend ('ESC[6n/# ')
                    '''
                    if cur_line[:3] == '/# ' or cur_line[-3:] == '/# ':
                        log.info('child %s cmd_prompt is up', self._log_name())
                        self._child_cmdline_up = True
                if not self._ip:
                    # Is IP assigned ? Search for 'eth0: $IP'
                    # only in verbose mode - [I/246 dhcp]: Configuring eth0: ip 192.168.122.37 subnet mask 255.255.255.0 gateway 192.168.122.1 MTU 1500
                    # there is also: 'eth0: ethernet address: 52:54:00:12:34:56'
                    ss = 'eth0: '
                    ss_ignore = 'eth0: ethernet address:'
                    if 0 == cur_line.find(ss_ignore):
                        log.debug('child %s eth0 ignore line, %s', self._log_name(), cur_line)
                    elif 0 == cur_line.find(ss):
                        log.debug('child %s eth0 IP found, %s', self._log_name(), cur_line)
                        self._ip = cur_line.split(' ')[1]
                        log.info('child %s IP via DHCP, %s', self._log_name(), self._ip)
        return out

    """
    Function will eat stdout/err (file pos could be reset to orig value, but it was not really needed so far).
    It is meaningful only for default cli.so app.

    The reason for waiting on command prompt is that it's started after detached apps (init scripts) - e.g. after http-server.
    When command prompt shows, also http-server REST api should be fully up (but we anyway as first REST api call do a dummy
    http GET, "just in case").
    """

    def wait_cmd_prompt(self, Td=5, Td2=0.1):
        log = logging.getLogger(__name__)
        stdout_data = ''
        if self._param._command and self._param._command.find(settings.OSV_CLI_APP) == -1:
            log.debug('child %s cmd_prompt shows up only with cli.so app', self._log_name())
            return False, stdout_data
        if self._child_cmdline_up:
            return True, stdout_data

        iimax = math.ceil(float(Td) / Td2)
        ii = 0
        while ii < iimax:
            stdout_data2 = self.read_std()
            stdout_data += stdout_data2
            if self._child_cmdline_up:
                return True, stdout_data
            log.debug('child %s cmd_prompt not up yet', self._log_name())
            sleep(Td2)
            ii += 1
        return False, stdout_data

    """
    Wait on VM to get IP from DHCP.
    If static IP configuration is used, return success immediately.
    """

    def wait_ip(self, Td=5, Td2=0.1):
        log = logging.getLogger(__name__)
        stdout_data = ''
        if self._ip:
            # DHCP IP already found, or static IP set in .run())
            return True, stdout_data

        iimax = math.ceil(float(Td) / Td2)
        ii = 0
        while ii < iimax:
            stdout_data2 = self.read_std()
            stdout_data += stdout_data2
            if self._ip:
                return True, stdout_data
            log.debug('child %s ip not up yet', self._log_name())
            sleep(Td2)
            ii += 1
        return False, stdout_data

    """
    Wait on VM to be fully up and operational.
    """

    def wait_up(self, Td=5, Td2=0.1):
        log = logging.getLogger(__name__)
        stdout_data = ''
        if self._vm:
            iimax = math.ceil(float(Td) / Td2)
            ii = 0
            while ii < iimax:
                if self._vm.isActive():
                    break
                log.debug('child %s ip not up yet', self._log_name())
                sleep(Td2)
                ii += 1
            ip_found, stdout_data2 = self.wait_ip(Td, Td2)
            stdout_data += stdout_data2
            cmd_found, stdout_data2 = self.wait_cmd_prompt(Td, Td2)
            stdout_data += stdout_data2
        return stdout_data

    def app_api(self, name):
        # circular dependency import
        import api
        api_instance = api.App(self, name)
        return api_instance

    def env_api(self, name=None):
        # circular dependency import
        import api
        if name is None:
            # all env vars
            api_instance = api.EnvAll(self)
            return api_instance
        else:
            # known env variable name
            api_instance = api.Env(self, name)
            return api_instance

    def os_api(self):
        # circular dependency import
        import api
        api_instance = api.Os(self)
        return api_instance

    def file_api(self):
        # circular dependency import
        import api
        api_instance = api.File(self)
        return api_instance


'''
For perm = '664', return 'rw-rw-r--'
'''


def _perm_num_to_str(perm):
    map = ['---', '--x', '-w-', '-wx', 'r--', 'r-x', 'rw-', 'rwx']
    ret = ''
    # special case: '0'
    if perm == '0':
        return '---' * 3
    for nn in perm:
        ret += map[int(nn)]
    return ret


'''
When called as
python -m osv.vm IP get /usr/ ./tmp/

A few exmaples:
# get ./ttt2/fstab ...
python -m osv.vm 192.168.122.89 get /etc  ttt2
python -m osv.vm 192.168.122.89 get /etc/ ttt2

# get ./ttt2/etc/fstab ...
python -m osv.vm 192.168.122.89 get /etc/ ttt2/
python -m osv.vm 192.168.122.89 get /etc  ttt2/

# get ./ttt2/etc/fstab ./tt2/init/30-auto-00 ...
python -m osv.vm 192.168.122.89 get /etc /init/ ttt2/

# list
python -m osv.vm 192.168.122.89 ls     /etc /init
python -m osv.vm 192.168.122.89 ls -la /etc /init

# help
python -m osv.vm -h|--help
python -m osv.vm help get

'''
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('ip', help='VM IP address.')
    parser.add_argument('cmd', choices=['ls', 'get'], help='Command to execute.')
    args, cmd_argv = parser.parse_known_args(sys.argv[1:])  # skip $0 == vm.py filename

    # special case: python -m osv.vm help get
    if args.ip in ['-h', 'help']:
        cmd_argv.insert(0, '--help')
        vm = None
        file_api = None
    else:
        vm = VM.connect_to_existing(args.ip)
        file_api = vm.file_api()

    if args.cmd in ['get']:
        parser2 = argparse.ArgumentParser(prog='osv.vm IP get')
        parser2.add_argument('src', nargs='+', help='VM source file/directory to copy from')
        parser2.add_argument('dest', help='Host destination file/directory to copy to')
        args2 = parser2.parse_args(cmd_argv)

        file_api.download_directory(args2.src, args2.dest)

    elif args.cmd in ['ls']:
        parser2 = argparse.ArgumentParser(prog='osv.vm IP ls')
        parser2.add_argument('-l', dest='long', action='store_true', help='Long listing format')
        parser2.add_argument('-a', dest='all', action='store_true', help='Show . and ..')
        parser2.add_argument('files', nargs='+')
        args2 = parser2.parse_args(cmd_argv)
        header_fmt = '%s:'
        for dir in args2.files:
            if len(args2.files) > 1:
                # print header
                print(header_fmt % dir)
                header_fmt = '\n%s:'

            dir_info = file_api._list_dir(dir)  # _list_dir returns info for dir, but [] for file :/
            if not dir_info:
                # must be file
                file_dirname, file_filename = os.path.split(dir)
                dir_info = file_api._list_dir(file_dirname)
                for dir_info_cur in dir_info:
                    if dir_info_cur['pathSuffix'] == file_filename:
                        # print info, about that file only
                        dir_info = [dir_info_cur]
                        break
            # else:
            #    is a directory, all entries will be consumed

            for di in dir_info:
                name = di['pathSuffix']
                if name in ['.', '..']:
                    if not args2.all:
                        continue
                if args2.long:
                    type = '-'  # FILE
                    if di['type'] == 'DIRECTORY':
                        type = 'd'
                    perm = _perm_num_to_str(di['permission'])
                    replica = di['replication']
                    # accessTime, modificationTime
                    fmt = "%Y-%m-%d %H:%M:%S"
                    tt = datetime.datetime.fromtimestamp(di['modificationTime']).strftime(fmt)
                    length = di['length']
                    print(
                        '%s%s %2d %s %s %6d %s %s' % (type, perm, replica, di['owner'], di['group'], length, tt, name))
                else:
                    print('%s ' % (name))
    # ---------------------------------------------------------------------------------------------
    else:
        print('Invalid commnand: %s', cmd, file=sys.stderr)

##
