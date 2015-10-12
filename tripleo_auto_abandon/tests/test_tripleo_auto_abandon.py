# -*- coding: utf-8 -*-

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

"""
test_tripleo_auto_abandon
----------------------------------

Tests for `tripleo_auto_abandon` module.
"""
import copy

import mock
from oslo_config import fixture as config_fixture

from tripleo_auto_abandon import auto_abandon
from tripleo_auto_abandon.tests import base

USER='foo'
KEY_FILE='/dev/null'
HTTP_PASSWORD='bar'
PROJECT_FILE='/top/secret.json'


class TestAutoAbandon(base.TestCase):
    def setUp(self):
        super(TestAutoAbandon, self).setUp()
        conf = config_fixture.Config()
        self.useFixture(conf)
        conf.config(gerrit_user=USER, ssh_key_file=KEY_FILE,
                    http_password=HTTP_PASSWORD,
                    project_file=PROJECT_FILE, dryrun=False)

    @mock.patch('reviewstats.utils.get_projects_info')
    @mock.patch('reviewstats.utils.get_changes')
    def test_get_changes(self, mock_get_changes, mock_get_projects_info):
        mock_projects = mock.Mock()
        mock_get_projects_info.return_value = mock_projects
        auto_abandon.get_changes()
        mock_get_projects_info.assert_called_with(PROJECT_FILE)
        mock_get_changes.assert_called_with(mock_projects, USER,
                                            KEY_FILE, only_open=True)

    @mock.patch('requests.auth.HTTPDigestAuth')
    @mock.patch('requests.post')
    def test_warn(self, mock_post, mock_auth):
        mock_auth_obj = mock.Mock()
        mock_auth.return_value = mock_auth_obj
        auto_abandon.warn('123', 'abc')
        data = {'message': auto_abandon.WARN_MSG}
        mock_auth.assert_called_with(USER, HTTP_PASSWORD)
        mock_post.assert_called_with(
            'https://review.openstack.org/a/changes/123/revisions/abc/review',
            json=data,
            auth=mock_auth_obj
            )

    @mock.patch('requests.auth.HTTPDigestAuth')
    @mock.patch('requests.post')
    def test_abandon(self, mock_post, mock_auth):
        mock_auth_obj = mock.Mock()
        mock_auth.return_value = mock_auth_obj
        auto_abandon.abandon('123')
        data = {'message': auto_abandon.AB_MSG}
        mock_auth.assert_called_with(USER, HTTP_PASSWORD)
        mock_post.assert_called_with(
            'https://review.openstack.org/a/changes/123/abandon',
            json=data,
            auth=mock_auth_obj
            )

    @mock.patch('tripleo_auto_abandon.auto_abandon.process_changes')
    @mock.patch('tripleo_auto_abandon.auto_abandon.get_changes')
    @mock.patch('tripleo_auto_abandon.auto_abandon.load_config')
    def test_main(self, mock_load_config, mock_get_changes,
                  mock_process_changes):
        mock_get_changes.return_value = mock.Mock()
        auto_abandon.main()
        self.assertTrue(mock_load_config.called)
        mock_process_changes.assert_called_with(mock_get_changes.return_value)


FAKE_CHANGE = {
    'patchSets': [
        {'approvals': [],
         'number': '1'}
    ],
    'status': 'NEW',
    'id': 'fake-id',
    'url': 'https://fake-url',
    'lastUpdated': 10,
    'commitMessage': 'Fake commit message',
}
BASE_TS = 100
ONE_DAY = 60 * 60 * 24
FAKE_MINUS_ONE = {
    'grantedOn': BASE_TS,
    'type': 'Code-Review',
    'value': -1,
}
FAKE_PLUS_ONE = {
    'grantedOn': BASE_TS,
    'type': 'Code-Review',
    'value': 1,
}
FAKE_MINUS_TWO = {
    'grantedOn': BASE_TS,
    'type': 'Code-Review',
    'value': -2,
}
FAKE_PLUS_TWO = {
    'grantedOn': BASE_TS,
    'type': 'Code-Review',
    'value': 2,
}
FAKE_COMMENT = {
    'grantedOn': BASE_TS + 10,
    'type': 'Code-Review',
    'value': 0,
}
FAKE_FAILED_CI = {
    'grantedOn': BASE_TS,
    'type': 'Verified',
    'value': -1,
}
FAKE_PASSED_CI = {
    'grantedOn': BASE_TS + 10,
    'type': 'Verified',
    'value': 1,
}


class TestProcessChanges(base.TestCase):
    @mock.patch('reviewstats.utils.patch_set_approved')
    @mock.patch('reviewstats.utils.is_workinprogress')
    def test_wip(self, mock_is_wip, mock_psa):
        mock_is_wip.return_value = True
        auto_abandon.process_changes([FAKE_CHANGE])
        # We should have bailed after the WIP check
        self.assertTrue(mock_is_wip.called)
        self.assertFalse(mock_psa.called)

    @mock.patch('reviewstats.utils.patch_set_approved')
    @mock.patch('reviewstats.utils.is_workinprogress')
    def test_approved(self, mock_is_wip, mock_psa):
        change = copy.deepcopy(FAKE_CHANGE)
        change['patchSets'] = [mock.MagicMock()]
        mock_is_wip.return_value = False
        mock_psa.return_value = True
        auto_abandon.process_changes([change])
        self.assertTrue(mock_is_wip.called)
        self.assertTrue(mock_psa.called)
        self.assertFalse(change['patchSets'][0].get.called)

    @mock.patch(
        'tripleo_auto_abandon.auto_abandon.days_since_negative_feedback')
    @mock.patch('reviewstats.utils.patch_set_approved')
    @mock.patch('reviewstats.utils.is_workinprogress')
    def test_no_approvals(self, mock_is_wip, mock_psa, mock_days):
        mock_is_wip.return_value = False
        mock_psa.return_value = False
        auto_abandon.process_changes([FAKE_CHANGE])
        self.assertTrue(mock_is_wip.called)
        self.assertTrue(mock_psa.called)
        self.assertFalse(mock_days.called)

    @mock.patch('tripleo_auto_abandon.auto_abandon.abandon')
    @mock.patch(
        'tripleo_auto_abandon.auto_abandon.days_since_negative_feedback')
    def test_abandon_after_expiration(self, mock_days, mock_abandon):
        change = copy.deepcopy(FAKE_CHANGE)
        change['patchSets'][0]['approvals'] = [FAKE_MINUS_ONE]
        mock_days.return_value = auto_abandon.ABANDON_DAYS + 1
        auto_abandon.process_changes([change])
        mock_abandon.assert_called_once_with('fake-id')

    @mock.patch('tripleo_auto_abandon.auto_abandon.abandon')
    @mock.patch(
        'tripleo_auto_abandon.auto_abandon.days_since_negative_feedback')
    def test_not_abandon_less_than_expiration(self, mock_days, mock_abandon):
        change = copy.deepcopy(FAKE_CHANGE)
        change['patchSets'][0]['approvals'] = [FAKE_MINUS_ONE]
        mock_days.return_value = auto_abandon.ABANDON_DAYS
        auto_abandon.process_changes([change])
        self.assertFalse(mock_abandon.called)

    @mock.patch(
        'tripleo_auto_abandon.auto_abandon.days_since_negative_feedback')
    def test_ignore_restored(self, mock_days):
        change = copy.deepcopy(FAKE_CHANGE)
        change['lastUpdated'] = BASE_TS + 100
        change['patchSets'][0]['approvals'] = [FAKE_MINUS_ONE]
        auto_abandon.process_changes([change])
        self.assertFalse(mock_days.called)

    def _test_multiple_patch_sets(self, mock_timegm, mock_abandon, good, bad,
                                  should_abandon):
        # 33 instead of 32 because the bad patch set happens after BASE_TS,
        # and due to rounding it ends up looking one full day newer.
        mock_timegm.return_value = BASE_TS + ONE_DAY * 33
        good_patchset = {'approvals': [], 'number': good}
        good_patchset['lastUpdated'] = BASE_TS + 50 * (int(good) - 1)
        fake_pos = copy.deepcopy(FAKE_PLUS_ONE)
        fake_pos['grantedOn'] = good_patchset['lastUpdated']
        good_patchset['approvals'] = [fake_pos]

        bad_patchset = {'approvals': [], 'number': bad}
        bad_patchset['lastUpdated'] = BASE_TS + 50 * (int(bad) - 1)
        fake_neg = copy.deepcopy(FAKE_MINUS_ONE)
        fake_neg['grantedOn'] = bad_patchset['lastUpdated']
        bad_patchset['approvals'] = [fake_neg]

        patchsets = [bad_patchset, good_patchset]
        change = copy.deepcopy(FAKE_CHANGE)
        change['patchSets'] = patchsets
        auto_abandon.process_changes([change])
        self.assertEqual(should_abandon, mock_abandon.called)

    @mock.patch('tripleo_auto_abandon.auto_abandon.abandon')
    @mock.patch('calendar.timegm')
    def test_multiple_patch_sets_bad(self, mock_timegm, mock_abandon):
        self._test_multiple_patch_sets(mock_timegm, mock_abandon, '1', '2',
                                       True)

    @mock.patch('tripleo_auto_abandon.auto_abandon.abandon')
    @mock.patch('calendar.timegm')
    def test_multiple_patch_sets_good(self, mock_timegm, mock_abandon):
        self._test_multiple_patch_sets(mock_timegm, mock_abandon, '2', '1',
                                       False)


class TestDaysCalculation(base.TestCase):
    def test_no_negative_feedback(self):
        approvals = [FAKE_COMMENT]
        fake_ts = BASE_TS + ONE_DAY
        self.assertEqual(0,
                         auto_abandon.days_since_negative_feedback(approvals,
                                                                   fake_ts))

    def test_positive_feedback(self):
        approvals = [FAKE_PLUS_ONE]
        fake_ts = BASE_TS + ONE_DAY
        self.assertEqual(0,
                         auto_abandon.days_since_negative_feedback(approvals,
                                                                   fake_ts))

    def test_negative_feedback(self):
        approvals = [FAKE_MINUS_ONE]
        fake_ts = BASE_TS + ONE_DAY
        self.assertEqual(1,
                         auto_abandon.days_since_negative_feedback(approvals,
                                                                   fake_ts))

    def test_negative_feedback_response(self):
        approvals = [FAKE_MINUS_ONE, FAKE_COMMENT]
        fake_ts = BASE_TS + ONE_DAY * 10
        self.assertEqual(0,
                         auto_abandon.days_since_negative_feedback(approvals,
                                                                   fake_ts))

    def test_negative_feedback_response_two(self):
        approvals = [FAKE_MINUS_TWO, FAKE_COMMENT]
        fake_ts = BASE_TS + ONE_DAY * 10
        self.assertEqual(0,
                         auto_abandon.days_since_negative_feedback(approvals,
                                                                   fake_ts))

    def test_positive_negative(self):
        fake_neg = copy.deepcopy(FAKE_MINUS_ONE)
        fake_neg['grantedOn'] = BASE_TS + 10
        approvals = [FAKE_PLUS_ONE, fake_neg]
        fake_ts = fake_neg['grantedOn'] + ONE_DAY
        self.assertEqual(1,
                         auto_abandon.days_since_negative_feedback(approvals,
                                                                   fake_ts))

    def test_positive_negative_two(self):
        fake_neg = copy.deepcopy(FAKE_MINUS_TWO)
        fake_neg['grantedOn'] = BASE_TS + 10
        approvals = [FAKE_PLUS_TWO, fake_neg]
        fake_ts = fake_neg['grantedOn'] + ONE_DAY
        self.assertEqual(1,
                         auto_abandon.days_since_negative_feedback(approvals,
                                                                   fake_ts))

    def test_failed_ci(self):
        ci_fail = copy.deepcopy(FAKE_FAILED_CI)
        ci_fail['grantedOn'] = BASE_TS - 10
        approvals = [FAKE_PLUS_ONE, FAKE_PLUS_TWO, ci_fail]
        fake_ts = ci_fail['grantedOn'] + ONE_DAY
        self.assertEqual(1,
                         auto_abandon.days_since_negative_feedback(approvals,
                                                                   fake_ts))

    def test_recheck(self):
        approvals = [FAKE_FAILED_CI, FAKE_PASSED_CI]
        fake_ts = FAKE_PASSED_CI['grantedOn'] + ONE_DAY
        self.assertEqual(0,
                         auto_abandon.days_since_negative_feedback(approvals,
                                                                   fake_ts))

    def test_negative_and_failed_ci(self):
        fake_neg = copy.deepcopy(FAKE_MINUS_ONE)
        fake_neg['grantedOn'] = BASE_TS + 10
        approvals = [FAKE_FAILED_CI, fake_neg]
        fake_ts = BASE_TS + ONE_DAY
        self.assertEqual(1,
                         auto_abandon.days_since_negative_feedback(approvals,
                                                                   fake_ts))

