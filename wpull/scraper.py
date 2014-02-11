# encoding=utf-8
'''Document scrapers.'''
import abc
import collections
import itertools
import re

from wpull.document import (BaseDocumentReader, HTMLReader, get_heading_encoding,
    get_encoding)
from wpull.util import to_str
import wpull.util


class BaseDocumentScraper(BaseDocumentReader):
    '''Base class for clases that scrape documents.'''
    @abc.abstractmethod
    def scrape(self, request, response):
        '''Extract the URLs from the document.

        Args:
            request: :class:`.http.Request`
            response: :class:`http.Response`

        Returns:
            :class:`dict`: The mandatory values are:
                * ``inline_urls``: URLs of objects embedded in the document
                * ``linked_urls``': URLs of objects linked from the document
                *  ``encoding``: the character encoding of the document
        '''
        pass


class DemuxDocumentScraper(object):
    '''Puts multiple Document Scrapers into one.'''
    def __init__(self, document_scrapers):
        self._document_scrapers = document_scrapers

    def scrape(self, request, response):
        '''Iterate the scrapers, returning the first of the results.'''
        for scraper in self._document_scrapers:
            scrape_info = scraper.scrape(request, response)

            if scrape_info is None:
                continue

            if scrape_info['inline_urls'] or scrape_info['linked_urls']:
                return scrape_info

    def scrape_info(self, request, response):
        '''Iterate the scrapers and return a dict of results.

        Returns:
            dict: A dict where the keys are the scrapers instances and the
            values are the results. That is, a mapping from
            :class:`BaseDocumentScraper` to :class:`dict`.
        '''
        info = {}
        for scraper in self._document_scrapers:
            scrape_info = scraper.scrape(request, response)
            info[scraper] = scrape_info

        return info


ScrapedLink = collections.namedtuple(
    'ScrapedLinkType',
    ['tag', 'attrib', 'link', 'inline', 'linked', 'base_link']
)
'''Information about the scraped link.'''


class HTMLScraper(HTMLReader, BaseDocumentScraper):
    '''Scraper for HTML documents.

    Args:
        followed_tags: A list of tags that should be scraped
        ignored_tags: A list of tags that should not be scraped
        robots: If True, discard any links if they cannot be followed
        only_relative: If True, discard any links that are not absolute paths
    '''
    LINK_ATTRIBUTES = frozenset([
        'action', 'archive', 'background', 'cite', 'classid',
        'codebase', 'data', 'href', 'longdesc', 'profile', 'src',
        'usemap',
        'dynsrc', 'lowsrc',
    ])
    ATTR_INLINE = 1
    ATTR_HTML = 2
    TAG_ATTRIBUTES = {
        'a': {'href': ATTR_HTML},
        'applet': {'code': ATTR_INLINE},
        'area': {'href': ATTR_HTML},
        'bgsound': {'src': ATTR_INLINE},
        'body': {'background': ATTR_INLINE},
        'embed': {'href': ATTR_HTML, 'src': ATTR_INLINE | ATTR_HTML},
        'fig': {'src': ATTR_INLINE},
        'form': {'action': ATTR_HTML},
        'frame': {'src': ATTR_INLINE | ATTR_HTML},
        'iframe': {'src': ATTR_INLINE | ATTR_HTML},
        'img': {
            'href': ATTR_INLINE, 'lowsrc': ATTR_INLINE, 'src': ATTR_INLINE},
        'input': {'src': ATTR_INLINE},
        'layer': {'src': ATTR_INLINE | ATTR_HTML},
        'object': {'data': ATTR_INLINE},
        'overlay': {'src': ATTR_INLINE | ATTR_HTML},
        'script': {'src': ATTR_INLINE},
        'table': {'background': ATTR_INLINE},
        'td': {'background': ATTR_INLINE},
        'th': {'background': ATTR_INLINE},
    }

    def __init__(self, followed_tags=None, ignored_tags=None, robots=False,
    only_relative=False):
        super().__init__()
        self._robots = robots
        self._only_relative = only_relative

        if followed_tags is not None:
            self._followed_tags = frozenset(
                [tag.lower() for tag in followed_tags])
        else:
            self._followed_tags = None

        if ignored_tags is not None:
            self._ignored_tags = frozenset(
                [tag.lower() for tag in ignored_tags])
        else:
            self._ignored_tags = None

    @classmethod
    def is_html(cls, request, response):
        '''Check if the response is likely to be HTML.'''
        if 'html' in response.fields.get('content-type', '').lower() \
        or '.htm' in request.url_info.path.lower():
            return True

        if response.body:
            peeked_data = wpull.util.peek_file(
                response.body.content_file).lower()
            if b'html' in peeked_data:
                return True

    def scrape(self, request, response):
        if not self.is_html(request, response):
            return

        content_file = response.body.content_file
        encoding = get_heading_encoding(response)

        root = self.parse(content_file, encoding, request.url_info.url)

        if root is None:
            return

        linked_urls = set()
        inline_urls = set()

        for scraped_link in self._scrape_tree(root):
            if self._only_relative:
                if scraped_link.base_link or '://' in scraped_link.link:
                    continue

            if not self._is_accepted(scraped_link.tag):
                continue

            base_url = root.base_url

            if scraped_link.base_link:
                base_url = wpull.url.urljoin(base_url, scraped_link.base_link)

            url = wpull.url.urljoin(base_url, scraped_link.link,
                allow_fragments=False)

            if scraped_link.inline:
                inline_urls.add(url)
            if scraped_link.linked:
                linked_urls.add(url)

        if self._robots and self._robots_cannot_follow(root):
            linked_urls.clear()

        return {
            'inline_urls': inline_urls,
            'linked_urls': linked_urls,
            'base_url': to_str(root.base_url),
            'encoding': to_str(root.getroottree().docinfo.encoding),
        }

    def _scrape_tree(self, root):
        '''Iterate the document tree.'''
        for element in root.iter():
            for scraped_link in self._scrape_element(element):
                yield scraped_link

    def _scrape_element(self, element):
        '''Scrape a HTML elmement.'''
        # reference: lxml.html.HtmlMixin.iterlinks()
        attrib = element.attrib
        tag = element.tag

        if tag == 'link':
            iterable = self._scrape_link_element(element)
        elif tag == 'meta':
            iterable = self._scrape_meta_element(element)
        elif tag in ('object', 'applet'):
            iterable = self._scrape_object_element(element)
        elif tag == 'param':
            iterable = self._scrape_param_element(element)
        elif tag == 'style':
            iterable = self._scrape_style_element(element)
        else:
            iterable = self._scrape_plain_element(element)

        for scraped_link in iterable:
            yield scraped_link

        if 'style' in attrib:
            for link in CSSScraper.scrape_urls(attrib['style']):
                yield ScrapedLink(
                    element.tag, 'style',
                    to_str(link), True,
                    False, None)

    def _scrape_link_element(self, element):
        '''Scrape a ``link`` for URLs.

        This function handles stylesheets and icons in addition to
        standard scraping rules.
        '''
        rel = element.get('rel', '')
        inline = 'stylesheet' in rel or 'icon' in rel

        for attrib_name, link in self._scrape_links_by_attrib(element):
            yield ScrapedLink(
                element.tag, attrib_name,
                to_str(link), inline,
                not inline, None
            )

    def _scrape_meta_element(self, element):
        '''Scrape the ``meta`` element.

        This function handles refresh URLs.
        '''
        if element.get('http-equiv', '').lower() == 'refresh':
            content_value = element.get('content')
            match = re.search(r'url=(.+)', content_value, re.IGNORECASE)
            if match:
                yield ScrapedLink(
                    element.tag, 'http-equiv',
                    to_str(match.group(1)), False,
                    True, None
                )

    def _scrape_object_element(self, element):
        '''Scrape ``object`` and ``embed`` elements.

        This function also looks at ``codebase`` and ``archive`` attributes.
        '''
        base_link = to_str(element.get('codebase', None))

        if base_link:
            # lxml returns codebase as inline
            yield ScrapedLink(
                element.tag, 'codebase',
                base_link, True,
                False, None
            )

        for attribute in ('code', 'src', 'classid', 'data'):
            if attribute in element.attrib:
                yield ScrapedLink(
                    element.tag, attribute,
                    to_str(element.get(attribute)), True,
                    False, base_link
                )

        if 'archive' in element.attrib:
            for match in re.finditer(r'[^ ]+', element.get('archive')):
                value = match.group(0)
                yield ScrapedLink(
                    element.tag, 'archive',
                    to_str(value), True,
                    False, base_link
                )

    def _scrape_param_element(self, element):
        '''Scrape a ``param`` element.'''
        valuetype = element.get('valuetype', '')

        if valuetype.lower() == 'ref' and 'value' in element.attrib:
            yield ScrapedLink(
                element.tag, 'value',
                to_str(element.get('value')), True,
                False, None)

    def _scrape_style_element(self, element):
        '''Scrape a ``style`` element.'''
        if element.text:
            link_iter = itertools.chain(
                CSSScraper.scrape_imports(element.text),
                CSSScraper.scrape_urls(element.text)
            )
            for link in link_iter:
                yield ScrapedLink(
                    element.tag, None,
                    to_str(link), True,
                    False, None
                )

    def _scrape_plain_element(self, element):
        '''Scrape any element using generic rules.'''
        for attrib_name, link in self._scrape_links_by_attrib(element):
            inline = self._is_link_inline(element.tag, attrib_name)
            linked = self._is_html_link(element.tag, attrib_name)
            yield ScrapedLink(
                element.tag, attrib_name,
                to_str(link), inline,
                linked, None
            )

    def _scrape_links_by_attrib(self, element):
        '''Scrape an element by looking at its attributes.'''
        for attrib_name in element.keys():
            if attrib_name in self.LINK_ATTRIBUTES:
                yield attrib_name, element.get(attrib_name)

    def _is_link_inline(self, tag, attribute):
        '''Return whether the link is likely to be inline object.'''
        if tag in self.TAG_ATTRIBUTES \
        and attribute in self.TAG_ATTRIBUTES[tag]:
            attr_flags = self.TAG_ATTRIBUTES[tag][attribute]
            return attr_flags & self.ATTR_INLINE

        return attribute != 'href'

    def _is_html_link(self, tag, attribute):
        '''Return whether the link is likely to be external object.'''
        if tag in self.TAG_ATTRIBUTES \
        and attribute in self.TAG_ATTRIBUTES[tag]:
            attr_flags = self.TAG_ATTRIBUTES[tag][attribute]
            return attr_flags & self.ATTR_HTML

        return attribute == 'href'

    def _is_accepted(self, element_tag):
        '''Return if the link is accepted by the filters.'''
        element_tag = element_tag.lower()

        if self._ignored_tags is not None \
        and element_tag in self._ignored_tags:
            return False

        if self._followed_tags is not None:
            return element_tag in self._followed_tags
        else:
            return True

    def _robots_cannot_follow(self, root):
        '''Return whether we can follow links due to robots.txt directives.'''
        for element in root.iter('meta'):
            if element.get('name', '').lower() == 'robots':
                if 'nofollow' in element.get('value', '').lower():
                    return True


class CSSScraper(BaseDocumentScraper):
    '''Scrapes CSS stylesheet documents.'''

    def parse(self, *args, **kwargs):
        raise NotImplementedError()

    def scrape(self, request, response):
        if not self.is_css(request, response):
            return

        base_url = request.url_info.url
        inline_urls = set()
        encoding = get_encoding(response)
        text = response.body.content.decode(encoding)
        iterable = itertools.chain(self.scrape_urls(text),
            self.scrape_imports(text))

        for link in iterable:
            inline_urls.add(wpull.url.urljoin(base_url, link,
                allow_fragments=False))

        return {
            'inline_urls': inline_urls,
            'linked_urls': (),
            'encoding': encoding,
        }

    @classmethod
    def is_css(cls, request, response):
        '''Return whether the document is likely to be CSS.'''
        if 'css' in response.fields.get('content-type', '').lower() \
        or '.css' in request.url_info.path.lower():
            return True

        if response.body:
            peeked_data = wpull.util.peek_file(
                response.body.content_file).lower()
            if 'html' in response.fields.get('content-type', '').lower() \
            and b'<html' not in peeked_data.lower() \
            and b'{' in peeked_data \
            and b'}' in peeked_data \
            and b':' in peeked_data:
                return True

    @classmethod
    def scrape_urls(cls, text):
        '''Scrape any thing that is a ``url()``.'''
        for match in re.finditer(r'''url\(\s*['"]?(.*?)['"]?\s*\)''', text):
            yield match.group(1)

    @classmethod
    def scrape_imports(cls, text):
        '''Scrape any thing that looks like an import.'''
        for match in re.finditer(r'''@import\s*([^\s]+).*?;''', text):
            url_str_fragment = match.group(1)
            if url_str_fragment.startswith('url('):
                for url in cls.scrape_urls(url_str_fragment):
                    yield url
            else:
                yield url_str_fragment.strip('"\'')
