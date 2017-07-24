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
from nova import block_device
from nova.compute import task_states
from nova.compute import vm_states


db_opts = [
    cfg.StrOpt('osapi_compute_unique_server_name_scope',
               default='',
               help='When set, compute API will consider duplicate hostnames '
                    'invalid within the specified scope, regardless of case. '
                    'Should be empty, "project" or "global".'),
]

api_db_opts = [
    cfg.StrOpt('connection',
               help='The SQLAlchemy connection string to use to connect to '
                    'the Nova API database.',
               secret=True),
    cfg.BoolOpt('sqlite_synchronous',
                default=True,
                help='If True, SQLite uses synchronous mode.'),
    cfg.StrOpt('slave_connection',
               secret=True,
               help='The SQLAlchemy connection string to use to connect to the'
                    ' slave database.'),
    cfg.StrOpt('mysql_sql_mode',
               default='TRADITIONAL',
               help='The SQL mode to be used for MySQL sessions. '
                    'This option, including the default, overrides any '
                    'server-set SQL mode. To use whatever SQL mode '
                    'is set by the server configuration, '
                    'set this to no value. Example: mysql_sql_mode='),
    cfg.IntOpt('idle_timeout',
               default=3600,
               help='Timeout before idle SQL connections are reaped.'),
    cfg.IntOpt('max_pool_size',
               help='Maximum number of SQL connections to keep open in a '
                    'pool.'),
    cfg.IntOpt('max_retries',
               default=10,
               help='Maximum number of database connection retries '
                    'during startup. Set to -1 to specify an infinite '
                    'retry count.'),
    cfg.IntOpt('retry_interval',
               default=10,
               help='Interval between retries of opening a SQL connection.'),
    cfg.IntOpt('max_overflow',
               help='If set, use this value for max_overflow with '
                    'SQLAlchemy.'),
    cfg.IntOpt('connection_debug',
               default=0,
               help='Verbosity of SQL debugging information: 0=None, '
                    '100=Everything.'),
    cfg.BoolOpt('connection_trace',
                default=False,
                help='Add Python stack traces to SQL as comment strings.'),
    cfg.IntOpt('pool_timeout',
               help='If set, use this value for pool_timeout with '
                    'SQLAlchemy.'),
]

CONF = cfg.CONF
CONF.register_opts(db_opts)
CONF.register_opts(oslo_db_options.database_opts, 'database')
CONF.register_opts(api_db_opts, group='api_database')

LOG = logging.getLogger(__name__)

main_context_manager = enginefacade.transaction_context()
api_context_manager = enginefacade.transaction_context()


def _get_db_conf(conf_group, connection=None):
    kw = dict(
        connection=connection or conf_group.connection,
        slave_connection=conf_group.slave_connection,
        sqlite_fk=False,
        __autocommit=True,
        expire_on_commit=False,
        mysql_sql_mode=conf_group.mysql_sql_mode,
        idle_timeout=conf_group.idle_timeout,
        connection_debug=conf_group.connection_debug,
        max_pool_size=conf_group.max_pool_size,
        max_overflow=conf_group.max_overflow,
        pool_timeout=conf_group.pool_timeout,
        sqlite_synchronous=conf_group.sqlite_synchronous,
        connection_trace=conf_group.connection_trace,
        max_retries=conf_group.max_retries,
        retry_interval=conf_group.retry_interval)
    return kw


def _context_manager_from_context(context):
    if context:
        try:
            return context.db_connection
        except AttributeError:
            pass


def configure(conf):
    main_context_manager.configure(**_get_db_conf(conf.database))
    api_context_manager.configure(**_get_db_conf(conf.api_database))


def create_context_manager(connection=None):
    """Create a database context manager object.

    : param connection: The database connection string
    """
    ctxt_mgr = enginefacade.transaction_context()
    ctxt_mgr.configure(**_get_db_conf(CONF.database, connection=connection))
    return ctxt_mgr


def get_context_manager(context):
    """Get a database context manager object.

    :param context: The request context that can contain a context manager
    """
    return _context_manager_from_context(context) or main_context_manager


def get_engine(use_slave=False, context=None):
    """Get a database engine object.

    :param use_slave: Whether to use the slave connection
    :param context: The request context that can contain a context manager
    """
    ctxt_mgr = _context_manager_from_context(context) or main_context_manager
    return ctxt_mgr.get_legacy_facade().get_engine(use_slave=use_slave)


def get_api_engine():
    return api_context_manager.get_legacy_facade().get_engine()


_SHADOW_TABLE_PREFIX = 'shadow_'
_DEFAULT_QUOTA_NAME = 'default'
PER_PROJECT_QUOTAS = ['fixed_ips', 'floating_ips', 'networks']


def get_backend():
    """The backend is this module itself."""
    return sys.modules[__name__]


def require_context(f):
    """Decorator to require *any* user or admin context.

    This does no authorization for user or project access matching, see
    :py:func:`nova.context.authorize_project_context` and
    :py:func:`nova.context.authorize_user_context`.

    The first argument to the wrapped function must be the context.

    """

    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        #nova.context.require_context(args[0])
        return f(*args, **kwargs)
    return wrapper


def require_instance_exists_using_uuid(f):
    """Decorator to require the specified instance to exist.

    Requires the wrapped function to use context and instance_uuid as
    their first two arguments.
    """
    @functools.wraps(f)
    def wrapper(context, instance_uuid, *args, **kwargs):
        instance_get_by_uuid(context, instance_uuid)
        return f(context, instance_uuid, *args, **kwargs)

    return wrapper


def require_aggregate_exists(f):
    """Decorator to require the specified aggregate to exist.

    Requires the wrapped function to use context and aggregate_id as
    their first two arguments.
    """

    @functools.wraps(f)
    def wrapper(context, aggregate_id, *args, **kwargs):
        aggregate_get(context, aggregate_id)
        return f(context, aggregate_id, *args, **kwargs)
    return wrapper


def select_db_reader_mode(f):
    """Decorator to select synchronous or asynchronous reader mode.

    The kwarg argument 'use_slave' defines reader mode. Asynchronous reader
    will be used if 'use_slave' is True and synchronous reader otherwise.
    If 'use_slave' is not specified default value 'False' will be used.

    Wrapped function must have a context in the arguments.
    """

    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        wrapped_func = safe_utils.get_wrapped_function(f)
        keyed_args = inspect.getcallargs(wrapped_func, *args, **kwargs)

        context = keyed_args['context']
        use_slave = keyed_args.get('use_slave', False)

        if use_slave:
            reader_mode = main_context_manager.async
        else:
            reader_mode = main_context_manager.reader

        with reader_mode.using(context):
            return f(*args, **kwargs)
    return wrapper


def pick_context_manager_writer(f):
    """Decorator to use a writer db context manager.

    The db context manager will be picked from the RequestContext.

    Wrapped function must have a RequestContext in the arguments.
    """
    @functools.wraps(f)
    def wrapped(context, *args, **kwargs):
        ctxt_mgr = get_context_manager(context)
        with ctxt_mgr.writer.using(context):
            return f(context, *args, **kwargs)
    return wrapped


def pick_context_manager_reader(f):
    """Decorator to use a reader db context manager.

    The db context manager will be picked from the RequestContext.

    Wrapped function must have a RequestContext in the arguments.
    """
    @functools.wraps(f)
    def wrapped(context, *args, **kwargs):
        ctxt_mgr = get_context_manager(context)
        with ctxt_mgr.reader.using(context):
            return f(context, *args, **kwargs)
    return wrapped


def pick_context_manager_reader_allow_async(f):
    """Decorator to use a reader.allow_async db context manager.

    The db context manager will be picked from the RequestContext.

    Wrapped function must have a RequestContext in the arguments.
    """
    @functools.wraps(f)
    def wrapped(context, *args, **kwargs):
        ctxt_mgr = get_context_manager(context)
        with ctxt_mgr.reader.allow_async.using(context):
            return f(context, *args, **kwargs)
    return wrapped



def convert_objects_related_datetimes(values, *datetime_keys):
    if not datetime_keys:
        datetime_keys = ('created_at', 'deleted_at', 'updated_at')

    for key in datetime_keys:
        if key in values and values[key]:
            if isinstance(values[key], six.string_types):
                try:
                    values[key] = timeutils.parse_strtime(values[key])
                except ValueError:
                    # Try alternate parsing since parse_strtime will fail
                    # with say converting '2015-05-28T19:59:38+00:00'
                    values[key] = timeutils.parse_isotime(values[key])
            # NOTE(danms): Strip UTC timezones from datetimes, since they're
            # stored that way in the database
            values[key] = values[key].replace(tzinfo=None)
    return values


def _sync_instances(context, project_id, user_id):
    return dict(zip(('instances', 'cores', 'ram'),
                    _instance_data_get_for_user(context, project_id, user_id)))


def _sync_floating_ips(context, project_id, user_id):
    return dict(floating_ips=_floating_ip_count_by_project(
                context, project_id))


def _sync_fixed_ips(context, project_id, user_id):
    return dict(fixed_ips=_fixed_ip_count_by_project(context, project_id))


def _sync_security_groups(context, project_id, user_id):
    return dict(security_groups=_security_group_count_by_project_and_user(
                context, project_id, user_id))


def _sync_server_groups(context, project_id, user_id):
    return dict(server_groups=_instance_group_count_by_project_and_user(
                context, project_id, user_id))

QUOTA_SYNC_FUNCTIONS = {
    '_sync_instances': _sync_instances,
    '_sync_floating_ips': _sync_floating_ips,
    '_sync_fixed_ips': _sync_fixed_ips,
    '_sync_security_groups': _sync_security_groups,
    '_sync_server_groups': _sync_server_groups,
}

###################


def constraint(**conditions):
    return Constraint(conditions)


def equal_any(*values):
    return EqualityCondition(values)


def not_equal(*values):
    return InequalityCondition(values)


class Constraint(object):

    def __init__(self, conditions):
        self.conditions = conditions

    def apply(self, model, query):
        for key, condition in self.conditions.items():
            for clause in condition.clauses(getattr(model, key)):
                query = query.filter(clause)
        return query


class EqualityCondition(object):

    def __init__(self, values):
        self.values = values

    def clauses(self, field):
        # method signature requires us to return an iterable even if for OR
        # operator this will actually be a single clause
        return [or_(*[field == value for value in self.values])]


class InequalityCondition(object):

    def __init__(self, values):
        self.values = values

    def clauses(self, field):
        return [field != value for value in self.values]


###################
@require_context
@pick_context_manager_reader
def my_test(context):
    connection = CONF.database.connection
    engine = get_api_engine()
    metadata = MetaData(engine, reflect=True)
    conn = engine.connect()

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

    instances = conn.execute(select_str)

    filled_instances = []
    for instance in instances:
    #    status = common.status_from_state(instance['vm_state'], instance['task_state'])
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



#######################################

