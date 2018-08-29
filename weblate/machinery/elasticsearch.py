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

import requests
from fuzzywuzzy import fuzz

from django.conf import settings

from weblate.logger import LOGGER
from weblate.machinery.base import MachineTranslation


def update_source_unit_index(unit):
    try:
        r = requests.put(
            '{}/weblate/{}/{}'.format(
                settings.MT_ES_URL, 'translations', unit.pk
            ),
            json={'source': unit.source, 'target': unit.target},
            timeout=20,
        )
        r.raise_for_status()
    except Exception:
        LOGGER.exception(
            'Ignoring failed index update to Elasticsearch="%s": %s',
            settings.MT_ES_URL, r.text
        )


class ESTranslation(MachineTranslation):
    """Elasticsearch machine translation support."""
    name = 'Elasticsearch'
    rank_boost = 3
    cache_translations = False

    def is_supported(self, source, language):
        """Any language is supported."""
        return True

    def compute_ratio(self, trans, text):
        """Compute ratio for getting relative similarity with each results.

        Elasticsearch score can't be easily converted to percentage which
        Weblate uses to show as "quality" of the result. Use fuzzywuzzy module
        to compute for similarity of the max result and use as basis for
        getting similarity of other results.

        fuzzywuzzy return similarity is between 0-100.
        """
        max_score = trans['hits']['max_score']
        max_result = next(
            filter(lambda t: t['_score'] == max_score, trans['hits']['hits'])
        )
        max_similarity = fuzz.token_set_ratio(
            max_result['_source']['source'], text
        )
        return max_similarity/max_score

    def get_search_results(self, text):
        try:
            r = requests.get(
                '{}/weblate/_search'.format(settings.MT_ES_URL),
                json={'query': {'match': {'source': text}}},
                timeout=20,
            )
            r.raise_for_status()
        except requests.exceptions.HTTPError:
            LOGGER.error(
                'Getting results from Elasticsearch="%s" failed.',
                settings.MT_ES_URL
            )
            raise
        return r.json()

    def download_translations(self, source, language, text, unit, user):
        """Download list of possible translations from a service."""
        trans = self.get_search_results(text)
        ratio = self.compute_ratio(trans, text)

        translations = []
        for t in trans['hits']['hits']:
            try:
                source = t['_source']['source']
                target = t['_source']['target']
            except KeyError as e:
                LOGGER.error(
                    'Key "%s" not found in Elasticsearch results.',
                    e.args[0]
                )
                raise ValueError('Invalid Elasticsearch Schema.')
            translations.append((
                target,
                '{0:.2f}'.format(t['_score']*ratio),
                '{0} ({1})'.format(self.name, t['_type']),
                source,
            ))
        return translations
