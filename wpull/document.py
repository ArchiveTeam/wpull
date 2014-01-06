# encoding=utf-8
import abc
import collections
import itertools
import lxml.html
import re
import urllib.parse

import wpull.util


class BaseDocumentScraper(object, metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def scrape(self, request, response):
        pass

ScrapedLink = collections.namedtuple(
    'ScrapedLink', ['tag', 'attrib', 'link', 'inline', 'linked', 'base_link'])


class HTMLScraper(BaseDocumentScraper):
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
        with wpull.util.reset_file_offset(content_file):
            root = lxml.html.parse(content_file, base_url=request.url_info.url
                ).getroot()

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
                base_url = urllib.parse.urljoin(base_url,
                    scraped_link.base_link)

            url = urllib.parse.urljoin(base_url, scraped_link.link,
                allow_fragments=False)

            if scraped_link.inline:
                inline_urls.add(url)
            if scraped_link.linked:
                linked_urls.add(url)

        if self._robots and self._robots_cannot_follow(root):
            linked_urls.clear()

        return inline_urls, linked_urls

    def _scrape_tree(self, root):
        for element in root.iter():
            for scraped_link in self._scrape_element(element):
                yield scraped_link

    def _scrape_element(self, element):
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
                yield ScrapedLink(element.tag, 'style', link, True, False,
                    None)

    def _scrape_link_element(self, element):
        rel = element.get('rel', '')
        inline = 'stylesheet' in rel or 'icon' in rel

        for attrib_name, link in self._scrape_links_by_attrib(element):
            yield ScrapedLink(element.tag, attrib_name, link, inline,
                not inline, None)

    def _scrape_meta_element(self, element):
        if element.get('http-equiv', '').lower() == 'refresh':
            content_value = element.get('content')
            match = re.search(r'url=(.+)', content_value, re.IGNORECASE)
            if match:
                yield ScrapedLink(
                    element.tag, 'http-equiv', match.group(1), False, True,
                    None)

    def _scrape_object_element(self, element):
        base_link = element.get('codebase', None)

        if base_link:
            # lxml returns codebase as inline
            yield ScrapedLink(element.tag, 'codebase', base_link, True, False,
                None)

        for attribute in ('code', 'src', 'classid', 'data'):
            if attribute in element.attrib:
                yield ScrapedLink(element.tag, attribute,
                    element.get(attribute), True, False, base_link)

        if 'archive' in element.attrib:
            for match in re.finditer(r'[^ ]+', element.get('archive')):
                value = match.group(0)
                yield ScrapedLink(element.tag, 'archive', value, True, False,
                   base_link)

    def _scrape_param_element(self, element):
        valuetype = element.get('valuetype', '')

        if valuetype.lower() == 'ref' and 'value' in element.attrib:
            yield ScrapedLink(
                element.tag, 'value', element.get('value'), True, False, None)

    def _scrape_style_element(self, element):
        if element.text:
            link_iter = itertools.chain(
                CSSScraper.scrape_imports(element.text),
                CSSScraper.scrape_urls(element.text)
            )
            for link in link_iter:
                yield ScrapedLink(element.tag, None, link, True, False, None)

    def _scrape_plain_element(self, element):
        for attrib_name, link in self._scrape_links_by_attrib(element):
            inline = self._is_link_inline(element.tag, attrib_name)
            linked = self._is_html_link(element.tag, attrib_name)
            yield ScrapedLink(element.tag, attrib_name, link, inline, linked,
                None)

    def _scrape_links_by_attrib(self, element):
        for attrib_name in self.LINK_ATTRIBUTES:
            if attrib_name in element.attrib:
                yield attrib_name, element.get(attrib_name)

    def _is_link_inline(self, tag, attribute):
        if tag in self.TAG_ATTRIBUTES \
        and attribute in self.TAG_ATTRIBUTES[tag]:
            attr_flags = self.TAG_ATTRIBUTES[tag][attribute]
            return attr_flags & self.ATTR_INLINE

        return attribute != 'href'

    def _is_html_link(self, tag, attribute):
        if tag in self.TAG_ATTRIBUTES \
        and attribute in self.TAG_ATTRIBUTES[tag]:
            attr_flags = self.TAG_ATTRIBUTES[tag][attribute]
            return attr_flags & self.ATTR_HTML

        return attribute == 'href'

    def _is_accepted(self, element_tag):
        element_tag = element_tag.lower()

        if self._ignored_tags is not None \
        and element_tag in self._ignored_tags:
            return False

        if self._followed_tags is not None:
            return element_tag in self._followed_tags
        else:
            return True

    def _robots_cannot_follow(self, root):
        for element in root.iter('meta'):
            if element.get('name', '').lower() == 'robots':
                if 'nofollow' in element.get('value', '').lower():
                    return True


class CSSScraper(BaseDocumentScraper):
    def scrape(self, request, response):
        if not self.is_css(request, response):
            return

        base_url = request.url_info.url
        inline_urls = set()
        text = response.body.content.decode()
        iterable = itertools.chain(self.scrape_urls(text),
            self.scrape_imports(text))

        for link in iterable:
            inline_urls.add(urllib.parse.urljoin(base_url, link,
                allow_fragments=False))

        return inline_urls, ()

    @classmethod
    def is_css(cls, request, response):
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
        for match in re.finditer(r'''url\(\s*['"]?(.*?)['"]?\s*\)''', text):
            yield match.group(1)

    @classmethod
    def scrape_imports(cls, text):
        for match in re.finditer(r'''@import\s*([^\s]+).*?;''', text):
            url_str_fragment = match.group(1)
            if url_str_fragment.startswith('url('):
                for url in cls.scrape_urls(url_str_fragment):
                    yield url
            else:
                yield url_str_fragment.strip('"\'')
