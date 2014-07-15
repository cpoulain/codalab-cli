'''
worksheet_util contains the following public functions:
- get_current_items: get the current items of a worksheet.
- request_new_items: pops up an editor to allow for full-text editing of a worksheet.
'''
import os
import re
import subprocess
import sys
import tempfile

from codalab.common import UsageError


BUNDLE_LINE_REGEX = '^(\[(.*)\])?\s*\{(.*)\}$'
DIRECTIVE_PREFIX = r'%'
BUNDLE_DISPLAY_DIRECTIVE = DIRECTIVE_PREFIX + r' display (table|default|inline)'
BUNDLE_DISPLAY_FIELD = DIRECTIVE_PREFIX + r' ([^\:]+): (image|metadata)/(.*)'
WORKSHEET_TITLE_FIELD = DIRECTIVE_PREFIX + r'\s*title:\s*(.*)'
WORKSHEET_DESCRIPTION_FIELD = DIRECTIVE_PREFIX + r'\s*description:\s*(.*)'

MATCH_DISPLAY_EXPR = re.compile('.*' + BUNDLE_DISPLAY_DIRECTIVE + '.*', re.DOTALL)
MATCH_FIELD_EXPR = re.compile('.*' + BUNDLE_DISPLAY_FIELD + '.*', re.DOTALL)
MATCH_DISPLAY_DIRECTIVE_EXPR = re.compile('^' + BUNDLE_DISPLAY_DIRECTIVE + '$')
MATCH_FIELD_DIRECTIVE_EXPR = re.compile('^' + BUNDLE_DISPLAY_FIELD + '$')
MATCH_TITLE_DIRECTIVE_EXPR = re.compile('^' + WORKSHEET_TITLE_FIELD + '$')
MATCH_DESCRIPTION_DIRECTIVE_EXPR = re.compile('^' + WORKSHEET_DESCRIPTION_FIELD + '$')

def expand_worksheet_item_info(value, type):
    '''
    Expands a worksheet item appropiately considering all bundle types.
    '''
    if type == 'directive':
        data = {
            'type': 'directive',
            'name': None,
            'path': None,
            'value': None,
        }
        match_display = MATCH_DISPLAY_EXPR.match(value)
        if match_display:
            return {
                'type': 'directive',
                'directive': 'display',
                'display': match_display.group(1),
                'markup': match_display.group(0),
            }
        else:
            match_field = MATCH_FIELD_EXPR.match(value)
            if match_field:
                return {
                    'type': 'directive',
                    'directive': match_field.group(2),
                    'name': match_field.group(1),
                    'path': match_field.group(3),
                    'markup': match_field.group(0),
                }
        return data
    return value

def get_worksheet_lines(worksheet_info):
    '''
    Generator that returns pretty-printed lines of text for the given worksheet.
    '''
    for (bundle_info, value, type) in worksheet_info['items']:
        if type == 'directive':
            yield value['markup']
        elif type in ('title', 'description'):
            yield '% {0}: {1}'.format(type, value)
        elif bundle_info is None:
            yield value
        else:
            if 'bundle_type' not in bundle_info:
                yield '// The following bundle reference is broken:'
            yield '[%s]{%s}' % (value, bundle_info['uuid'])


def get_current_items(worksheet_info):
    '''
    Return list of (bundle_uuid, value, type) pairs.
    Note: worksheet_info['items'] contains (bundle_info, value)
    '''
    items = []
    for (bundle_info, value, type) in worksheet_info['items']:
        if bundle_info is None:
            items.append((None, value, type))
        else:
            items.append((bundle_info['uuid'], value, type))
    return items


def request_new_items(worksheet_info):
    '''
    Input: a worksheet info dict.
    Popup an editor, populated with the current worksheet contents.
    Return a list of new items that the user typed into the editor.
    '''
    header = '''
// Full-text editing for worksheet %s. This file is basically Markdown, except
// that is used for comments and that lines of the form {bundle_spec} are
// resolved as links to CodaLab bundles. You can even preface the curly braces
// with bracketed help text, like so: [some explanatory text]{bundle_spec}
    '''.strip() % (worksheet_info['name'],)
    # Construct a form template with the current value of the worksheet.
    template_lines = header.split('\n')
    template_lines.extend(get_worksheet_lines(worksheet_info))
    template = os.linesep.join(template_lines)
    # Show the form to the user in their editor of choice and parse the result.
    editor = os.environ.get('EDITOR', 'notepad' if sys.platform == 'win32' else 'vim')
    tempfile_name = ''
    with tempfile.NamedTemporaryFile(suffix='.c', delete=False) as form:
        form.write(template)
        form.flush()
        tempfile_name = form.name
    lines = template_lines
    if os.path.isfile(tempfile_name):
        subprocess.call([editor, tempfile_name])
        with open(tempfile_name, 'rb') as form:
            lines = form.readlines()
        os.remove(tempfile_name)
    form_result = [line[:-1] if line.endswith('\n') else line for line in lines]
    if form_result == template_lines:
        raise UsageError('No change made; aborting')
    return parse_worksheet_form(form_result)

def parse_worksheet_form_bundle(match):
    # Return a (bundle_uuid, value, type) pair out of the bundle line.
    # Note that the value could be None (if there was no [])
    value = match.group(2)
    value = value if value is None else value.strip()
    return (match.group(3).strip(), value, 'bundle')

def parse_worksheet_form_display(match):
    return (None, match.group(0), 'directive')

parse_worksheet_parse_table = {
    BUNDLE_LINE_REGEX: parse_worksheet_form_bundle,
    BUNDLE_DISPLAY_DIRECTIVE: parse_worksheet_form_display,
    BUNDLE_DISPLAY_FIELD: parse_worksheet_form_display,
    WORKSHEET_TITLE_FIELD: (lambda m: (None, m.group(1), 'title')),
    WORKSHEET_DESCRIPTION_FIELD: (lambda m: (None, m.group(1), 'description')),
}
parse_worksheet_parse_table_exprs = {
    k: re.compile(k) for k in parse_worksheet_parse_table
}

def parse_worksheet_form(form_result):
    '''
    Parse the result of a form template produced in request_missing_metadata.
    Return a list of (bundle_uuid, value, type) tuples, where bundle_uuid could be None.
    '''
    result = []
    for line in form_result:
        line = line.strip()
        if line[:2] == '//':
            continue
        current_result = (None, line, 'markup')
        # Loop for each regexp and to check and apply a match
        for line_parser in parse_worksheet_parse_table:
            match = parse_worksheet_parse_table_exprs[line_parser].match(line)
            if match:
                current_result = parse_worksheet_parse_table[line_parser](match)
                break
        result.append(current_result)
    return result
