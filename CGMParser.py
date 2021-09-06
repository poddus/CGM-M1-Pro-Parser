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

    # @abstractmethod
    # def get_instance_variables(self):
    #     """return dict of instance variables and corresponding values"""

    @abstractmethod
    def repr_as_dict(self) -> dict:
        """return dict of instance variables and corresponding values"""

    def get_keys(self):
        # TODO: this should return type list
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
    content: list = field(default_factory=[])

    def repr_as_dict(self) -> dict:
        instance_variables = vars(self)

        notices = []
        for notice in instance_variables['content']:
            current_notice = [
                notice['date'],
                notice['type'],
                notice['erfasser'],
                notice['text']
            ]
            notices.append('\t'.join(i for i in current_notice))
        instance_variables['content'] = '\n'.join(i for i in notices)

        return instance_variables


@dataclass()
class CGMPatientTGS(CGMPatient):
    """represent single record in Textgruppenstatistik"""

    kasse: str
    member_id: str
    groups: list = field(default_factory=[])
    content: list = field(default_factory=[])

    def repr_as_dict(self) -> dict:
        inst_vars = vars(self)
        if len(inst_vars['groups']) == 0:
            inst_vars['groups'] = ''
        elif len(inst_vars['groups']) == 1:
            inst_vars['groups'] = inst_vars['groups'][0]
        elif len(inst_vars['groups']) > 1:
            inst_vars['groups'] = ', '.join(inst_vars['groups'])

        notes = []
        for note in inst_vars['content']:
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
        inst_vars['content'] = '\n'.join(i for i in notes)
        return inst_vars


class FailedGrepMatch(ValueError):
    pass


class ParsingContext(ABC):
    """define methods specific to a particular input format"""

    HEADER: str
    RECORD_DELIMITER: str

    def __init__(self, raw_input):
        self.trimmed_input = raw_input[4:]  # remove header and first patient delimiter

    @abstractmethod
    def parse_records(self, records):
        """return list of parsed records (list of dicts)"""

    @abstractmethod
    def _parse_content(self, content):
        """return parsed record content (list of dicts)"""

    def separate_records(self):
        """return list of records (list of list of strings)"""

        records = []
        current_record = []
        for line in self.trimmed_input:
            if re.match(self.RECORD_DELIMITER, line):
                logging.debug('patient delimiter encountered')
                records.append(current_record)
                current_record = []
                continue
            # trim trailing whitespace. leading whitespace (indent) is needed for parsing and is removed later
            trimmed_line = re.sub(r' +$', '', line)
            current_record.append(trimmed_line)
        # add last record to list
        records.append(current_record)
        return records

    @staticmethod
    def _write_record_content(content_item, content_list):
        content_item['text'] = ' '.join(content_item['text'])
        content_list.append(content_item)
        logging.debug('appended notice to list of notices')
        return content_list


class ParsingContextGOF(ParsingContext):
    """parsing context for GOF format"""

    HEADER = (
        '==========================================================================================\n'
        'Eintrag                                                                                 \n'
        '==========================================================================================\n'
    )
    RECORD_DELIMITER = r'={85} {6}\n'

    def parse_records(self, records):
        logging.info('parsing entries using GOF format')
        records_new = []
        for rec in records:
            # parse first line (patient info)
            match_0 = re.search(
                # TODO: can names be empty?
                r'(^\d*)\s+([\w -]+), ([\w -]+)\s+(\d{2}.\d{2}.\d{4})',
                rec[0]
            )
            if not match_0:
                raise FailedGrepMatch('no match of patient information for record:\n{}'.format(rec))

            # parse second line (insurance info)
            match_1 = re.search(
                r'([\w]+)\s+(\d)(\d{4})\s+([MFR])\s+(\d*)\s+(\d{2})',
                rec[1]
            )
            if not match_1:
                raise FailedGrepMatch('no match of insurance information!')

            # parse content
            content = self._parse_content(rec[2:])

            records_new.append(
                CGMPatientGOF(
                    pat_id=match_0[1],
                    first_name=match_0[3],
                    last_name=match_0[2],
                    birth_date=datetime.strptime(match_0[4], '%d.%m.%Y').date().strftime('%Y-%m-%d'),
                    billing_type=match_1[1],
                    quarter=match_1[2],
                    qyear=match_1[3],
                    ins_status=match_1[4],
                    vknr=match_1[5],
                    ktab=match_1[6],
                    content=content
                )
            )
        return records_new

    def _parse_content(self, content):
        content_list = []
        new_line = True
        for line in content:
            match_info = re.search(r'^(\d{2}.\d{2}.\d{4})\s(\w+)(\s\(\w{3}\))*', line)
            if match_info:
                if not new_line:
                    content_list = self._write_record_content(current_content, content_list)

                current_content = {
                    'text': [],
                    'date': datetime.strptime(match_info[1], '%d.%m.%Y').date().strftime('%Y-%m-%d'),
                    'type': match_info[2]
                }

                if not match_info[3]:
                    # sometimes this information is not given
                    current_content['erfasser'] = ''
                else:
                    current_content['erfasser'] = match_info[3][2:-1]
            else:
                trimmed_line = re.sub(r'^\s*|\n', '', line)
                current_content['text'].append(trimmed_line)
            new_line = False

        content_list = self._write_record_content(current_content, content_list)
        return content_list


class ParsingContextTGS(ParsingContext):
    """parsing context for TGS format"""

    HEADER = (
        '================================================================================================\n'
        'Textgruppenstatistik\n'
        '================================================================================================\n'
        )
    RECORD_DELIMITER = r'-{96}'

    TGS_INDENT_LEVELS = {
        'erfasser': 9,
        'schein_typ': 13,
        'behandler': 15,
        'fachgebiet': 19,
        'zeilentyp': 23
    }

    def __init__(self, raw_input):
        # remove footer from input
        super().__init__(raw_input[:-3])

    def parse_records(self, records):
        logging.info('parsing entries using TGS format')
        records_new = []
        for rec in records:
            # parse first line (patient ID)
            match_0 = re.search(
                r'^Patientennr. (\d+)\s*(.*)',
                rec[0]
            )
            if not match_0:
                raise FailedGrepMatch('no match on first line for record:\n{}'.format(rec))

            # parse second line (patient and insurance info)
            # TODO: it may be that if a patient dies within the current quarter, then the death date will
            #  show up in this line, since the birth date is designated with a '*'. Try to generate example input
            match_1 = re.search(r'([\w -]+),([\w -]+);\s\*\s(\d{2}.\d{2}.\d{4}),\s([\w .-]+),\s([A-Z0-9]+)', rec[1])
            if not match_1:
                raise FailedGrepMatch('no match on second line for record:\n{}'.format(rec))

            # parse notes
            content = self._parse_content(rec[2:])

            records_new.append(
                CGMPatientTGS(
                    pat_id=match_0[1],
                    first_name=match_1[2],
                    last_name=match_1[1],
                    birth_date=datetime.strptime(match_1[3], '%d.%m.%Y').date().strftime('%Y-%m-%d'),
                    kasse=match_1[4],
                    member_id=match_1[5],
                    groups=match_0[2][1:-1].split(sep=', '),
                    content=content
                )
            )
        return records_new

    def _parse_content(self, content):
        content_list = []
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
                    current_content['date'] = datetime.strptime(match_date[1], '%d.%m.%y').date().strftime(
                        '%Y-%m-%d')
                if match_other:
                    current_content[k] = match_other[1]
            new_line = False

            match_text = re.search(r'.{28}(.+)', line)
            if match_text:
                current_content['text'].append(match_text[1])

        content_list = self._write_record_content(current_content, content_list)
        return content_list


class CGMParser:
    """
    Parser for lists exported from CGM M1 Pro

    supported input types:
    GO-Fehler (1. von 3 Protokollen bei der Kassenabrechnung)
    TGS (Textgruppenstatistik)
    """

    def __init__(self, raw_input):
        self.context = self._determine_context(raw_input)
        self.records = self.context.separate_records()
        self.parsed_records = self.context.parse_records(self.records)

    def _determine_context(self, raw_input):
        """assign relevant context to self.context based on raw input"""
        h = ''.join(raw_input[:3])

        if h == ParsingContextGOF.HEADER:
            logging.info('context set to GOF')
            return ParsingContextGOF(raw_input)
        elif h == ParsingContextTGS.HEADER:
            logging.info('context set to TGS')
            return ParsingContextTGS(raw_input)

    def export_csv(self, filepath):
        with open(filepath, mode='w') as f:
            fieldnames = self.parsed_records[0].get_keys()  # TODO: hacky way to get fieldnames
            csv_writer = csv.DictWriter(f, delimiter=';', fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
            csv_writer.writeheader()
            for rec in self.parsed_records:
                csv_writer.writerow(rec.repr_as_dict())

    def export_ids(self, filepath):
        with open(filepath, mode='w') as f:
            for rec in self.parsed_records:
                f.writelines(rec.pat_id + '\n')


def main(args):
    with open(args.input_path, 'r', encoding='cp1252') as f:
        data = f.readlines()

    p = CGMParser(data)
    p.export_csv('out.csv')


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
