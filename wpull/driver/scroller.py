'''PhantomJS page scrolling.'''
import gettext
import logging

import trollius
from trollius import From, Return

from wpull.backport.logging import BraceMessage as __


_logger = logging.getLogger(__name__)
_ = gettext.gettext


PAGE_DOWN = 16777239


class Scroller(object):
    '''PhantomJS infinite page scroller.

    Attributes:
        action_callback: A function that accepts two arguments for actions.
    '''
    def __init__(self, driver, resource_tracker, scroll_height=768, wait_time=1.0, num_scrolls=10, smart_scroll=True):
        self._driver = driver
        self._resource_tracker = resource_tracker
        self._scroll_height = scroll_height
        self._wait_time = wait_time
        self._num_scrolls = num_scrolls
        self._smart_scroll = smart_scroll

        self._current_y = 0

        self.action_callback = None

    @trollius.coroutine
    def scroll_to_bottom(self):
        '''Scroll the page as far as possible.

        Coroutine.
        '''
        total_scroll_count = 0

        for scroll_count in range(self._num_scrolls):
            _logger.debug(__('Scrolling page. Count={0}.', scroll_count))

            pre_scroll_counter_values = self._resource_tracker.to_values()

            self._current_y += self._scroll_height

            self._log_action('set_scroll_left', 0)
            self._log_action('set_scroll_top', self._current_y)

            yield From(self._driver.scroll_to(0, self._current_y))
            yield From(self._driver.send_key(PAGE_DOWN))

            total_scroll_count += 1

            self._log_action('wait', self._wait_time)
            yield From(trollius.sleep(self._wait_time))

            post_scroll_counter_values = self._resource_tracker.to_values()

            _logger.debug(__(
                'Counter values pre={0} post={1}',
                pre_scroll_counter_values,
                post_scroll_counter_values
            ))

            if self._smart_scroll and \
                    pre_scroll_counter_values == post_scroll_counter_values:
                break

        _logger.info(__(
            gettext.ngettext(
                'Scrolled page {num} time.',
                'Scrolled page {num} times.',
                total_scroll_count,
            ),
            num=total_scroll_count
        ))

        raise Return(total_scroll_count)

    @trollius.coroutine
    def scroll_to_top(self):
        '''Scroll to top of page.'''
        self._log_action('set_scroll_left', 0)
        self._log_action('set_scroll_top', 0)

        yield From(self._driver.scroll_to(0, 0))

    def _log_action(self, action_name, action_value):
        '''Call the action callback.'''
        if self.action_callback:
            self.action_callback(action_name, action_value)
