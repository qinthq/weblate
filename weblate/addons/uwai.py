# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2018 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

from __future__ import unicode_literals
import os
from time import perf_counter

import requests
import yaml
from django.utils.translation import ugettext_lazy as _

from weblate.addons.base import BaseAddon
from weblate.addons.events import EVENT_UNIT_POST_SAVE
from weblate.logger import LOGGER as logger
from weblate.utils.state import STATE_APPROVED


class PlatformHookAddon(BaseAddon):
    # List of events addon should receive
    events = (EVENT_UNIT_POST_SAVE,)

    # Addon unique identifier
    name = 'weblate.addons.platform_hook'

    # Verbose name shown in the user interface
    verbose = _('UWAI Addon')

    # Detailed addon description
    description = _(
        'This addon provides extra features for UWAI services.'
    )

    PLATFORM_NOTIFY_URL = os.getenv('PLATFORM_NOTIFY_URL')

    # Callback to implement custom behavior
    def unit_post_save(self, unit, created):
        start = perf_counter()
        if created or unit.state != STATE_APPROVED:
            return

        # Invalidate cached stats before getting.
        unit.translation.stats.invalidate()
        stats = unit.translation.get_stats()
        logger.info('Invalidating cache: %s', perf_counter()-start)

        is_approved = int(unit.translation.stats.approved_percent) == 100
        is_translated = int(stats.get('translated_percent', 0)) == 100
        is_fuzzy = int(stats.get('fuzzy_percent', 0)) == 100

        # do_push() causes another unit.save() signal; disregard the event by
        # checking if unit is pending.
        is_pending = unit.pending

        if is_approved and is_translated and not is_fuzzy and is_pending:
            # Need to commit pending before reading translation file.
            # Read translation file before pushing to ignore repo.lock.
            unit.translation.component.commit_pending(
                request=None, from_link=True, skip_push=True
            )

            # Get translation file.
            start_ = perf_counter()
            trans_filename = unit.translation.get_filename()
            with open(trans_filename) as handle:
                try:
                    translations = yaml.safe_load(handle.read())
                except yaml.YAMLError:
                    logger.error(
                        'Unable to open yaml file: %s', trans_filename
                    )
                    raise
            logger.info('Loading yaml file: %s', perf_counter()-start_)

            # Push local changes before doing webhook to UWAI Platform.
            start_ = perf_counter()
            unit.translation.do_push(force_commit=False)
            logger.info('Pushing local changes: %s', perf_counter()-start_)

            # Save changes to translation file; otherwise, result of getting
            # translations is not updated.
            start_ = perf_counter()
            unit.translation.store.save()
            logger.info('Saving changes to file: %s', perf_counter()-start_)

            start_ = perf_counter()
            site_id, _ = os.path.splitext(
                os.path.split(unit.translation.filename)[-1]
            )
            try:
                r = requests.post(
                    self.PLATFORM_NOTIFY_URL,
                    json={
                        'site_id': site_id,
                        'translations': translations,
                        'project': unit.translation.component.project.name
                    },
                    timeout=20,
                    # WANT: Optionally add extra headers to check
                    # coming from Weblate. (e.g. X-WEBLATE: <val>)
                )
                r.raise_for_status()
            except requests.exceptions.HTTPError:
                logger.exception(
                    'Call to UWAI Platform failed: %s', r.text
                )
            logger.info(
                'Sending webhook to Platform: %s', perf_counter()-start_
            )
        return
