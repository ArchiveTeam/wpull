# encoding=utf-8
'''Document scrapers.'''
import abc
import collections
import gettext
import itertools
import logging
import mimetypes
import re

import lxml.etree

from wpull.document import (BaseDocumentReader, HTMLReader,
    detect_response_encoding, CSSReader, SitemapReader, JavaScriptReader)
import wpull.url


_ = gettext.gettext
_logger = logging.getLogger(__name__)


ScrapedLinkResult = collections.namedtuple(
    'ScrapedLinkResultType',
    ['link', 'inline', 'encoding']
)
'''A named tuple decribing a scraped link.

Attributes:
    link (str): The link that was scraped.
    inline (bool): Whether the link is an embeded object.
    encoding (str): The character encoding of the link.
'''


class BaseDocumentScraper(BaseDocumentReader):
    '''Base class for clases that scrape documents.'''
    @abc.abstractmethod
    def scrape(self, request, response):
        '''Extract the URLs from the document.

        Args:
            request (:class:`.http.request.Request`): The request.
            response (:class:`http.request.Response`): The response.

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
    element: An instance of :class:`.document.HTMLReadElement`.
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
        * ``script``: The link was found in JavaScript text.
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
    only_relative=False, encoding_override=None):
        super().__init__()
        self._robots = robots
        self._only_relative = only_relative
        self._encoding_override = encoding_override

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
        if not self.is_supported(request=request, response=response):
            return

        base_url = request.url_info.url
        content_file = response.body.content_file
        encoding = self._encoding_override \
            or detect_response_encoding(response, is_html=True)
        linked_urls = set()
        inline_urls = set()

        try:
            with wpull.util.reset_file_offset(content_file):
                elements = self.read_links(content_file, encoding=encoding)

                result_meta_info = self._process_elements(
                    elements, response, base_url, linked_urls, inline_urls
                )

        except (UnicodeError, lxml.etree.LxmlError) as error:
            _logger.warning(
                _('Failed to read document at ‘{url}’: {error}')\
                .format(url=request.url_info.url, error=error)
            )
            result_meta_info = {}

        if result_meta_info.get('robots_no_follow'):
            linked_urls.clear()

        return {
            'inline_urls': inline_urls,
            'linked_urls': linked_urls,
            'base_url': base_url,
            'encoding': encoding,
        }

    def _process_elements(self, elements, response, base_url, linked_urls,
    inline_urls):
        robots_check_needed = self._robots
        robots_no_follow = False
        inject_refresh = True
        doc_base_url = None

        for element in elements:
            if robots_check_needed and self.robots_cannot_follow(element):
                robots_check_needed = False
                robots_no_follow = True

            if not doc_base_url and element.tag == 'base':
                doc_base_url = urljoin_safe(
                    base_url, clean_link_soup(element.attrib.get('href', ''))
                )

            link_infos = self.iter_links_element(element)

            if inject_refresh and 'Refresh' in response.fields:
                link = parse_refresh(response.fields['Refresh'])

                if link:
                    link_info = LinkInfo(
                        None, '_refresh', None,
                        link,
                        False, True,
                        None, 'refresh'
                    )
                    link_infos = itertools.chain(link_infos, [link_info])

                inject_refresh = False
            else:
                inject_refresh = False

            for link_info in link_infos:
                if self._only_relative:
                    if link_info.base_link or '://' in link_info.link:
                        continue

                if not self._is_accepted(link_info.tag):
                    continue

                element_base_url = doc_base_url or base_url

                if link_info.base_link:
                    clean_base_url = clean_link_soup(link_info.base_link)

                    if clean_base_url:
                        element_base_url = urljoin_safe(
                            base_url, clean_base_url
                        ) or base_url

                url = urljoin_safe(
                    element_base_url,
                    clean_link_soup(link_info.link),
                    allow_fragments=False
                )

                if url:
                    if link_info.inline:
                        inline_urls.add(url)
                    if link_info.linked:
                        linked_urls.add(url)

        return {'robots_no_follow': robots_no_follow}

    @classmethod
    def scrape_file(self, file, encoding=None, base_url=None):
        '''Scrape a file for links.

        See :meth:`scrape` for the return value.
        '''
        scraper = HTMLScraper()
        elements = scraper.read_links(file, encoding=encoding)

        linked_urls = set()
        inline_urls = set()

        link_infos = self.iter_links(elements)

        for link_info in link_infos:
            element_base_url = base_url

            if link_info.base_link:
                clean_base_url = clean_link_soup(link_info.base_link)

                if element_base_url and base_url:
                    element_base_url = urljoin_safe(
                        base_url, clean_base_url
                    ) or base_url

            url = urljoin_safe(
                element_base_url,
                clean_link_soup(link_info.link),
                allow_fragments=False
            )

            if url:
                if link_info.inline:
                    inline_urls.add(url)
                if link_info.linked:
                    linked_urls.add(url)

        return {
            'inline_urls': inline_urls,
            'linked_urls': linked_urls,
            'base_url': base_url,
            'encoding': encoding,
        }

    @classmethod
    def iter_links(cls, elements):
        '''Iterate the document root for links.

        Returns:
            iterable: A iterator of :class:`LinkedInfo`.
        '''
        for element in elements:
            for link_infos in cls.iter_links_element(element):
                yield link_infos

    @classmethod
    def iter_links_element(cls, element):
        '''Iterate a HTML element.'''
        # reference: lxml.html.HtmlMixin.iterlinks()
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
        elif tag == 'script':
            iterable = cls.iter_links_script_element(element)
        else:
            iterable = cls.iter_links_plain_element(element)

        # RSS/Atom
        if tag in ('link', 'url', 'icon'):
            iterable = itertools.chain(
                iterable, cls.iter_links_element_text(element)
            )

        for link_info in iterable:
            yield link_info

        if 'style' in attrib:
            for link in CSSScraper.scrape_urls(attrib['style']):
                yield LinkInfo(
                    element, element.tag, 'style',
                    link,
                    True, False,
                    None,
                    'css'
                )

    @classmethod
    def iter_links_element_text(cls, element):
        '''Get the element text as a link.'''
        if element.text:
            yield LinkInfo(
                element, element.tag, None,
                element.text,
                False, True,
                None,
                'plain'
            )

    @classmethod
    def iter_links_link_element(cls, element):
        '''Iterate a ``link`` for URLs.

        This function handles stylesheets and icons in addition to
        standard scraping rules.
        '''
        rel = element.attrib.get('rel', '')
        inline = 'stylesheet' in rel or 'icon' in rel

        for attrib_name, link in cls.iter_links_by_attrib(element):
            yield LinkInfo(
                element, element.tag, attrib_name,
                link,
                inline, not inline,
                None,
                'plain'
            )

    @classmethod
    def iter_links_meta_element(cls, element):
        '''Iterate the ``meta`` element for links.

        This function handles refresh URLs.
        '''
        if element.attrib.get('http-equiv', '').lower() == 'refresh':
            content_value = element.attrib.get('content')

            if content_value:
                link = parse_refresh(content_value)

                if link:
                    yield LinkInfo(
                        element, element.tag, 'http-equiv',
                        link,
                        False, True,
                        None,
                        'refresh'
                    )

    @classmethod
    def iter_links_object_element(cls, element):
        '''Iterate ``object`` and ``embed`` elements.

        This function also looks at ``codebase`` and ``archive`` attributes.
        '''
        base_link = element.attrib.get('codebase', None)

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
                    element.attrib.get(attribute),
                    True, False,
                    base_link,
                    'plain'
                )

        if 'archive' in element.attrib:
            for match in re.finditer(r'[^ ]+', element.attrib.get('archive')):
                value = match.group(0)
                yield LinkInfo(
                    element, element.tag, 'archive',
                    value,
                    True, False,
                    base_link,
                    'list'
                )

    @classmethod
    def iter_links_param_element(cls, element):
        '''Iterate a ``param`` element.'''
        valuetype = element.attrib.get('valuetype', '')

        if valuetype.lower() == 'ref' and 'value' in element.attrib:
            yield LinkInfo(
                element, element.tag, 'value',
                element.attrib.get('value'),
                True, False,
                None,
                'plain'
            )

    @classmethod
    def iter_links_style_element(cls, element):
        '''Iterate a ``style`` element.'''
        if element.text:
            link_iter = itertools.chain(
                CSSScraper.scrape_imports(element.text),
                CSSScraper.scrape_urls(element.text)
            )
            for link in link_iter:
                yield LinkInfo(
                    element, element.tag, None,
                    link,
                    True, False,
                    None,
                    'css'
                )

    @classmethod
    def iter_links_script_element(cls, element):
        '''Iterate a ``script`` element.'''
        if element.text:
            link_iter = JavaScriptScraper.scrape_links(element.text)

            for link in link_iter:
                inline = is_likely_inline(link)

                yield LinkInfo(
                    element, element.tag, None,
                    link,
                    inline, not inline,
                    None,
                    'script'
                )

        for link in cls.iter_links_plain_element(element):
            yield link

    @classmethod
    def iter_links_plain_element(cls, element):
        '''Iterate any element for links using generic rules.'''
        for attrib_name, link in cls.iter_links_by_attrib(element):
            if attrib_name in cls.LINK_ATTRIBUTES:
                inline = cls.is_link_inline(element.tag, attrib_name)
                linked = cls.is_html_link(element.tag, attrib_name)
            else:
                inline = is_likely_inline(link)
                linked = not inline

            yield LinkInfo(
                element, element.tag, attrib_name,
                link,
                inline, linked,
                None,
                'plain'
            )

    @classmethod
    def iter_links_by_attrib(cls, element):
        '''Iterate an element by looking at its attributes for links.'''
        for attrib_name in element.attrib.keys():
            attrib_value = element.attrib.get(attrib_name)

            if attrib_name in cls.LINK_ATTRIBUTES:
                if attrib_value.lstrip().startswith('javascript:'):
                    for link in cls.iter_links_by_js_attrib(attrib_name,
                    attrib_value):
                        yield link
                else:
                    yield attrib_name, attrib_value

            elif attrib_name[:5] in ('onkey', 'oncli', 'onmou'):
                for link in cls.iter_links_by_js_attrib(attrib_name,
                attrib_value):
                    yield link

            elif attrib_name.startswith('data-'):
                if wpull.url.is_likely_link(attrib_value) \
                and not wpull.url.is_unlikely_link(attrib_value):
                    yield attrib_name, attrib_value

    @classmethod
    def iter_links_by_js_attrib(cls, attrib_name, attrib_value):
        '''Iterate links of a JavaScript pseudo-link attribute.'''
        links = JavaScriptScraper.scrape_links(attrib_value)

        for link in links:
            yield attrib_name, link

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

    @classmethod
    def robots_cannot_follow(self, element):
        '''Return whether we cannot follow links due to robots.txt directives.
        '''
        return (
            element.tag == 'meta'
            and element.attrib.get('name', '').lower() == 'robots'
            and 'nofollow' in element.attrib.get('value', '').lower()
        )


class CSSScraper(CSSReader, BaseDocumentScraper):
    '''Scrapes CSS stylesheet documents.'''
    def __init__(self, encoding_override=None):
        super().__init__()
        self._encoding_override = encoding_override

    def scrape(self, request, response):
        if not self.is_supported(request=request, response=response):
            return

        scraped_links = self.iter_scrape(request, response)
        inline_urls = set()
        encoding = 'latin1'

        try:
            for scraped_link in scraped_links:
                encoding = scraped_link.encoding
                inline_urls.add(scraped_link.link)

        except UnicodeError as error:
            _logger.warning(
                _('Failed to read document at ‘{url}’: {error}')\
                .format(url=request.url_info.url, error=error)
            )

        return {
            'inline_urls': inline_urls,
            'linked_urls': (),
            'encoding': encoding,
        }

    def iter_scrape(self, request, response):
        if not self.is_supported(request=request, response=response):
            return

        base_url = request.url_info.url
        encoding = self._encoding_override \
            or detect_response_encoding(response)

        with wpull.util.reset_file_offset(response.body.content_file):
            for link in self.read_links(response.body.content_file, encoding):
                link = urljoin_safe(base_url, link, allow_fragments=False)

                if link:
                    yield ScrapedLinkResult(link, True, encoding)


class JavaScriptScraper(JavaScriptReader, BaseDocumentScraper):
    '''Scrapes JavaScript documents.'''
    def __init__(self, encoding_override=None):
        super().__init__()
        self._encoding_override = encoding_override

    def scrape(self, request, response):
        if not self.is_supported(request=request, response=response):
            return

        scraped_links = self.iter_scrape(request, response)
        inline_urls = set()
        linked_urls = set()
        encoding = 'latin1'

        try:
            for scraped_link in scraped_links:
                encoding = scraped_link.encoding

                if is_likely_inline(scraped_link.link):
                    inline_urls.add(scraped_link.link)
                else:
                    linked_urls.add(scraped_link.link)

        except UnicodeError as error:
            _logger.warning(
                _('Failed to read document at ‘{url}’: {error}')\
                .format(url=request.url_info.url, error=error)
            )

        return {
            'inline_urls': inline_urls,
            'linked_urls': linked_urls,
            'encoding': encoding,
        }

    def iter_scrape(self, request, response):
        if not self.is_supported(request=request, response=response):
            return

        base_url = request.url_info.url
        encoding = self._encoding_override \
            or detect_response_encoding(response)

        with wpull.util.reset_file_offset(response.body.content_file):
            for link in self.read_links(response.body.content_file, encoding):
                link = urljoin_safe(base_url, link, allow_fragments=False)

                if link:
                    yield ScrapedLinkResult(link, True, encoding)


class SitemapScraper(SitemapReader, BaseDocumentScraper):
    '''Scrape Sitemaps'''
    def __init__(self, encoding_override=None):
        super().__init__()
        self._encoding_override = encoding_override

    def scrape(self, request, response):
        if not self.is_supported(request=request, response=response):
            return

        base_url = request.url_info.url
        encoding = self._encoding_override \
            or detect_response_encoding(response)
        links = set()

        try:
            with wpull.util.reset_file_offset(response.body.content_file):
                link_iter = self.read_links(
                    response.body.content_file, encoding=encoding
                )

                for link in link_iter:
                    link = urljoin_safe(
                        base_url,
                        clean_link_soup(link)
                    )

                    if link:
                        links.add(link)

        except (UnicodeError, lxml.etree.LxmlError) as error:
            _logger.warning(
                _('Failed to read document at ‘{url}’: {error}')\
                .format(url=request.url_info.url, error=error)
            )

        return {
            'inline_urls': (),
            'linked_urls': links,
            'encoding': encoding
        }


def parse_refresh(text):
    '''Parses text for HTTP Refresh URL.

    Returns:
        str, None
    '''
    match = re.search(r'url\s*=(.+)', text, re.IGNORECASE)

    if match:
        url = match.group(1)

        if url.startswith('"'):
            url = url.strip('"')
        elif url.startswith("'"):
            url = url.strip("'")

        return clean_link_soup(url)


def clean_link_soup(link):
    '''Strip whitespace from a link in HTML soup.

    Args:
        link (str): A string containing the link with lots of whitespace.

    The link is split into lines. For each line, leading and trailing
    whitespace is removed and tabs are removed throughout. The lines are
    concatenated and returned.

    For example, passing the ``href`` value of::

        <a href=" http://example.com/

                blog/entry/

            how smaug stole all the bitcoins.html
        ">

    will return
    ``http://example.com/blog/entry/how smaug stole all the bitcoins.html``.

    Returns:
        str: The cleaned link.
    '''
    return ''.join(
        [line.strip().replace('\t', '') for line in link.splitlines()]
    )


def urljoin_safe(base_url, url, allow_fragments=True):
    '''urljoin with warning log on error.

    Returns:
        str, None'''
    try:
        return wpull.url.urljoin(
            base_url, url, allow_fragments=allow_fragments
        )
    except ValueError as error:
        _logger.warning(
            _('Discarding malformed URL ‘{url}’: {error}.')\
            .format(url=url, error=error)
        )


def is_likely_inline(link):
    '''Return whether the link is likely to be inline.'''
    file_type = mimetypes.guess_type(link, strict=False)[0]

    if file_type:
        prefix_type = file_type.split('/', 1)[0]

        return prefix_type in ('image', 'video', 'audio')
