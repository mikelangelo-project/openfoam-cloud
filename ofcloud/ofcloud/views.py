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


import io
import shutil
import tarfile
import tempfile

from django.http import HttpResponse

from ofcloud.models import Instance
from osv.vm import VM


def download_instance_case(request, instance_id):
    instance = Instance.objects.get(pk=instance_id)

    vm = VM.connect_to_existing(instance.ip)
    file_api = vm.file_api()

    temppath = tempfile.mkdtemp()
    print temppath
    file_api.download_directory(['/case'], temppath)

    tar_bytes = io.BytesIO()
    tar = tarfile.open(fileobj=tar_bytes, mode="w:gz")
    tar.add(temppath, arcname="case")
    tar.close()

    shutil.rmtree(temppath)

    response = HttpResponse(tar_bytes.getvalue(), content_type='application/x-gzip')
    response['Content-Disposition'] = 'attachment; filename=%s.tar.gz' % instance.name
    return response


def download_instance_log(request, instance_id):
    instance = Instance.objects.get(pk=instance_id)

    vm = VM.connect_to_existing(instance.ip)
    file_api = vm.file_api()

    content = file_api.get('/case/run.log')

    response = HttpResponse(content)

    return response
