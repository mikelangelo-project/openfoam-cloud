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
