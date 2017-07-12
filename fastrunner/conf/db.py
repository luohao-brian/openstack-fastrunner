# Copyright 2015 Intel Corporation
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

from oslo_config import cfg

database_group = cfg.OptGroup(
    'database',
    title='Database Options')


ALL_OPTS = [cfg.StrOpt(
    'connection',
    help='Database connection')]


def register_opts(conf):
    conf.register_group(database_group)
    conf.register_opts(ALL_OPTS, group=database_group)


def list_opts():
    return {database_group.name: ALL_OPTS}
