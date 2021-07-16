#!/usr/bin/env python
# coding: utf-8

import re
import logging
from datetime import date

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)


class CGMPatient:
    """
    base class which defines a generic single entry
    """
    def __init__(self, patient_buffer):
        self.pat_id = patient_buffer['pat_id']
        self.first_name = patient_buffer['first_name']
        self.last_name = patient_buffer['last_name']
        self.birth_date = patient_buffer['birth_date']

    def fullname(self):
        return '{} {}'.format(self.first_name, self.last_name)


class CGMBillingNotice(CGMPatient):
    """
    represents single entry in GO-Fehler

    quarter is of the format
    [1,2,3,4][yyyy] (for example 12000 for 1. quarter of year 2000)

    insurance status can be
    M (Mitglied)
    F (Familie)
    R (Rentner)

    VKNR (Vertragskassennummer)

    KTAB (Kostenträgerabrechnungsbereich)
    00 = Primärabrechnung
    01 = Sozialversicherungsabkommen (SVA)
    02 = Bundesversorgungsgesetz (BVG)
    03 = Bundesentschädigungsgesetz (BEG)
    07 = Bundesvertriebenengesetz (BVFG)
    """
    def __init__(self, patient_buffer, insurance_buffer, notices=None):
        super().__init__(patient_buffer)

        self.treatment_type = insurance_buffer['treatment_type']
        self.quarter = insurance_buffer['quarter']
        self.ins_status = insurance_buffer['ins_status']
        self.vknr = insurance_buffer['vknr']
        self.ktab = insurance_buffer['ktab']

        if notices:
            self.notices = notices
        else:
            self.notices = []


class CGMPatientRecord(CGMPatient):
    """represents single entry in Textgruppenstatistik"""
    def __init__(self, patient_buffer, chart_notes=None):
        super().__init__(patient_buffer)
        if chart_notes:
            self.chart_notes = chart_notes
        else:
            self.chart_notes = []


class CGMParser:
    """
    Parser for lists exported from CGM M1 Pro

    supported input types:
    GO-Fehler (1. von 3 Protokollen bei der Kassenabrechnung)
    TGS (Textgruppenstatistik)
    """

    GO_FEHLER_HEADER = (
        '==========================================================================================\n'
        'Eintrag                                                                                 \n'
        '==========================================================================================\n'
        )
    TGS_HEADER = (
        '================================================================================================\n'
        'Textgruppenstatistik\n'
        '================================================================================================\n'
        )

    # input types
    T_GOF = 'GO-Fehler'
    T_TGS = 'TGS'
    # regex searches
    PAT_DEL = r'={85} {6}\n'
    TGS_ENTRY_DEL = r'-{96}'
    # PAT_NAME = r'[\w ÄäÖöÜüß-]*'
    # DATE = r'\d{2}.\d{2}.\d{4}'

    def __init__(self):
        self.input_type = ''
        self.rel_pos = 0

        self.entries = []
        self.entry_buffer = []

    def interpret_header(self, data):
        h = data[0:3]
        logging.debug(data[0:3])
        del data[0:3]
        h = ''.join(h)
        if h == self.GO_FEHLER_HEADER:
            self.input_type = self.T_GOF
        elif h == self.TGS_HEADER:
            self.input_type = self.T_TGS
        logging.info('input type set to: {}'.format(self.input_type))
        return data

    def parse_date(self, y, m, d):
        return date(int(y), int(m), int(d))

    def separate_entries(self, data):
        if self.input_type == self.T_GOF:
            logging.info('separating data using GOF format')

            # remove first entry delimiter
            del data[0]

            entries = []
            entry_buffer = []
            for line in data:
                trimmed_line = ''
                if re.match(self.PAT_DEL, line):
                    logging.info('patient delimiter encountered')
                    entries.append(entry_buffer)
                    entry_buffer = []
                    continue
                trimmed_line = re.sub('^ *| *\n *| *$', '', line)
                entry_buffer.append(trimmed_line)

            return entries

    def convert_to_datetime(y, m, d):
        return date(
            int(y),
            int(m),
            int(d)
        )

    def parse_notices(self, entries):
        pass

    def parse_entries(self, entries):
        entries_new = []
        if self.input_type == self.T_GOF:
            logging.info('parsing entries using GOF format')

            for e in entries:
                # parse first line
                patient_buffer = {}
                match_pat = re.search(
                    '(^\d*)\s([\w ÄäÖöÜüß-]*), ([\w ÄäÖöÜüß-]*)\s(\d{2}).(\d{2}).(\d{4})',
                    e[0]
                )
                if match_pat:
                    pat_birth_date = self.convert_to_datetime(
                        int(match_pat[6]),
                        int(match_pat[5]),
                        int(match_pat[4])
                    )
                    patient_buffer['pat_id'] = match_pat[1]
                    patient_buffer['last_name'] = match_pat[2]
                    patient_buffer['first_name'] = match_pat[3]
                    patient_buffer['birth_date'] = pat_birth_date

                # parse second line
                # TODO
                insurance_buffer = {}

                # parse notices
                # TODO
                notices = self.parse_notices(entries[2:])

                entries_new.append(CGMBillingNotice(patient_buffer, insurance_buffer, notices))


p = CGMParser()
with open('test_input/abrechnung_short.txt', 'r', encoding='cp1252') as f:
    data = f.readlines()

data = p.interpret_header(data)
entries = p.separate_entries(data)


def parse_abrechung(f):
    is_header = False
    header_buffer = []

    patients = []
    patient_buffer = {}
    notice_buffer = {}

    # first patient delimiter ('===') after header results in index 0
    patient_count = -1

    # indices start at 1
    content_line_count = 1
    log_line_count = 1

    for line in f:
        logging.debug(
            'pos abs/rel: {}, {}'.format(
                log_line_count,
                content_line_count
            )
        )

        # parse header
        if re.search('={90}', line) and (is_header is False):
            is_header = True
            continue
        if re.search('={90}', line):
            is_header = False
            continue
        header_buffer.append(line)

        # parse patient records
        # match 85 '=' and 5 ' '
        if re.search('^={85} {5}', line):
            # add patient from last round to list, skip first loop
            if patient_count != -1:
                patient_buffer['notice'] = notice_buffer
                patients.append(patient_buffer)
                patient_buffer = {}
            content_line_count = 1
            patient_count += 1
            logging.debug('patient_count: {}'.format(patient_count))
            continue

        # match patient information
        match_pat = re.search(
            '(^\d*)\s([\w ÄäÖöÜüß-]*), ([\w ÄäÖöÜüß-]*)\s(\d{2}).(\d{2}).(\d{4})',
            line
        )
        if match_pat:
            # convert to datetime object
            pat_birth_date = date(
                int(match_pat[6]),
                int(match_pat[5]),
                int(match_pat[4])
            )

            patient_buffer['pat_id'] = match_pat[1]
            patient_buffer['last_name'] = match_pat[2]
            patient_buffer['first_name'] = match_pat[3]
            patient_buffer['birth_date'] = pat_birth_date

            logging.debug(patient_buffer)

        # match notice date and type
        match_notice = re.search('^(\d{2}).(\d{2}).(\d{4})\s(.*)', line)
        if match_notice:
            # convert to datetime object
            date_stamp = date(
                int(match_notice[3]),
                int(match_notice[2]),
                int(match_notice[1])
            )

            notice_buffer['date'] = date_stamp
            notice_buffer['type'] = match_notice[4]
            logging.debug(notice_buffer)

        # TODO: match notice content
        # (until next notice or next patient record delimiter)

        content_line_count += 1
        log_line_count += 1
    return patients


with open('test_input/abrechnung_short.txt', 'r', encoding='cp1252') as f:
    patients = parse_abrechung(f)

for p in patients:
    print(
        'ID: {}\n'
        'Name: {} {}\n'
        'geb.: {}\n'
        'Notice Date: {}\n'
        'Notice Type: {}\n'.format(p['pat_id'],
                                   p['first_name'],
                                   p['last_name'],
                                   p['birth_date'].isoformat(),
                                   p['notice']['date'],
                                   p['notice']['type']
                                   )
    )
