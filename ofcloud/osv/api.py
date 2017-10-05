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
'''
REST api to access OSv VM.
'''

import settings
import requests
# import requests.exceptions
import ast
from urllib import urlencode
import logging
from distutils.version import StrictVersion
from time import sleep
import simplejson
import sys
import os
import os.path


class ApiError(Exception):
    pass


class ApiResponseError(ApiError):
    def __init__(self, message, response):
        super(ApiError, self).__init__(message)
        self.response = response


class BaseApi:
    def __init__(self, vm):
        # TODO - why asserts if python -m osv.vm 192.168.122.89 get /usr ./tmp
        # assert(isinstance(vm, VM))
        self.vm = vm
        self.base_path = ''

    def wait_up(self):
        if not self.vm._api_up:
            log = logging.getLogger(__name__)
            self.vm.wait_ip()
            '''
            requests.exceptions.ConnectionError occures if VM is not up yet (stdout/err are not redirected to file, and
            we only blindly set vm._ip to expected static ip.
            '''
            iimax = 50
            for ii in range(1, iimax):
                try:
                    # dummy request, just to wait on service up
                    uri = 'http://%s:%d' % (self.vm._ip, settings.OSV_API_PORT)
                    uri += '/os/uptime'
                    resp = requests.get(uri)
                    self.vm._api_up = True
                    return
                except requests.exceptions.ConnectionError:
                    log.debug('API wait_up requests.exceptions.ConnectionError %d/%d, uri %s', ii, iimax, uri)
                    sleep(0.1)

    def uri(self):
        return 'http://%s:%d' % (self.vm._ip, settings.OSV_API_PORT) + self.base_path

    # kwargs is there only to pass in timeout for requests.get
    def http_get(self, params=None, path_extra='', **kwargs):
        self.wait_up()
        url_all = self.uri() + path_extra
        if params:
            url_all += '?' + urlencode(params)

        resp = requests.get(url_all, **kwargs)
        if resp.status_code != 200:
            raise ApiResponseError('HTTP call failed', resp)
        return resp.content

    # OSv uses data encoded in URL manytimes (more often than POST data).
    def http_post(self, params=None, data=None, path_extra='', **kwargs):
        log = logging.getLogger(__name__)
        self.wait_up()
        url_all = self.uri() + path_extra
        if params:
            url_all += '?' + urlencode(params)
        ## log.debug('http_post %s, data "%s"', url_all, str(data))
        resp = requests.post(url_all, data, **kwargs)
        if resp.status_code != 200:
            raise ApiResponseError('HTTP call failed', resp)
        return resp.content

    def http_put(self, params=None, data=None, path_extra='', **kwargs):
        self.wait_up()
        url_all = self.uri() + path_extra
        if params:
            url_all += '?' + urlencode(params)
        resp = requests.put(url_all, data, **kwargs)
        if resp.status_code != 200:
            raise ApiResponseError('HTTP call failed', resp)
        return resp.content

    def http_delete(self, path_extra='', **kwargs):
        self.wait_up()
        resp = requests.delete(self.uri() + path_extra, **kwargs)
        if resp.status_code != 200:
            raise ApiResponseError('HTTP call failed', resp)
        return resp.content


# line = 'key=value', returns key, value
def env_var_split(line):
    ii = line.find('=')
    kk = line[:ii]
    vv = line[ii + 1:]
    return kk, vv


class EnvAll(BaseApi):
    def __init__(self, vm):
        BaseApi.__init__(self, vm)
        self.base_path = '/env'

    # get all env vars
    def get(self):
        content = self.http_get(path_extra='/')
        arr1 = ast.literal_eval(content)
        arr2 = {}
        for kk_vv in arr1:
            kk, vv = env_var_split(kk_vv)
            arr2[kk] = vv
        return arr2


class Env(BaseApi):
    def __init__(self, vm, name):
        BaseApi.__init__(self, vm)
        self.base_path = '/env/' + name
        self._name = name

    def get(self):
        content = self.http_get()
        # value only, enclosed in ""
        value = content.strip('"')
        return value

    def set(self, value):
        params = {'val': value}
        self.http_post(params)

    # delete return HTTP 200 even if no such var is set
    def delete(self):
        self.http_delete()


class App(BaseApi):
    # name - path to .so to run.
    def __init__(self, vm, name):
        BaseApi.__init__(self, vm)
        self.base_path = '/app/'
        self._name = name

    def run(self):
        assert (self._name)
        params = {'command': self._name}
        self.http_put(params)


def _magic_timeout():
    # older requests lib have a single timeout value, not tuple (2.2.1 vs 2.8.1)
    if StrictVersion(requests.__version__) >= StrictVersion('2.8.1'):
        timeout = (30, 1)
    else:
        timeout = 5
    return timeout


class Os(BaseApi):
    # name - path to .so to run.
    def __init__(self, vm):
        BaseApi.__init__(self, vm)
        self.base_path = '/os/'

    # http call does not return until timeout - VM goes down without closing network socket.
    # VM only prints  'Powering off.' to terminal
    def shutdown(self):
        log = logging.getLogger(__name__)
        log.info('http shutdown VM %s', self.vm._log_name())
        try:
            self.http_post(path_extra='shutdown', timeout=_magic_timeout())
        # TODO what is wrong with that - import in __init__.py, or in tests ?
        # except requests.exceptions.ReadTimeout:
        except Exception as ex:
            log.info('Error should be ReadTimeout, msg %s', ex.message)
            pass

    # VM is down without even printing 'Powering off.'
    def poweroff(self):
        log = logging.getLogger(__name__)
        try:
            self.http_post(path_extra='poweroff', timeout=_magic_timeout())
        # except requests.exceptions.ReadTimeout:
        except Exception as ex:
            log.info('Error should be ReadTimeout, msg %s', ex.message)
            pass


class File(BaseApi):
    """
    List and download directories etc.
    """

    def __init__(self, vm):
        BaseApi.__init__(self, vm)
        self.base_path = '/file/'

    # get file
    def _get_file(self, file_path, dest=None):
        # GET http://192.168.122.37:8000/file/%2Flibtools.so?op=GET
        params = {'op': 'GET'}
        content = self.http_get(params, path_extra=file_path)
        if dest:
            open(dest, 'w').write(content)
        return content

    def _list_dir(self, dir_path):
        # list dir
        # http://192.168.122.37:8000/file/%2F?op=LISTSTATUS
        params = {'op': 'LISTSTATUS'}
        content = self.http_get(params, path_extra=dir_path)
        return simplejson.loads(content)

    def get_dir(self, path, dest):
        log = logging.getLogger(__name__)
        # list dir, get it recursively
        # TODO - symlinks
        log.info('Downloading VM dir %s', path)
        if not os.path.exists(dest):
            log.info('host mkdir %s', dest)
            os.mkdir(dest)
        dir_content = self._list_dir(path)
        for entry in dir_content:
            if entry['type'] == 'DIRECTORY':
                subdir_name = entry['pathSuffix']
                if subdir_name in ['.', '..']:
                    continue
                if path == '/' and subdir_name in ['dev', 'proc']:
                    # do not 'download' /dev/urandom etc
                    dev_dir = os.path.join(dest, subdir_name)
                    if os.path.exists(dev_dir):
                        os.removedirs(dev_dir)
                    log.info('Only mkdir %s on destination side', dev_dir)
                    os.mkdir(dev_dir)
                    continue
                log.debug('Recurse in dir %s', os.path.join(path, subdir_name))
                self.get_dir(os.path.join(path, subdir_name), os.path.join(dest, subdir_name))
            elif entry['type'] == 'FILE':
                file_name = entry['pathSuffix']
                log.debug('GET file %s/%s', path, file_name)
                self._get_file(os.path.join(path, file_name), os.path.join(dest, file_name))
            else:
                log.error('Unknown type %s (json data %s)', entry['type'], simplejson.dumps(entry))

    '''
    Copy file or directory from VM at path src, to host to path dest.
    '''

    def get(self, src, dest=None):
        params = {'op': 'LISTSTATUS'}
        try:
            content = self.http_get(params, path_extra=src)
            if content == '[]':
                # src is file, not directory
                return self._get_file(src, dest)
            else:
                # src is directory
                self.get_dir(src, dest)
        except ApiResponseError:
            print('The src "%s" does not exist', src, file=sys.stderr)
            raise

        return None

    def download_directory(self, src, dest):
        # multiple src files/directories, dest should be a dir.
        # or dest ends with '/' - cp to dir was requested
        dest_is_dir = len(src) > 1 or dest.endswith(os.path.sep)
        if dest_is_dir:
            if os.path.exists(dest):
                if os.path.isdir(dest):
                    pass  # all ok
                else:
                    print('Destination %s is exists, but is not a directory', dest, file=sys.stderr)
                    exit(1)
            else:
                os.mkdir(dest)
        for src in src:
            src_filename = os.path.split(src.rstrip(os.path.sep))[1]  # name of src file or directory
            if dest_is_dir:
                dest_filename = os.path.join(dest, src_filename)  # name of dest file or directory
            else:
                dest_filename = dest
            self.get(src, dest_filename)

##
