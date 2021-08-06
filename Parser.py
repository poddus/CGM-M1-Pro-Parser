#!/usr/bin/env python
# coding: utf-8

import re
import logging
from datetime import datetime
import csv

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)


class CGMPatient:
    """
    base class which defines a generic single patient-related entry
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
    def __init__(self, patient_buffer, insurance_buffer, chart_notes=None):
        super().__init__(patient_buffer)

        self.kasse = insurance_buffer['kasse']
        self.member_id = insurance_buffer['member_id']
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
    TGS_INDENT_LEVELS = {
        'erfasser': 9,
        'schein_typ': 13,
        'behandler': 15,
        'fachgebiet': 19,
        'zeilentyp': 23
    }
    # TODO: These expressions are often reused within more complex ones, but formatting raw strings is ugly
    # PAT_NAME = r'[\w ÄäÖöÜüß-]*'
    # DATE = r'\d{2}.\d{2}.\d{4}'

    def __init__(self):
        self.input_type = ''

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
            logging.info('removing footer')
            logging.debug(data[-3:])
            del data[-3:]
        logging.info('input type set to: {}'.format(self.input_type))
        return data

    def separate_entries(self, data):
        # remove first entry delimiter
        del data[0]

        delimiter = ''
        if self.input_type == self.T_GOF:
            logging.info('separating data using GOF format')
            delimiter = self.PAT_DEL

        elif self.input_type == self.T_TGS:
            logging.info('separating data using TGS format')
            delimiter = self.TGS_ENTRY_DEL

        entries = []
        current_entry = []
        for line in data:
            trimmed_line = ''
            if re.match(delimiter, line):
                logging.info('patient delimiter encountered')
                entries.append(current_entry)
                current_entry = []
                continue
            # trim trailing whitespace. leading whitespace (indent) is needed for parsing and is removed later
            trimmed_line = re.sub(r' +$', '', line)
            current_entry.append(trimmed_line)
        return entries

    def parse_entries(self, entries):
        entries_new = []
        if self.input_type == self.T_GOF:
            logging.info('parsing entries using GOF format')

            for e in entries:
                # parse first line (patient info)
                current_patient = {}
                match_0 = re.search(
                    # TODO: can names be empty?
                    r'(^\d*)\s+([\w ÄäÖöÜüß-]+), ([\w ÄäÖöÜüß-]+)\s+(\d{2}.\d{2}.\d{4})',
                    e[0]
                )
                if match_0:
                    logging.debug('successful match of patient information')

                    pat_birth_date = datetime.strptime(match_0[4], '%d.%m.%Y').date()

                    current_patient['pat_id'] = match_0[1]
                    current_patient['last_name'] = match_0[2]
                    current_patient['first_name'] = match_0[3]
                    current_patient['birth_date'] = pat_birth_date
                else:
                    logging.error('no match of patient information for entry:\n{}'.format(e))

                # parse second line (insurance info)
                current_insurance = {}
                match_1 = re.search(
                    r'([\wÄäÖöÜüß]+)\s+(\d)(\d{4})\s+([MFR])\s+(\d*)\s+(\d{2})',
                    e[1]
                )
                if match_1:
                    logging.debug('successful match of insurance information')
                    current_insurance['billing_type'] = match_1[1]
                    current_insurance['q'] = match_1[2]
                    current_insurance['qyear'] = match_1[3]
                    current_insurance['ins_status'] = match_1[4]
                    current_insurance['vknr'] = match_1[5]
                    current_insurance['ktab'] = match_1[6]
                else:
                    logging.error('no match of insurance information!')

                # parse notices
                notices = self._parse_entry_content(e[2:])

                entries_new.append(CGMBillingNotice(current_patient, current_insurance, notices))
        elif self.input_type == self.T_TGS:
            logging.info('parsing entries using TGS format')
            for e in entries:
                current_patient = {}
                current_insurance = {}

                # parse first line (patient ID)
                match_0 = re.search(
                    r'^Patientennr. (\d+)\s*(.*)',
                    e[0]
                )
                if match_0:
                    logging.debug('successful match on line 1')
                    current_patient['pat_id'] = match_0[1]
                    current_patient['groups'] = match_0[2][1:-1].split(sep=', ')
                else:
                    logging.error('no match on first line for entry:\n{}'.format(e))

                # parse second line (patient and insurance info)
                # TODO: it may be that if a patient dies within the current quarter, then the death date will
                #  show up in this line, since the birth date is designated with a '*'. Try to generate example input
                match_1 = re.search(r'([\w ÄäÖöÜüß-]+),([\w ÄäÖöÜüß-]+);\s\*\s(\d{2}.\d{2}.\d{4}),\s([\wÄäÖöÜüß .-]+),\s([A-Z0-9]+)', e[1])
                if match_1:
                    logging.debug('successful match on line 2')
                    pat_birth_date = datetime.strptime(match_1[3], '%d.%m.%Y').date()
                    current_patient['last_name'] = match_1[1]
                    current_patient['first_name'] = match_1[2]
                    current_patient['birth_date'] = pat_birth_date

                    current_insurance['kasse'] = match_1[4]
                    current_insurance['member_id'] = match_1[5]

                # parse notes
                chart_notes = self._parse_entry_content(e[2:])

                entries_new.append(CGMPatientRecord(current_patient, current_insurance, chart_notes))
        return entries_new

    def _parse_entry_content(self, content):
        content_list = []
        new_line = True
        if self.input_type == self.T_GOF:
            for line in content:
                match_info = re.search(r'^(\d{2}.\d{2}.\d{4})\s(.*)', line)
                if match_info:
                    logging.debug('successful match of entry content meta information')
                    if new_line:
                        content_list = self._write_entry_content(current_content, content_list)

                    current_content = {'text': []}

                    date_stamp = datetime.strptime(match_info[1], '%d.%m.%Y').date()
                    current_content['date'] = date_stamp
                    current_content['type'] = match_info[2]
                # remove leading whitespace
                trimmed_line = re.sub(r'^\s*', '', line)
                current_content['text'].append(trimmed_line)
                new_line = False

        elif self.input_type == self.T_TGS:
            current_content = {'text': []}
            new_line = True
            for line in content:
                for k, v in self.TGS_INDENT_LEVELS.items():
                    match_date = re.search(r'^(\d{2}.\d{2}.\d{2})', line)
                    match_other = re.search(r'^.{{{}}}(\w+)'.format(v), line)
                    if not new_line and (match_date or match_other):
                        # different from GOF, here we want to retain attributes, but we clear text for next loop
                        # this is done by creating a copy
                        content_list = self._write_entry_content(current_content, content_list)
                        current_content = current_content.copy()
                        current_content['text'] = []
                        new_line = True
                    if match_date:
                        date_stamp = datetime.strptime(match_date[1], '%d.%m.%y').date()
                        current_content['date'] = date_stamp
                    if match_other:
                        current_content[k] = match_other[1]
                new_line = False

                match_text = re.search(r'.{28}(.+)', line)
                if match_text:
                    current_content['text'].append(match_text[1])

        content_list = self._write_entry_content(current_content, content_list)
        return content_list

    def _write_entry_content(self, content_item, content_list):
        content_item['text'] = ' '.join(content_item['text'])
        content_list.append(content_item)
        logging.info('appended notice to list of notices')
        return content_list

    def export_csv(self, entries, filepath):
        if self.input_type == self.T_GOF:
            with open(filepath, mode='w') as f:
                fieldnames = [
                    'Patienten-ID',
                    'Nachname',
                    'Vorname',
                    'Geburtsdatum',
                    'Scheinart',
                    'Quartal',
                    'Versicherungsstatus',
                    'VKNR',
                    'KTAB'
                ]
                csv_writer = csv.DictWriter(f, delimiter=';', fieldnames=fieldnames)
                csv_writer.writeheader()
                for e in entries:
                    row_buffer = {
                        'Patienten-ID': e.pat_id,
                        'Nachname': e.last_name,
                        'Vorname': e.first_name,
                        'Geburtsdatum': e.birth_date,
                        'Scheinart': e.billing_type,
                        'Quartal': e.quarter + e.qyear,
                        'Versicherungsstatus': e.ins_status,
                        'VKNR': e.vknr,
                        'KTAB': e.ktab
                    }
                    csv_writer.writerow(row_buffer)
        if self.input_type == self.T_TGS:
            raise NotImplementedError


p = CGMParser()
with open('test_input/hzv.txt', 'r', encoding='cp1252') as f:
    glob_data = f.readlines()

glob_data = p.interpret_header(glob_data)
glob_entries = p.separate_entries(glob_data)
glob_parsed_entries = p.parse_entries(glob_entries)
p.export_csv(glob_parsed_entries, 'out.csv')