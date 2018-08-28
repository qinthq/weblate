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
from time import perf_counter

import requests
from similar_text import similar_text
from fuzzywuzzy import fuzz

from django.conf import settings

from weblate.lang.models import Language
from weblate.logger import LOGGER
from weblate.memory.storage import TranslationMemory
from weblate.machinery.base import MachineTranslation


def update_index(unit):
    try:
        r = requests.put(
            '{}/weblate_tm/{}/{}'.format(
                settings.MT_ES_URL, 'weblate_trans', unit.pk
            ),
            json={'source': unit.source, 'target': unit.target},
            timeout=20,
        )
        r.raise_for_status()
    except Exception:
        LOGGER.exception(
            'Ignoring failed index update to ES URL="%s": %s',
            settings.MT_ES_URL, r.text
        )


class ESTranslation(MachineTranslation):
    """Translation service using strings already translated in Weblate."""
    name = 'Elasticsearch Translation Memory'
    rank_boost = 1
    cache_translations = False

    def convert_language(self, language):
        return Language.objects.get(code=language)

    def is_supported(self, source, language):
        """Any language is supported."""
        return True

    def format_unit_match(self, text, target, similarity, origin):
        """Format match to translation service result."""
        return (
            target,
            similarity,
            '{0} ({1})'.format(
                self.name,
                origin,
            ),
            text,
        )

    def download_translations(self, source, language, text, unit, user):
        """Download list of possible translations from a service."""
        start = perf_counter()

        es_search_url = '{}/{}/_search'.format(
            settings.MT_ES_URL, 'weblate_tm'
        )
        try:
            r = requests.get(
                es_search_url,
                json={'query': {'match': {'source': text}}},
                timeout=20,
            )
            r.raise_for_status()
            res_ = r.json()
        except requests.exceptions.HTTPError:
            LOGGER.error(
                'Querying Elasticsearch: "%s" failed.', es_search_url
            )
            raise
        LOGGER.info('Querying ES server:%s', perf_counter()-start)

        max_score = res_['hits']['max_score']
        max_result = [
            u for u in res_['hits']['hits']
            if u['_score'] == max_score
        ][0]

        start_ = perf_counter()
        # max_similarity = similar_text(max_result['_source']['source'], text)
        max_similarity = fuzz.partial_ratio(
            max_result['_source']['source'], text
        )
        LOGGER.info('Getting ES similar_text():%s', perf_counter()-start_)

        for u in res_['hits']['hits']:
            source = u['_source']
            u['similarity'] = round(
                (max_similarity*u['_score'])/max_score, 2
            )

        results = [
            self.format_unit_match(
                u['_source']['source'],
                u['_source']['target'],
                u['similarity'],
                u['_type'],
            ) for u in res_['hits']['hits']
        ]
        LOGGER.info('Getting ES results:%s', perf_counter()-start)
        return results
