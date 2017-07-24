# Copyright (c) 2011 X.commerce, a business unit of eBay Inc.
# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""Implementation of SQLAlchemy backend."""

import json
import collections
import copy
import datetime
import functools
import inspect
import sys
import uuid

from oslo_config import cfg
from oslo_db import api as oslo_db_api
from oslo_db import exception as db_exc
from oslo_db import options as oslo_db_options
from oslo_db.sqlalchemy import enginefacade
from oslo_db.sqlalchemy import update_match
from oslo_db.sqlalchemy import utils as sqlalchemyutils
from oslo_log import log as logging
from oslo_utils import excutils
from oslo_utils import timeutils
from oslo_utils import uuidutils
import six
from six.moves import range
from sqlalchemy import *

CONF = cfg.CONF
LOG = logging.getLogger(__name__)

api_context_manager = enginefacade.transaction_context()


def get_api_engine():
    return api_context_manager.get_legacy_facade().get_engine()


def get_backend():
    """The backend is this module itself."""
    return sys.modules[__name__]


@enginefacade.reader.connection
def instance_get_all(context):
    import pdb
    pdb.set_trace()
    engine = get_api_engine()
    metadata = MetaData(engine, reflect=True)

    instances_table = metadata.tables['instances']    
    instance_extra_table = metadata.tables['instance_extra']

    select_str = select([
        instances_table.c.hostname,
        instances_table.c.task_state,
        instances_table.c.uuid,
        instances_table.c.image_ref,
        instances_table.c.display_name,
        instance_extra_table.c.flavor,
        instances_table.c.availability_zone,
        instances_table.c.host,
        instances_table.c.project_id,
        instances_table.c.user_id,
        instances_table.c.created_at,
        instances_table.c.power_state,
        instances_table.c.vm_state]).select_from(
            instances_table.join(instance_extra_table,
                instances_table.c.uuid==instance_extra_table.c.instance_uuid)).where(
                instances_table.c.project_id == context.project_id)

    instances = context.connection.execute(select_str)
    
    filled_instances = []
    for instance in instances:
    #   status = common.status_from_state(instance['vm_state'], instance['task_state'])
        status = 'ACTIVE' #fake 
        flavor = json.JSONDecoder().decode(instance['flavor'])['cur']['nova_object.data']
        instance = {
            'status':status,
            'name':instance['hostname'],
            'id':instance['uuid'],
            'OS-EXT-STS:power_state':instance['power_state'],
            'OS-EXT-STS:task_state':instance['task_state'],
            'OS-EXT-AZ:availability_zone':instance['availability_zone'],
            'flavor':{
                'disk':flavor['ephemeral_gb'],
                'vcpus':flavor['vcpus'],
                'ram':flavor['memory_mb'],
                'id':flavor['flavorid'],
                'name':flavor['name']},
            'OS-EXT-SRV-ATTR:host':instance['host'],
            'OS-SRV-USG:created_at':instance['created_at'],
            'tenant_id':instance['project_id']}

        filled_instances.append(instance)

    return {'servers':filled_instances}

