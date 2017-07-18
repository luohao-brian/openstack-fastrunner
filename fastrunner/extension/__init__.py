
from oslo_utils import importutils


def _get_compute_api_class_name():
    """Returns the name of compute API class."""
    return 'fastrunner.extension.api.API'

def API(*args, **kwargs):
    class_name = _get_compute_api_class_name()
    return importutils.import_object(class_name, *args, **kwargs)

