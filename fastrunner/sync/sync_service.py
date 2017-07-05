from oslo_log import log as logging

LOG = logging.getLogger(__name__)

from oslo_service import service as os_service
from oslo_service import threadgroup

class SyncService(os_service.Service):
    def __init__(self, *args, **kwargs):
        super(SyncService, self).__init__(*args, **kwargs)
        self.tg = threadgroup.ThreadGroup()

    def start(self):
        self.tg.add_dynamic_timer(self.sync_data, periodic_interval_max=60)

    def sync_data(self):
        LOG.info("===============TODO: sync===============")


