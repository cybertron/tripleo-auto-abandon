#!/usr/bin/env python
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

import calendar
import datetime
import json

from oslo_config import cfg
import requests
from requests import auth
from reviewstats import utils

from tripleo_auto_abandon import _opts

WARN_MSG = ('TripleO Review Cleanup Bot\n\n'
            'This change has had unaddressed negative feedback for a '
            'significant period of time. If the feedback is not dealt with '
            'through a comment or new patch set, the change will be '
            'automatically abandoned. Note that if this happens you will '
            'still be able to restore the change if you wish to continue '
            'working on it.'
            )
AB_MSG = ('TripleO Review Cleanup Bot\n\n'
          'This change has had unaddressed negative feedback for more than '
          'one month. It is being automatically abandoned by this cleanup '
          'job. Please feel free to restore the change if you wish to '
          'continue working on it.\n\n'
          'For more details, see [insert URL here]'
          )
ABANDON_DAYS = 31

CONF = cfg.CONF
CONF.register_opts(_opts.opts)


def load_config():
    CONF(['--config-file', 'auto-abandon.conf'])


def _dry_run_msg(url, data):
    return ("DRY RUN: POST %s DATA: %s" %(url, data))


def purty_print(msg):
    try:
        msg = msg.text
    except Exception:
        pass
    time_stamp = datetime.datetime.now().isoformat()
    print "%s: %s " %(time_stamp, msg)


def get_changes():
    #with open('changes.json') as f:
    #    return json.loads(f.read())
    projects = utils.get_projects_info(CONF.project_file)

    return utils.get_changes(projects, CONF.gerrit_user, CONF.ssh_key_file,
                             only_open=True)


def warn(change_id, revision_id):
    url = ('https://review.openstack.org/a/changes/%s/revisions/%s/review' %
           (change_id, revision_id))
    data = {'message': WARN_MSG}
    if CONF.dryrun:
        response = _dry_run_msg(url, data)
    else:
        response = requests.post(url, json=data,
                                 auth=auth.HTTPDigestAuth(CONF.gerrit_user,
                                                          CONF.http_password))
    purty_print(response)


def abandon(change_id):
    url = ('https://review.openstack.org/a/changes/%s/abandon' %
           change_id)
    data = {'message': AB_MSG}
    if CONF.dryrun:
        response = _dry_run_msg(url, data)
    else:
        response = requests.post(url, json=data,
                                 auth=auth.HTTPDigestAuth(CONF.gerrit_user,
                                                          CONF.http_password))
    purty_print(response)


def days_since_negative_feedback(approvals, now_ts):
    """Check for reviews with unaddressed negative feedback

    This is defined as any negative review that was not followed up by a new
    patch set or a non-negative comment (to allow for committers to respond to
    feedback). A Failed CI pass is also considered unaddressed negative
    feedback, regardless of any subsequent reviews.

    Returns 0 if there is no unaddressed negative feedback.  Otherwise returns
    the number of days since the unaddressed negative feedback was posted.

    :param approvals: list of gerrit approvals for the latest patch set of
        the change.
    :param now_ts: The current timestamp, in seconds.
    """
    negative_feedback = False
    failed_ci = False

    for review in approvals:
        if review['type'] == 'Verified':
            if int(review['value']) < 0:
                failed_ci = review
            else:
                failed_ci = None
        if review['type'] == 'Code-Review':
            if int(review['value']) < 0:
                negative_feedback = review
            else:
                negative_feedback = None
    if not negative_feedback and not failed_ci:
        return 0
    if negative_feedback and failed_ci:
        oldest_negative = min(negative_feedback['grantedOn'],
                            failed_ci['grantedOn'])
    else:
        oldest_negative = (negative_feedback['grantedOn']
                            if negative_feedback
                            else failed_ci['grantedOn'])
    age = now_ts - oldest_negative
    # The timestamps are in seconds
    days = age / (60 * 60 * 24)
    return days


def process_changes(changes):
    now = datetime.datetime.utcnow()
    # NOTE(bnemec): This is only used in days_since_negative_feedback,
    # but there's no sense recalculating it every iteration through the loop.
    now_ts = calendar.timegm(now.timetuple())
    for change in changes:
        if utils.is_workinprogress(change):
            continue
        # NOTE(bnemec): I think Gerrit already returns patch sets sorted, but
        # it won't hurt to make sure.
        change['patchSets'].sort(key=lambda a: int(a['number']))
        last_patchset = change['patchSets'][-1]
        if utils.patch_set_approved(last_patchset):
            continue
        approvals = last_patchset.get('approvals', [])
        if not approvals:
            continue
        approvals.sort(key=lambda a: a['grantedOn'])
        # This most likely means the change was abandoned and restored
        # since the last vote.  Let's not abandon it again.
        if change['lastUpdated'] > approvals[-1]['grantedOn']:
            continue
        days = days_since_negative_feedback(approvals, now_ts)



        #warn(change['id'], last_patchset['revision'])



        if days > ABANDON_DAYS:
            purty_print('Abandoning %s - %s' %
                        (change['url'],
                         change['commitMessage'].split('\n')[0]))
            abandon(change['id'])
        # NOTE(bnemec): This probably complicates things too much.  We'd have
        # to check that we haven't already commented on the patch set, and
        # I'm not sure the return on investment is worth it.
        #elif days > 24:
            #print 'Warning %s' % change['url']
            #warn(change['id'], last_patchset['revision'])


def main():
    load_config()
    changes = get_changes()

    #with open('changes.json', 'w') as f:
    #    f.write(json.dumps(changes))
    #changes = [c for c in changes if c['id'] == 'Icffa80719841291de3a05f6439925a8d068d36eb']
    #print changes

    process_changes(changes)


if __name__ == '__main__':
    main()
