# Copyright 2015 Red Hat Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import copy

from oslo_config import cfg

opts = [
    cfg.StrOpt('gerrit_user',
               help='Username for connecting to Gerrit.',
               ),
    cfg.StrOpt('ssh_key_file',
               help=('Path to file containing the SSH key for connecting to '
                     'Gerrit.'),
               ),
    cfg.StrOpt('http_password',
               help='HTTP Password for gerrit_user.',
               ),
    cfg.StrOpt('project_file',
               help=('Reviewstats project file listing the projects that the '
                     'tool should be run against.'),
               ),
    cfg.BoolOpt('dryrun',
                default=True,
                help=('When set to True, no changes will actually be '
                      'abandoned.'),
                ),
]

def list_opts():
    return [(None, copy.deepcopy(opts))]
