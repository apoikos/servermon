# -*- coding: utf-8 -*- vim:fileencoding=utf-8:
# vim: tabstop=4:shiftwidth=4:softtabstop=4:expandtab

# Copyright © 2010-2012 Greek Research and Technology Network (GRNET S.A.)
#
# Permission to use, copy, modify, and/or distribute this software for any
# purpose with or without fee is hereby granted, provided that the above
# copyright notice and this permission notice appear in all copies.
#
# THE SOFTWARE IS PROVIDED "AS IS" AND ISC DISCLAIMS ALL WARRANTIES WITH REGARD
# TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND
# FITNESS. IN NO EVENT SHALL ISC BE LIABLE FOR ANY SPECIAL, DIRECT, INDIRECT,
# OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS OF
# USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER
# TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR PERFORMANCE
# OF THIS SOFTWARE.

'''
Module contains functions for performing searches in hwdoc

Important function here is search(q) which searches strings or iterables of
strings in model Equipment. get_search_terms(text) is a function tokenizing a
text and return a Set of tokens for use by search(q). canonicalize_mac(key) is
a function taken as MAC address as a string and returning it in the proper
format for search(q)
'''

from servermon.hwdoc.models import Equipment, ServerManagement
from django.db.models import Q
from socket import gethostbyaddr, herror, gaierror, error
from whoosh.analysis import SpaceSeparatedTokenizer, StopFilter
from django.utils.translation import ugettext as _
from django.conf import settings
import re

def canonicalize_mac(key):
    '''
    Accepts a MAC in various formats and returns at form aa:bb:cc:dd:ee:ff

    @type  key: string
    @param key: the MAC to canonicalize

    @rtype: string
    @return: The MAC address in canonical format
    '''

    string = key.lower().replace(':','').replace('-','').replace('.','')
    result = ''

    count = 0
    for s in string:
        if (count / 2) > 0 and (count % 2) == 0:
            result += ':'
        result += s
        count += 1
    return result

def search(q):
    '''
    Searches in Equipment model for racks, units, IP address, MACs, serial, hostnames etc

    @type  q: string or iterable
    @param q: a string or an iterable of strings to search for.

    @rtype: QuerySet
    @return: A QuerySet with results matching all items of q 
    '''

    if q is None or len(q) == 0:
        return Equipment.objects.none()

    # Working on iterables. However in case we are not given one it is cheaper
    # to create one than fail
    try:
        q.__iter__()
    except AttributeError:
        q = (q,)

    ids = []

    for key in q:
        if key.upper().replace('R','').replace('U','').isdigit():
            rackunit = key.upper().replace('R','').replace('U','')
            if len(rackunit) < 3:
                result = Equipment.objects.filter(rack=rackunit)
            elif len(rackunit) == 3:
                result = Equipment.objects.none()
            elif len(rackunit) == 4:
                result = Equipment.objects.filter(rack=rackunit[0:2], unit=rackunit[2:4])
            else:
                result = Equipment.objects.filter(serial=key)
        else:
            try:
                dns = gethostbyaddr(key)[0]
            except (herror, gaierror, IndexError, error, UnicodeEncodeError):
                dns = ''
            mac = canonicalize_mac(key)
            result = Equipment.objects.filter(
                                            Q(serial=key)|
                                            Q(model__name__icontains=key)|
                                            Q(allocation__name__icontains=key)|
                                            Q(allocation__contacts__name__icontains=key)|
                                            Q(allocation__contacts__surname__icontains=key)|
                                            Q(servermanagement__mac__icontains=mac)|
                                            Q(servermanagement__hostname__icontains=key)|
                                            Q(servermanagement__hostname=dns)
                                            )
        ids.extend(result.distinct().values_list('id', flat=True))
        ids = list(set(ids))
    try:
        return Equipment.objects.filter(pk__in=ids).distinct()
    except DatabaseError as e:
        raise RuntimeError(_('An error occured while querying db: %(databaseerror)s') % {'databaseerror': e})

def populate_tickets(equipment_list):
    '''
    Populates tickets attribute for each equipment in a queryset.

    Note: This function is a temporary hack and will be replaced at some point.
    It works by looking at settings.TICKETING_URL and matches strings based on
    that. This function WILL evaluate the queryset and cause database lookups.

    @type  equipment_list: Queryset
    @param equipment_list: A Django queryset containing equipment which need to
    be populated with tickets attribute

    @rtype: QuerySet
    @return: A QuerySet with equipment's comments attribute populated
    '''

    # TODO: Just a HACK 
    for equipment in equipment_list:
        m = re.search('((?:%s[0-9]+)\s*)+' % settings.TICKETING_URL,
                str(equipment.comments), re.DOTALL)
        if m:
            tickets = m.group(0).split()
            equipment.tickets = [ (re.sub(settings.TICKETING_URL,'', t), t) for t in tickets]
    return equipment_list

def get_search_terms(text):
    '''
    Splits up a text in tokens, drops non-usefull ones and returns a Set of tokens

    @type   text: String
    @param  text: A unicode string to split up in tokens

    @rtype: Set of strings
    @return: A Set of usefull unique tokens appearing the text
    '''

    stoplist = ['and', 'is', 'it', 'an', 'as', 'at', 'have', 'in', 'yet', 'if',
            'from', 'for', 'when', 'by', 'to', 'you', 'be', 'we', 'that', 'may',
            'not', 'with', 'tbd', 'a', 'on', 'your', 'this', 'of', 'us', 'will',
            'can', 'the', 'or', 'are', 'up', 'down', 'ip',]

    analyzer = SpaceSeparatedTokenizer() | StopFilter(stoplist=stoplist)

    tokens = set([x.text for x in analyzer(text)])

    # TODO: When we go to whoosh 2.x we can drop the following and use a whoosh
    # SubstitutionFilter to the analyzer above
    tokens = set([re.sub('[\(\)/]','',x) for x in tokens])

    return tokens
