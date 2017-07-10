from oslo_log import log as logging

LOG = logging.getLogger(__name__)

from sqlalchemy import *
import redis

from oslo_service import service as os_service
from oslo_service import threadgroup

class SyncService(os_service.Service):
    def __init__(self, *args, **kwargs):
        super(SyncService, self).__init__(*args, **kwargs)
        self.tg = threadgroup.ThreadGroup()

    def start(self):
        self.tg.add_dynamic_timer(self.sync_data, periodic_interval_max=60)

    def sync_data(self):
	LOG.info("=============== mysql2redis sync started: ===============")
       
        r_redis = redis.StrictRedis(host='localhost', port=6379, db=0)
        LOG.info("redis connected!")

        engine = create_engine('mysql://nova:redhat@localhost:3306/nova', echo=False)
        metadata = MetaData(engine, reflect=True)
        conn = engine.connect()

        table = metadata.tables['instances']

        select_str = select([table])
        result = conn.execute(select_str)
        table_name = "instances"
        
        for row in result:
            uuid = row['uuid']
            r_redis.hmset("%s:%s" %(table_name, uuid), {
                'created_at':row['created_at'],
                'updated_at':row['updated_at'],
                'user_id':row['user_id'],
                'project_id':row['project_id'],
                'image_ref':row['image_ref'],
                'kernel_id':row['kernel_id'],
                'ramdisk_id':row['ramdisk_id'],
                'memory_mb':row['memory_mb'],
                'vcpus':row['vcpus'],
                'power_state':row['power_state'],
                'vm_state':row['vm_state'],
                'hostname':row['hostname'],
                'display_name':row['display_name'],
                'availability_zone':row['availability_zone'],
                'os_type':row['os_type'],
                'vm_mode':row['vm_mode'],
                'uuid':row['uuid'],
                'access_ip_v4':row['access_ip_v4']})


        #get all project_ids
        projects = conn.execute('select distinct project_id from instances;')
        for project_id in projects:
            uuids = conn.execute('select uuid from instances where project_id="%s"' %(project_id[0]))
            for uuid in uuids:
                r_redis.sadd("projects:%s" %(project_id[0]), uuid[0])


        LOG.info("=============mysql2redis sync end==========")
        conn.close()

