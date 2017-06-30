import dateutil.parser
import pymssql

import re

from django.conf import settings
from django.utils import timezone


def get_manifestations():
    pdb = _Database()
    rows = pdb.get_manifestations()
    for row in rows:
        row['date_updated'] = _convert_MARC_datetime(row['date_updated'])
    return rows


def get_altered_manifestation_id_mapping():
    """
    returns a dictionary which maps the former id(s) of each manifestation to its current id
    """
    pdb = _Database()
    change_mapping = {
        result["NewBibRecordID"]: result["OldBibRecordID"]
        for result in pdb.get_altered_manifestation_id_mapping()}
    keys = list(change_mapping.keys())

    id_mapping = {}
    seen_ids = set([])
    keys.sort(reverse=True)
    #  uses the fact that ids always increase to walk back through chains of reassigned ids
    for key in keys:
        #  ignore ids which are not current ids,
        #  that is they have already been encountered when walking back from a current id
        if key not in seen_ids:
            seed = key
            while change_mapping.get(key):
                key = change_mapping[key]
                seen_ids.add(key)
                id_mapping.update({key: seed})
    return id_mapping


def get_works():
    pdb = _Database()
    rows = pdb.get_tags('24', 'a')
    works = {}
    for row in rows:
        exp = r'^{}(\d+)$'.format(settings.CONNECTOR['work_prefix'])
        m = re.match(exp, row['Data'])
        if m:
            works.update({row['manifestation_id']: int(m.group(1))})
    return works


def get_identifiers(manifestation_id):
    identifiers = []
    pdb = _Database()
    rows = pdb.get_tags('856', 'u', manifestation_id)
    provider_indicators = settings.INDICATORS
    link_indicators = settings.LINKS
    for row in rows:
        identifier = {}
        for source, exp in provider_indicators.items():
            m = re.search(exp, row['Data'])
            if m:
                identifier['value'] = m.group(1)
                identifier['source'] = source
                identifiers.append(identifier)
        for link_indicator in link_indicators:
            exp = link_indicator['url']
            m = re.match(exp, row['Data'])
            if m:
                identifier_value = m.group()
                identifier['source'] = 'link'
                if link_indicator.get('sub'):
                    for k, v in link_indicator['sub'].items():
                        identifier_value = re.sub(k, v, identifier_value)
                identifier['value'] = identifier_value
                identifiers.append(identifier)

    rows = pdb.get_tags('20', 'a', manifestation_id)
    for row in rows:
        identifier = {'source': 'isbn'}
        m = re.match(r'\S*', row['Data'])
        if m:
            isbn = re.sub(r'[^X0-9]', '', m.group())
            if len(isbn) == 10 and _isbn10_check_digit(isbn[:-1]) == isbn[-1]:
                isbn = _isbn_convert_10_to_13(isbn)
            if len(isbn) == 13 and _isbn13_check_digit(isbn[:-1]) == isbn[-1]:
                identifier.update({'value': isbn})
                identifiers.append(identifier)

    rows = pdb.get_tags('35', 'a', manifestation_id)
    for row in rows:
        identifier = {'source': 'oclc'}
        m = re.match(r'^\(OCoLC\)\s*[ocnm]*(\d+)\s*$', row['Data'])
        if m:
            oclc = m.group(1)
            identifier.update({'value': oclc})
            identifiers.append(identifier)
    return identifiers


class _Database(object):
    _connection = None
    _cursor = None

    def __init__(self):
        connector = settings.CONNECTOR
        self._connection = pymssql.connect(
            connector['ip_address'],
            connector['user'],
            connector['password'],
            connector['database'],
            port=connector['port'])
        self._cursor = self._connection.cursor(as_dict=True)

    def __del__(self):
        self._connection.close()

    def query(self, query, params=None):
        self._cursor.execute(query, params)
        results = self._cursor.fetchall()
        return results

    def get_manifestations(self):
        query = """
                SELECT
                    BibliographicRecordID AS manifestation_id,
                    MARCModificationDate AS date_updated,
                    Precedence AS precedence
                FROM Polaris.Polaris.BibliographicRecords
                    AS br WITH (NOLOCK)
                JOIN Polaris.Polaris.MARCTypeOfMaterial
                    AS tom WITH (NOLOCK)
                ON br.PrimaryMARCTOMID = tom.MARCTypeOfMaterialID"""
        results = self.query(query)
        return results

    def get_tags(self, tag_number, subfield, manifestation_id=None):
        if manifestation_id:
            query = """
                    SELECT
                        Data
                    FROM Polaris.Polaris.BibliographicTags
                        AS tag WITH (NOLOCK)
                    LEFT OUTER JOIN Polaris.Polaris.BibliographicSubfields
                        AS sub WITH (NOLOCK)
                        ON tag.BibliographicTagID = sub.BibliographicTagID
                    WHERE
                        tag.TagNumber = %s
                        AND sub.Subfield = %s
                        AND tag.BibliographicRecordID = %s"""
            params = (tag_number, subfield, manifestation_id)
            results = self.query(query, params)
        else:
            query = """
                    SELECT
                        BibliographicRecordID AS manifestation_id,
                        Data
                    FROM Polaris.Polaris.BibliographicTags
                        AS tag WITH (NOLOCK)
                    LEFT OUTER JOIN Polaris.Polaris.BibliographicSubfields
                        AS sub WITH (NOLOCK)
                        ON tag.BibliographicTagID = sub.BibliographicTagID
                    WHERE
                        tag.TagNumber = %s
                        AND sub.Subfield = %s"""
            params = (tag_number, subfield)
            results = self.query(query, params)
        return results

    def get_altered_manifestation_id_mapping(self):
        query = """
            SELECT
                td.numValue AS OldBibRecordID,
                td1.numValue AS NewBibRecordID,
                th.TranClientDate
                FROM PolarisTransactions.polaris.TransactionHeaders th WITH (nolock)
                    INNER JOIN PolarisTransactions.polaris.TransactionDetails td WITH (nolock)
                        ON (th.TransactionID = td.TransactionID AND td.TransactionSubTypeID = 38)
                    INNER JOIN PolarisTransactions.polaris.TransactionDetails td1 WITH (nolock)
                        ON (th.TransactionID = td1.TransactionID AND td1.TransactionSubTypeID = 278)
                WHERE
                    th.TransactionTypeID = 3024
                    AND td1.numValue IS NOT NULL AND td1.numValue > 0
            UNION
            SELECT
                td.numValue AS OldBibID,
                td1.numValue AS NewBibID,
                th.TranClientDate
                FROM PolarisTransactions.polaris.TransactionHeaders th WITH (nolock)
                INNER JOIN PolarisTransactions.polaris.TransactionDetails td WITH (nolock)
                    ON (th.TransactionID = td.TransactionID AND td.TransactionSubTypeID = 36)
                INNER JOIN PolarisTransactions.polaris.TransactionDetails td1 WITH (nolock)
                    ON (th.TransactionID = td1.TransactionID AND td1.TransactionSubTypeID = 279)
                WHERE
                    th.TransactionTypeID = 3024
                    AND td1.numValue IS NOT NULL
                    AND td1.numValue > 0
            UNION
            SELECT
                td.numValue AS OldBibRecordID,
                td1.numValue AS NewBibRecordID,
                th.TranClientDate
                FROM
                    PolarisTransactions.polaris.TransactionHeaders th WITH (nolock)
                    INNER JOIN PolarisTransactions.polaris.TransactionDetails td WITH (nolock)
                        ON (th.TransactionID = td.TransactionID AND td.TransactionSubTypeID = 38)
                    INNER JOIN PolarisTransactions.polaris.TransactionDetails td1 WITH (nolock)
                        ON (th.TransactionID = td1.TransactionID AND td1.TransactionSubTypeID = 278)
                WHERE
                    th.TransactionTypeID = 3001
                    AND td1.numValue IS NOT NULL
                    AND td1.numValue > 0
            UNION
            SELECT
                td.numValue AS OldBibID,
                td1.numValue AS NewBibID,
                th.TranClientDate
                FROM
                    PolarisTransactions.polaris.TransactionHeaders th WITH (nolock)
                    INNER JOIN PolarisTransactions.polaris.TransactionDetails td WITH (nolock)
                        ON (th.TransactionID = td.TransactionID AND td.TransactionSubTypeID = 36)
                    INNER JOIN PolarisTransactions.polaris.TransactionDetails td1 WITH (nolock)
                        ON (th.TransactionID = td1.TransactionID AND td1.TransactionSubTypeID = 278)
                WHERE
                    th.TransactionTypeID = 3001
                    AND td1.numValue IS NOT NULL
                    AND td1.numValue > 0"""
        results = self.query(query)
        return results


def _isbn10_check_digit(isbn):
    assert len(isbn) == 9
    sum = 0
    for i in range(len(isbn)):
        c = int(isbn[i])
        w = i + 1
        sum += w * c
    r = sum % 11
    if r == 10:
        return 'X'
    else:
        return str(r)


def _isbn13_check_digit(isbn):
    assert len(isbn) == 12
    sum = 0
    for i in range(len(isbn)):
        c = int(isbn[i])
        if i % 2:
            w = 3
        else:
            w = 1
        sum += w * c
    r = 10 - (sum % 10)
    if r == 10:
        return '0'
    else:
        return str(r)


def _isbn_convert_10_to_13(isbn):
    assert len(isbn) == 10
    prefix = '978' + isbn[:-1]
    check = _isbn13_check_digit(prefix)
    return prefix + check


def _convert_MARC_datetime(s):
    t = '{}-{}-{} {}:{}'.format(s[:4], s[4:6], s[6:8], s[8:10], s[10:12])
    return timezone.make_aware(dateutil.parser.parse(t))
