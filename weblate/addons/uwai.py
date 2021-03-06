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

import requests
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
        if created or unit.state != STATE_APPROVED:
            return

        stats = unit.translation.get_stats()
        is_approved = int(unit.translation.stats.approved_percent) == 100
        is_translated = int(stats.get('translated_percent', 0)) == 100
        is_fuzzy = int(stats.get('fuzzy_percent', 0)) == 100

        if is_approved and is_translated and not is_fuzzy:
            site_id, _ = os.path.splitext(
                os.path.split(unit.translation.filename)[-1]
            )
            try:
                r = requests.post(
                    self.PLATFORM_NOTIFY_URL,
                    json={'site_id': site_id},
                    # WANT: Optionally add extra headers to check
                    # coming from Weblate. (e.g. X-WEBLATE: <val>)
                )
                r.raise_for_status()
            except requests.exceptions.HTTPError:
                logger.exception(
                    'Call to UWAI Platform failed: %s', r.text
                )
        return
