#!/usr/bin/env python
# coding: utf-8

import re
import logging
from datetime import date

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)


class CGMParser:
    """
    keep track of position and state, format input.

    possible states:
    header (default)
    patient
    notice
    footer

    possible input types:
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
    # states
    S_HEADER = 'HEADER'
    S_PATIENT = 'PATIENT'
    S_NOTICE = 'NOTICE'
    S_FOOTER = 'FOOTER'
    # regex searches
    PAT_DEL = r'={85} {6}\n'
    TGS_ENTRY_DEL = r'-{96}'
    PAT_NAME = r'[\w ÄäÖöÜüß-]*'
    DATE = r'\d{2}.\d{2}.\d{4}'

    def __init__(self):
        self.input_type = ''
        self.state = self.S_HEADER
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
        logging.info('set state to: {}'.format(self.S_PATIENT))
        self.state = self.S_PATIENT
        return data

    def parse_date(self, y, m, d):
        return date(int(y), int(m), int(d))

    def separate_entries(self, data):
        if self.input_type == self.T_GOF:
            logging.info('sep data using GOF format')
            data_str = ''.join(data)
            entries = re.split(self.PAT_DEL, data_str)
            trimmed = []
            for e in entries:
                trimmed.append(re.sub(' *\n *| *$', '\n', e))
            del trimmed[0]
            return trimmed


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
