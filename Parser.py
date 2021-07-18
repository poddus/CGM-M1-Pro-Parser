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

        self.billing_type = insurance_buffer['billing_type']
        self.quarter = insurance_buffer['q']
        self.qyear = insurance_buffer['qyear']
        self.ins_status = insurance_buffer['ins_status']
        self.vknr = insurance_buffer['vknr']
        self.ktab = insurance_buffer['ktab']

        if notices:
            self.notices = notices
        else:
            self.notices = []

    def __repr__(self):
        return '{self.__class__.__name__}(self.pat_id)'.format(self=self)

    def __str__(self):
        str_buffer = []
        str_buffer.append(
            '\n'
            'STAMMDATEN\n'
            '----------\n'
            'ID: {self.pat_id}\n'
            'Name: {self.last_name}, {self.first_name}\n'
            'Geburtstag: {self.birth_date}\n'
            '\n'
            'VERSICHERUNGSDATEN\n'
            '------------------\n'
            'Scheinart: {self.billing_type}\n'
            'Quartal: {self.quarter}, {self.qyear}\n'
            'Versicherungsstatus: {self.ins_status}\n'
            'VKNR: {self.vknr}\n'
            'KTAB: {self.ktab}\n'
            '\n'
            'FEHLER\n'
            '------\n'
            .format(self=self)
        )
        for n in self.notices:
            str_buffer.append('Datum: {}\n'.format(str(n['date'])))
            str_buffer.append('{}\n'.format(n['text']))
        str_buffer.append('\n')

        return ''.join(str_buffer)


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

    def separate_entries(self, data):
        if self.input_type == self.T_GOF:
            logging.info('separating data using GOF format')

            # remove first entry delimiter
            del data[0]

            entries = []
            current_entry = []
            for line in data:
                trimmed_line = ''
                if re.match(self.PAT_DEL, line):
                    logging.info('patient delimiter encountered')
                    entries.append(current_entry)
                    current_entry = []
                    continue
                trimmed_line = re.sub('^ *| *\n *| *$', '', line)
                current_entry.append(trimmed_line)

            return entries

    def parse_notices(self, notices):
        notice_list = []
        for line in notices:
            match_notice_info = re.search('^(\d{2}).(\d{2}).(\d{4})\s(.*)', line)
            if match_notice_info:
                try:
                    current_notice['text'] = ' '.join(current_notice['text'])
                    notice_list.append(current_notice)
                    logging.info('appended notice to list of notices')
                except NameError:
                    # ignore undefined variable in first loop
                    pass
                current_notice = {}
                current_notice['text'] = []

                logging.debug('successful match of notice information')
                # convert to datetime object
                date_stamp = date(
                    int(match_notice_info[3]),
                    int(match_notice_info[2]),
                    int(match_notice_info[1])
                )

                current_notice['date'] = date_stamp
                current_notice['type'] = match_notice_info[4]
                continue
            trimmed_line = re.sub(r'^\s*|\s$', '', line)
            current_notice['text'].append(trimmed_line)

        # add last entry to list this duplicates code from the loop and I don't like it
        current_notice['text'] = ' '.join(current_notice['text'])
        notice_list.append(current_notice)
        logging.info('appended last notice to list of notices')

        return notice_list

    def parse_entries(self, entries):
        entries_new = []
        if self.input_type == self.T_GOF:
            logging.info('parsing entries using GOF format')

            for e in entries:
                # parse first line (patient info)
                current_patient = {}
                match_pat = re.search(
                    '(^\d*)\s([\w ÄäÖöÜüß-]*), ([\w ÄäÖöÜüß-]*)\s(\d{2}).(\d{2}).(\d{4})',
                    e[0]
                )
                if match_pat:
                    logging.debug('successful match of patient information')
                    pat_birth_date = date(
                        int(match_pat[6]),
                        int(match_pat[5]),
                        int(match_pat[4])
                    )
                    current_patient['pat_id'] = match_pat[1]
                    current_patient['last_name'] = match_pat[2]
                    current_patient['first_name'] = match_pat[3]
                    current_patient['birth_date'] = pat_birth_date
                else:
                    logging.error('no match of patient information!')

                # parse second line (insurance info)
                current_insurance = {}
                match_ins = re.search(
                    '([\w ÄäÖöÜüß])\s(\d)(\d{4})\s([MFR])\s(\d*)\s(\d{2})',
                    e[1]
                )
                if match_ins:
                    logging.debug('successful match of insurance information')
                    current_insurance['billing_type'] = match_ins[1]
                    current_insurance['q'] = match_ins[2]
                    current_insurance['qyear'] = match_ins[3]
                    current_insurance['ins_status'] = match_ins[4]
                    current_insurance['vknr'] = match_ins[5]
                    current_insurance['ktab'] = match_ins[6]
                else:
                    logging.error('no match of insurance information!')

                # parse notices
                # TODO
                notices = self.parse_notices(e[2:])

                entries_new.append(CGMBillingNotice(current_patient, current_insurance, notices))
            return entries_new


p = CGMParser()
with open('test_input/abrechnung_short.txt', 'r', encoding='cp1252') as f:
    data = f.readlines()

data = p.interpret_header(data)
entries = p.separate_entries(data)
parsed_entries = p.parse_entries(entries)
for e in parsed_entries:
    print(e)
