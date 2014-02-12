# encoding=utf-8
'''Document scrapers.'''
import abc
import collections
import itertools
import re

from wpull.document import (BaseDocumentReader, HTMLReader, get_heading_encoding,
    get_encoding, CSSReader)
import wpull.url
from wpull.util import to_str


class BaseDocumentScraper(BaseDocumentReader):
    '''Base class for clases that scrape documents.'''
    @abc.abstractmethod
    def scrape(self, request, response):
        '''Extract the URLs from the document.

        Args:
            request: :class:`.http.Request`
            response: :class:`http.Response`

        Returns:
            dict, None: Returns a dict or None.

            If a dict is provided, the mandatory values are:

                * ``inline_urls``: URLs of objects embedded in the document
                * ``linked_urls``': URLs of objects linked from the document
                *  ``encoding``: the character encoding of the document

            If None, then the scraper does not support scraping the document.
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


LinkInfo = collections.namedtuple(
    'LinkInfoType',
    [
        'element', 'tag', 'attrib', 'link',
        'inline', 'linked', 'base_link', 'value_type'
    ]
)
'''Information about a link in a lxml document.

Attributes:
    element: An instance of :class:`lxml.html.HtmlElement`.
    tag (str): The element tag name.
    attrib (str, None): If ``str``, the name of the attribute. Otherwise,
        the link was found in ``element.text``.
    link (str): The link found.
    inline (bool): Whether the link is an embedded object (like images or
        stylesheets).
    linked (bool): Whether the link is a link to another page.
    base_link (str, None): The base URL.
    value_type (str): Indicates how the link was found. Possible values are

        * ``plain``: The link was found plainly in an attribute value.
        * ``list``: The link was found in a space separated list.
        * ``css``: The link was found in a CSS text.
        * ``refresh``: The link was found in a refresh meta string.
'''


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
    '''HTML element attributes that may contain links.'''
    ATTR_INLINE = 1
    '''Flag for embedded objects (like images, stylesheets) in documents.'''
    ATTR_HTML = 2
    '''Flag for links that point to other documents.'''
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
    '''Mapping of element tag names to attributes containing links.'''

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

    def scrape(self, request, response):
        if not self.is_html(request, response):
            return

        content_file = response.body.content_file
        encoding = get_heading_encoding(response)

        tree = self.parse(content_file, encoding, request.url_info.url)
        root = tree.getroot()

        if root is None:
            return

        linked_urls = set()
        inline_urls = set()

        for scraped_link in self.iter_links(root):
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

    @classmethod
    def iter_links(cls, root):
        '''Iterate the document root for links.

        Returns:
            LinkInfo: A iterator of :class:`LinkedInfo`.
        '''
        for element in root.iter():
            for scraped_link in cls.iter_links_element(element):
                yield scraped_link

    @classmethod
    def iter_links_element(cls, element):
        '''Iterate a HTML element.'''
        # reference: lxml.html.HtmlMixin.iterlinks()
        # NOTE: to_str is needed because on Python 2, only byte strings
        # are returned from lxml
        attrib = element.attrib
        tag = element.tag

        if tag == 'link':
            iterable = cls.iter_links_link_element(element)
        elif tag == 'meta':
            iterable = cls.iter_links_meta_element(element)
        elif tag in ('object', 'applet'):
            iterable = cls.iter_links_object_element(element)
        elif tag == 'param':
            iterable = cls.iter_links_param_element(element)
        elif tag == 'style':
            iterable = cls.iter_links_style_element(element)
        else:
            iterable = cls.iter_links_plain_element(element)

        for link_info in iterable:
            yield link_info

        if 'style' in attrib:
            for link in CSSScraper.scrape_urls(attrib['style']):
                yield LinkInfo(
                    element, element.tag, 'style',
                    to_str(link),
                    True, False,
                    None,
                    'css'
                )

    @classmethod
    def iter_links_link_element(cls, element):
        '''Iterate a ``link`` for URLs.

        This function handles stylesheets and icons in addition to
        standard scraping rules.
        '''
        rel = element.get('rel', '')
        inline = 'stylesheet' in rel or 'icon' in rel

        for attrib_name, link in cls.iter_links_by_attrib(element):
            yield LinkInfo(
                element, element.tag, attrib_name,
                to_str(link),
                inline, not inline,
                None,
                'plain'
            )

    @classmethod
    def iter_links_meta_element(cls, element):
        '''Iterate the ``meta`` element for links.

        This function handles refresh URLs.
        '''
        if element.get('http-equiv', '').lower() == 'refresh':
            content_value = element.get('content')
            match = re.search(r'url=(.+)', content_value, re.IGNORECASE)
            if match:
                yield LinkInfo(
                    element, element.tag, 'http-equiv',
                    to_str(match.group(1)),
                    False, True,
                    None,
                    'refresh'
                )

    @classmethod
    def iter_links_object_element(cls, element):
        '''Iterate ``object`` and ``embed`` elements.

        This function also looks at ``codebase`` and ``archive`` attributes.
        '''
        base_link = to_str(element.get('codebase', None))

        if base_link:
            # lxml returns codebase as inline
            yield LinkInfo(
                element, element.tag, 'codebase',
                base_link,
                True, False,
                None,
                'plain'
            )

        for attribute in ('code', 'src', 'classid', 'data'):
            if attribute in element.attrib:
                yield LinkInfo(
                    element, element.tag, attribute,
                    to_str(element.get(attribute)),
                    True, False,
                    base_link,
                    'plain'
                )

        if 'archive' in element.attrib:
            for match in re.finditer(r'[^ ]+', element.get('archive')):
                value = match.group(0)
                yield LinkInfo(
                    element, element.tag, 'archive',
                    to_str(value),
                    True, False,
                    base_link,
                    'list'
                )

    @classmethod
    def iter_links_param_element(cls, element):
        '''Iterate a ``param`` element.'''
        valuetype = element.get('valuetype', '')

        if valuetype.lower() == 'ref' and 'value' in element.attrib:
            yield LinkInfo(
                element, element.tag, 'value',
                to_str(element.get('value')),
                True, False,
                None,
                'plain'
            )

    @classmethod
    def iter_links_style_element(self, element):
        '''Iterate a ``style`` element.'''
        if element.text:
            link_iter = itertools.chain(
                CSSScraper.scrape_imports(element.text),
                CSSScraper.scrape_urls(element.text)
            )
            for link in link_iter:
                yield LinkInfo(
                    element, element.tag, None,
                    to_str(link),
                    True, False,
                    None,
                    'css'
                )

    @classmethod
    def iter_links_plain_element(cls, element):
        '''Iterate any element for links using generic rules.'''
        for attrib_name, link in cls.iter_links_by_attrib(element):
            inline = cls.is_link_inline(element.tag, attrib_name)
            linked = cls.is_html_link(element.tag, attrib_name)
            yield LinkInfo(
                element, element.tag, attrib_name,
                to_str(link),
                inline, linked,
                None,
                'plain'
            )

    @classmethod
    def iter_links_by_attrib(cls, element):
        '''Iterate an element by looking at its attributes for links.'''
        for attrib_name in element.keys():
            if attrib_name in cls.LINK_ATTRIBUTES:
                yield attrib_name, element.get(attrib_name)

    @classmethod
    def is_link_inline(cls, tag, attribute):
        '''Return whether the link is likely to be inline object.'''
        if tag in cls.TAG_ATTRIBUTES \
        and attribute in cls.TAG_ATTRIBUTES[tag]:
            attr_flags = cls.TAG_ATTRIBUTES[tag][attribute]
            return attr_flags & cls.ATTR_INLINE

        return attribute != 'href'

    @classmethod
    def is_html_link(cls, tag, attribute):
        '''Return whether the link is likely to be external object.'''
        if tag in cls.TAG_ATTRIBUTES \
        and attribute in cls.TAG_ATTRIBUTES[tag]:
            attr_flags = cls.TAG_ATTRIBUTES[tag][attribute]
            return attr_flags & cls.ATTR_HTML

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


class CSSScraper(CSSReader, BaseDocumentScraper):
    '''Scrapes CSS stylesheet documents.'''
    URL_PATTERN = r'''url\(\s*['"]?(.*?)['"]?\s*\)'''
    IMPORT_URL_PATTERN = r'''@import\s*([^\s]+).*?;'''

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
    def scrape_urls(cls, text):
        '''Scrape any thing that is a ``url()``.'''
        for match in re.finditer(cls.URL_PATTERN, text):
            yield match.group(1)

    @classmethod
    def scrape_imports(cls, text):
        '''Scrape any thing that looks like an import.'''
        for match in re.finditer(cls.IMPORT_URL_PATTERN, text):
            url_str_fragment = match.group(1)
            if url_str_fragment.startswith('url('):
                for url in cls.scrape_urls(url_str_fragment):
                    yield url
            else:
                yield url_str_fragment.strip('"\'')
