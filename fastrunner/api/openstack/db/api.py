"""Defines interface for DB access.

All functions in this module return objects that implement a dictionary-like
interface. Currently, many of these objects are sqlalchemy objects that
implement a dictionary interface. However, a future goal is to have all of
these objects be simple dictionaries.

"""

from oslo_config import cfg
from oslo_db import concurrency
from oslo_log import log as logging

 
CONF = cfg.CONF

_BACKEND_MAPPING = {'sqlalchemy': 'fastrunner.api.openstack.db.sqlalchemy.api'}

IMPL = concurrency.TpoolDbapiWrapper(CONF, backend_mapping=_BACKEND_MAPPING)

LOG = logging.getLogger(__name__)

# The maximum value a signed INT type may have
MAX_INT = 0x7FFFFFFF



def instance_get_all(context, search_opts):
    """Get all instances."""
    return IMPL.my_test(context)
#    return IMPL.instance_get_all(context)



