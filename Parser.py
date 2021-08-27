#!/usr/bin/env python
# coding: utf-8

import re
from dataclasses import dataclass, field
import logging
from datetime import datetime
import csv
from abc import ABC, abstractmethod

logger = logging.getLogger()
logger.setLevel(logging.INFO)


@dataclass()
class CGMPatient(ABC):
    """
    base class which defines a generic single patient-related record
    """
    pat_id: str
    first_name: str
    last_name: str
    birth_date: datetime.date

    @abstractmethod
    def get_contents(self):
        """return dict of instance variables and corresponding values"""

    def get_keys(self):
        return vars(self).keys()


@dataclass()
class CGMPatientGOF(CGMPatient):
    """
    represent single record in GO-Fehler

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

    def get_contents(self):
        inst_vars = vars(self)

        notices = []
        for notice in inst_vars['notices']:
            pass
            current_notice = [
                notice['date'],
                notice['type'],
                notice['erfasser'],
                notice['text']
            ]
            notices.append('\t'.join(i for i in current_notice))
        inst_vars['notices'] = '\n'.join(i for i in notices)

        return inst_vars


@dataclass()
class CGMPatientTGS(CGMPatient):
    """represent single record in Textgruppenstatistik"""

    kasse: str
    member_id: str
    groups: list = field(default_factory=[])
    chart_notes: list = field(default_factory=[])

    def get_contents(self):
        inst_vars = vars(self)
        if len(inst_vars['groups']) == 0:
            inst_vars['groups'] = ''
        elif len(inst_vars['groups']) == 1:
            inst_vars['groups'] = inst_vars['groups'][0]
        elif len(inst_vars['groups']) > 1:
            inst_vars['groups'] = ', '.join(inst_vars['groups'])

        notes = []
        for note in inst_vars['chart_notes']:
            current_note = [
                note['date'],
                note['erfasser'],
                note['schein_typ'],
                note['behandler'],
                note['fachgebiet'],
                note['zeilentyp'],
                note['text']
            ]
            notes.append('\t'.join(i for i in current_note))
        inst_vars['chart_notes'] = '\n'.join(i for i in notes)
        return inst_vars


class FailedGrepMatch(ValueError):
    pass


class ParsingContext(ABC):
    """define methods specific to a particular input format"""

    @abstractmethod
    def separate_records(self):
        """return list of records (list of list of strings)"""

    @abstractmethod
    def parse_records(self):
        """return list of parsed records (list of dicts)"""

    def _parse_content(self):
        """return parsed record content (list of dicts)"""


class ParsingContextGOF(ParsingContext):
    """parsing context for GOF format"""

    def separate_records(self):
        raise NotImplementedError

    def parse_records(self):
        raise NotImplementedError

    def _parse_content(self):
        raise NotImplementedError


class ParsingContextTGS(ParsingContext):
    """parsing context for TGS format"""

    def separate_records(self):
        raise NotImplementedError

    def parse_records(self):
        raise NotImplementedError

    def _parse_content(self):
        raise NotImplementedError


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
    TGS_RECORD_DEL = r'-{96}'
    TGS_INDENT_LEVELS = {
        'erfasser': 9,
        'schein_typ': 13,
        'behandler': 15,
        'fachgebiet': 19,
        'zeilentyp': 23
    }

    # def __init__(self):
    #     self.input_type = ''
    #     self.entries = []

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
        # remove first record delimiter
        del data[0]

        delimiter = ''
        if self.input_type == self.T_GOF:
            logging.info('separating data using GOF format')
            delimiter = self.PAT_DEL

        elif self.input_type == self.T_TGS:
            logging.info('separating data using TGS format')
            delimiter = self.TGS_RECORD_DEL
        else:
            logging.error('no delimiter recognized')

        entries = []
        current_record = []
        for line in data:
            trimmed_line = ''
            if re.match(delimiter, line):
                logging.debug('patient delimiter encountered')
                entries.append(current_record)
                current_record = []
                continue
            # trim trailing whitespace. leading whitespace (indent) is needed for parsing and is removed later
            trimmed_line = re.sub(r' +$', '', line)
            current_record.append(trimmed_line)
        # add last record to list
        entries.append(current_record)
        return entries

    # TODO: refactor into dataclass
    def parse_entries(self, entries):
        entries_new = []
        if self.input_type == self.T_GOF:
            logging.info('parsing entries using GOF format')

            for e in entries:
                # parse first line (patient info)
                record_buffer = {}
                match_0 = re.search(
                    # TODO: can names be empty?
                    r'(^\d*)\s+([\w -]+), ([\w -]+)\s+(\d{2}.\d{2}.\d{4})',
                    e[0]
                )
                if not match_0:
                    raise FailedGrepMatch('no match of patient information for record:\n{}'.format(e))

                # parse second line (insurance info)
                match_1 = re.search(
                    r'([\w]+)\s+(\d)(\d{4})\s+([MFR])\s+(\d*)\s+(\d{2})',
                    e[1]
                )
                if not match_1:
                    raise FailedGrepMatch('no match of insurance information!')

                # parse notices
                notices = self._parse_record_content(e[2:])

                entries_new.append(
                    CGMPatientGOF(
                        pat_id= match_0[1],
                        first_name= match_0[3],
                        last_name= match_0[2],
                        birth_date= datetime.strptime(match_0[4], '%d.%m.%Y').date().strftime('%Y-%m-%d'),
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
                record_buffer = {}

                # parse first line (patient ID)
                match_0 = re.search(
                    r'^Patientennr. (\d+)\s*(.*)',
                    e[0]
                )
                if not match_0:
                    raise FailedGrepMatch('no match on first line for record:\n{}'.format(e))

                # parse second line (patient and insurance info)
                # TODO: it may be that if a patient dies within the current quarter, then the death date will
                #  show up in this line, since the birth date is designated with a '*'. Try to generate example input
                match_1 = re.search(r'([\w -]+),([\w -]+);\s\*\s(\d{2}.\d{2}.\d{4}),\s([\w .-]+),\s([A-Z0-9]+)', e[1])
                if not match_1:
                    raise FailedGrepMatch('no match on second line for record:\n{}'.format(e))

                # parse notes
                chart_notes = self._parse_record_content(e[2:])

                entries_new.append(
                    CGMPatientTGS(
                        pat_id=match_0[1],
                        first_name=match_1[2],
                        last_name=match_1[1],
                        birth_date=datetime.strptime(match_1[3], '%d.%m.%Y').date().strftime('%Y-%m-%d'),
                        kasse=match_1[4],
                        member_id=match_1[5],
                        groups=match_0[2][1:-1].split(sep=', '),
                        chart_notes=chart_notes
                    )
                )
        return entries_new

    # TODO: refactor into dataclass
    def _parse_record_content(self, content):
        content_list = []
        new_line = True
        if self.input_type == self.T_GOF:
            for line in content:
                match_info = re.search(r'^(\d{2}.\d{2}.\d{4})\s(\w+)(\s\(\w{3}\))*', line)
                if match_info:
                    if not new_line:
                        content_list = self._write_record_content(current_content, content_list)
                    current_content = {'text': []}
                    current_content['date'] = datetime.strptime(match_info[1], '%d.%m.%Y').date().strftime('%Y-%m-%d')
                    current_content['type'] = match_info[2]
                    if match_info[3]:
                        current_content['erfasser'] = match_info[3][2:-1]
                else:  # this line is not info line -> parse content
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
                        content_list = self._write_record_content(current_content, content_list)
                        current_content = current_content.copy()
                        current_content['text'] = []
                        new_line = True
                    if match_date:
                        current_content['date'] = datetime.strptime(match_date[1], '%d.%m.%y').date().strftime('%Y-%m-%d')
                    if match_other:
                        current_content[k] = match_other[1]
                new_line = False

                match_text = re.search(r'.{28}(.+)', line)
                if match_text:
                    current_content['text'].append(match_text[1])

        content_list = self._write_record_content(current_content, content_list)
        return content_list

    @staticmethod
    def _write_record_content(content_item, content_list):
        content_item['text'] = ' '.join(content_item['text'])
        content_list.append(content_item)
        logging.debug('appended notice to list of notices')
        return content_list

    def export_csv(self, entries, filepath):
        with open(filepath, mode='w') as f:
            fieldnames = entries[0].get_keys()  # TODO: hacky way to get fieldnames
            csv_writer = csv.DictWriter(f, delimiter=';', fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
            csv_writer.writeheader()
            for e in entries:
                csv_writer.writerow(e.get_contents())

    @staticmethod
    def export_ids(entries, filepath):
        with open(filepath, mode='w') as f:
            for e in entries:
                f.writelines(e.pat_id + '\n')

    # --------------------------------------------------------
    # refactored code below

    def __init__(self, raw_input):
        self.raw_input = raw_input
        self.context = self._determine_context(raw_input)
        self.separated_records = self.context.separate_records(raw_input)
        self.parsed_records = self.context.parse_records(self.separated_records)

    def _determine_context(self, input):
        """assign relevant context to self.context based on raw input"""
        raise NotImplementedError


def main(args):
    with open(args.input_path, 'r', encoding='cp1252') as f:
        glob_data = f.readlines()

    p = CGMParser(glob_data)


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
