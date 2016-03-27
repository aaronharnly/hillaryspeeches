#!/usr/bin/env python
"""
Scrapes Presidential debates from the UCSB American Presidency Project.

Creates YAML files named by date, with the raw text scraped from the site.
Subsequent scripts or hand-munging are required to properly annotate the speakers.
"""
from io import StringIO
from collections import OrderedDict
from datetime import datetime
import os
import re
import sys

from bs4 import BeautifulSoup
import dateparser
import requests
import yaml

INDEX_URL="http://www.presidency.ucsb.edu/debates.php"


#
# HTTP
#
def scrape(url):
    """Fetch the given URL as a BeautifulSoup parser"""
    r = requests.get(url)
    return BeautifulSoup(r.text, 'html.parser')


#
# YAML
#
def _represent_ordereddict(dumper, data):
    """From http://stackoverflow.com/questions/16782112/can-pyyaml-dump-dict-items-in-non-alphabetical-order/16782282#16782282"""
    value = []
    for item_key, item_value in data.items():
        node_key = dumper.represent_data(item_key)
        node_value = dumper.represent_data(item_value)
        value.append((node_key, node_value))
    return yaml.nodes.MappingNode(u'tag:yaml.org,2002:map', value)

yaml.add_representer(OrderedDict, _represent_ordereddict)

def _represent_str(dumper, data):
    """From http://stackoverflow.com/questions/8640959/how-can-i-control-what-scalar-form-pyyaml-uses-for-my-data"""
    if len(data.splitlines()) > 1:
        # for multiline strings, use the > style
        return dumper.represent_scalar('tag:yaml.org,2002:str', data, style=">")
    return dumper.represent_scalar('tag:yaml.org,2002:str', data)

yaml.add_representer(str, _represent_str)

#
# Parsing links & debates
#

# debate links will have <td>s with these CSS classes
DEBATE_CLASSES = ['docdate', 'doctext']

def _row_to_debate(row):
    """Extract a debate from a <tr> containing links"""
    try:
        date_td = row.find('td', class_='docdate')
        text_td = row.find('td', class_='doctext')
        link = text_td.a
        return {
            "url": link.get('href') if link else None,
            "title": text_td.get_text().strip(),
            "date": dateparser.parse(date_td.get_text()).date()
        }
    except Exception as ex:
        sys.stderr.write("Failed to parse row: {}.\nException: {}\n".format(row, ex))
        return None

def fetch_debate_list():
    """
    Get a list of debates to download.
    """
    parser = scrape(INDEX_URL)
    rows = parser.find_all('tr')
    rows_with_debates = [
        row
        for row in rows
        if [
            klass
            for child in row.find_all('td')
            for klass in child.get('class', [])
        ] == DEBATE_CLASSES
    ]
    debates = [_row_to_debate(row) for row in rows_with_debates]
    return debates

def _text_walker(soup, writer):
    # We use an explicit stack, because the broken HTML on these pages
    # will exceed the recursion depth if we do the recursive call
    stack = []
    stack.append(soup)

    while stack:
        current = stack.pop()
        if current.name is None:
            # (This is a NavigableString)
            writer.write(current.string)
        else:
            if current.name in ['br', 'p']:
                # Note that the debate pages have broken HTML, with <p> tags without
                # closing </p> tags. Ordinarily we would process the newline for <p>
                # tags at the close of the tag
                writer.write("\n")
            # note that we reverse the order, so that the first child is at the top of the stack
            for child in reversed(list(current.children)):
                stack.append(child)

TRAILING_WHITESPACE_RE = re.compile(r"\s+$", re.MULTILINE)

def _extract_text(soup):
    """Given a debate HTML node, extract the debate text"""
    text_node = soup.find('span', class_='displaytext')
    text_writer = StringIO()
    _text_walker(text_node, text_writer)
    text = text_writer.getvalue()
    cleaned = TRAILING_WHITESPACE_RE.sub("", text)
    return cleaned

def fetch_debate(debate_ref):
    """
    Given a debate URL, return the debate as a dict.
    """
    url = debate_ref['url']
    parser = scrape(url)
    text = _extract_text(parser)

    return OrderedDict([
        ("speakers-of-interest", []),
        ("src", url),
        ("src-date", debate_ref['date']),
        ("index", INDEX_URL),
        ("type", "debate"),
        ("title", debate_ref['title']),
        ("raw-text", text)
    ])

def write_debate(debate, filehandle):
    """
    Render a debate as YAML to the given open filehandle
    """
    filehandle.write(yaml.dump(debate, allow_unicode=True))

def main(args):
    """
    Given an output directory, fetch Presidential debates and write
    them out as YAML files by date.
    """
    if len(args) < 1:
        sys.stderr.write("No output directory given!")
        sys.stderr.write("Usage: debates-scrape.py <output-dir>")
        sys.exit(1)
    output_dir = args[1]
    debate_refs = fetch_debate_list()
    for debate_ref in debate_refs:
        if debate_ref['url']:
            sys.stderr.write("Fetching {}\n".format(debate_ref['url']))
            debate = fetch_debate(debate_ref)
            filename = "{}a.yml".format(debate_ref['date'].isoformat())
            filepath = os.path.join(output_dir, filename)
            with open(filepath, 'w') as filehandle:
                write_debate(debate, filehandle)
                sys.stderr.write(" Wrote {}\n".format(filepath))
        else:
            sys.stderr.write("No URL for debate '{}'; skipping\n".format(debate_ref['title']))


if __name__ == '__main__':
    main(sys.argv)
