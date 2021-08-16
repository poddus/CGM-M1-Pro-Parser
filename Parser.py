#!/usr/bin/env python
# coding: utf-8

import re
from dataclasses import dataclass, field
import logging
from datetime import datetime
import csv

logger = logging.getLogger()
logger.setLevel(logging.INFO)

@dataclass()
class CGMPatient:
    """
    base class which defines a generic single patient-related entry
    """
    pat_id: str
    first_name: str
    last_name: str
    birth_date: datetime.date

    def fullname(self):
        return '{} {}'.format(self.first_name, self.last_name)

@dataclass()
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

    billing_type: str
    quarter: str
    qyear: str
    ins_status: str
    vknr: str
    ktab: str
    notices: list = field(default_factory=[])


@dataclass()
class CGMPatientRecord(CGMPatient):
    """represents single entry in Textgruppenstatistik"""

    kasse: str
    member_id: str
    groups: list = field(default_factory=[])
    chart_notes: list = field(default_factory=[])


class FailedGrepMatch(ValueError):
    pass


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

    # input types TODO: should these be enums?
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

    def __init__(self):
        self.input_type = ''
        self.entries = []

    def interpret_header(self, data):
        h = data[0:3]
        logging.debug(data[0:3])
        # remove header from data
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
        else:
            logging.error('no delimiter recognized')

        entries = []
        current_entry = []
        for line in data:
            trimmed_line = ''
            if re.match(delimiter, line):
                logging.debug('patient delimiter encountered')
                entries.append(current_entry)
                current_entry = []
                continue
            # trim trailing whitespace. leading whitespace (indent) is needed for parsing and is removed later
            trimmed_line = re.sub(r' +$', '', line)
            current_entry.append(trimmed_line)
        # add last entry to list
        entries.append(current_entry)
        return entries

    def parse_entries(self, entries):
        entries_new = []
        if self.input_type == self.T_GOF:
            logging.info('parsing entries using GOF format')

            for e in entries:
                # parse first line (patient info)
                entry_buffer = {}
                match_0 = re.search(
                    # TODO: can names be empty?
                    r'(^\d*)\s+([\w -]+), ([\w -]+)\s+(\d{2}.\d{2}.\d{4})',
                    e[0]
                )
                if not match_0:
                    raise FailedGrepMatch('no match of patient information for entry:\n{}'.format(e))

                # parse second line (insurance info)
                match_1 = re.search(
                    r'([\w]+)\s+(\d)(\d{4})\s+([MFR])\s+(\d*)\s+(\d{2})',
                    e[1]
                )
                if not match_1:
                    raise FailedGrepMatch('no match of insurance information!')

                # parse notices
                notices = self._parse_entry_content(e[2:])

                entries_new.append(
                    CGMBillingNotice(
                        pat_id= match_0[1],
                        first_name= match_0[3],
                        last_name= match_0[2],
                        birth_date= datetime.strptime(match_0[4], '%d.%m.%Y').date(),
                        billing_type= match_1[1],
                        quarter= match_1[2],
                        qyear= match_1[3],
                        ins_status= match_1[4],
                        vknr= match_1[5],
                        ktab= match_1[6],
                        notices=notices
                    )
                )
        elif self.input_type == self.T_TGS:
            logging.info('parsing entries using TGS format')
            for e in entries:
                entry_buffer = {}

                # parse first line (patient ID)
                match_0 = re.search(
                    r'^Patientennr. (\d+)\s*(.*)',
                    e[0]
                )
                if not match_0:
                    raise FailedGrepMatch('no match on first line for entry:\n{}'.format(e))

                # parse second line (patient and insurance info)
                # TODO: it may be that if a patient dies within the current quarter, then the death date will
                #  show up in this line, since the birth date is designated with a '*'. Try to generate example input
                match_1 = re.search(r'([\w -]+),([\w -]+);\s\*\s(\d{2}.\d{2}.\d{4}),\s([\w .-]+),\s([A-Z0-9]+)', e[1])
                if not match_1:
                    raise FailedGrepMatch('no match on second line for entry:\n{}'.format(e))

                # parse notes
                chart_notes = self._parse_entry_content(e[2:])

                entries_new.append(
                    CGMPatientRecord(
                        pat_id=match_0[1],
                        first_name=match_1[2],
                        last_name=match_1[1],
                        birth_date=datetime.strptime(match_1[3], '%d.%m.%Y').date(),
                        kasse=match_1[4],
                        member_id=match_1[5],
                        groups=match_0[2][1:-1].split(sep=', '),
                        chart_notes=chart_notes
                    )
                )
        return entries_new

    # TODO: refactor into dataclass
    def _parse_entry_content(self, content):
        content_list = []
        new_line = True
        if self.input_type == self.T_GOF:
            for line in content:
                match_info = re.search(r'^(\d{2}.\d{2}.\d{4})\s(.*)', line)
                if match_info:
                    logging.debug('successful match of entry content meta information')
                    if not new_line:
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
                    # TODO: combine searches with regex OR operator (|)?
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

    @staticmethod
    def _write_entry_content(content_item, content_list):
        content_item['text'] = ' '.join(content_item['text'])
        content_list.append(content_item)
        logging.debug('appended notice to list of notices')
        return content_list

    def export_csv(self, entries, filepath):
        # TODO: implement export of content
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
            with open(filepath, mode='w') as f:
                fieldnames = [
                    'Patienten-ID',
                    'Nachname',
                    'Vorname',
                    'Geburtsdatum',
                    'Kasse',
                    'Versichertennummer'
                ]
                csv_writer = csv.DictWriter(f, delimiter=';', fieldnames=fieldnames)
                csv_writer.writeheader()
                for e in entries:
                    row_buffer = {
                        'Patienten-ID': e.pat_id,
                        'Nachname': e.last_name,
                        'Vorname': e.first_name,
                        'Geburtsdatum': e.birth_date,
                        'Kasse': e.kasse,
                        'Versichertennummer': e.member_id
                    }
                    csv_writer.writerow(row_buffer)

    @staticmethod
    def export_ids(entries, filepath):
        with open(filepath, mode='w') as f:
            for e in entries:
                f.writelines(e.pat_id + '\n')


def main(args):
    p = CGMParser()
    with open(args.input_path, 'r', encoding='cp1252') as f:
        glob_data = f.readlines()

    glob_data = p.interpret_header(glob_data)
    glob_entries = p.separate_entries(glob_data)
    glob_parsed_entries = p.parse_entries(glob_entries)
    if args.a:
        p.export_csv(glob_parsed_entries, args.output_path)
    else:
        p.export_ids(glob_parsed_entries, args.output_path)


if __name__ == "__main__":
    from argparse import ArgumentParser

    def parse_arguments():
        parser = ArgumentParser(
            description='Accepts a CGM M1 Pro list file and returns a csv file of either only patient IDs (default) or '
                        'of all available information (-a).'
        )
        parser.add_argument(
            'input_path',
            help='path to the file to be parsed'
        )
        parser.add_argument(
            'output_path',
            help='relative path to the output (CSV) file'
        )
        parser.add_argument(
            '-a',
            action='store_true',
            help='export all available information to output'
        )
        return parser.parse_args()

    arguments = parse_arguments()
    main(arguments)
