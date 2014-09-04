'''Date and time parsing'''
import re
import datetime

HOUR_PERIOD_PATTERN = re.compile(
    r'(am|pm|ap|de|fh|fm|em|ip|ke|дп|пп|上午|下午|午前|午後)\b', re.IGNORECASE)
'''Regex pattern for AM/PM string.'''

ISO_8601_DATE_PATTERN = re.compile(r'(\d{4})[\w./-](\d{1,2})[\w./-](\d{1,2})')
'''Regex pattern for dates similar to YYYY-MM-DD.'''

MMM_DD_YY_PATTERN = re.compile(r'([^\W\d_]{3,4})\s{0,4}(\d{1,2})\s{0,4}(\d{0,4})')
'''Regex pattern for dates similar to MMM DD YY.

Example: Feb 09 90
'''

NN_NN_NNNN_PATTERN = re.compile(r'(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})')
'''Regex pattern for dates similar to NN NN YYYY.

Example: 2/9/90
'''

TIME_PATTERN = re.compile(r'(\d{1,2}):(\d{2}):?(\d{0,2})')
'''Regex pattern for time in HH:MM[:SS]'''

MONTH_MAP = {
    'jan': 1,
    'feb': 2,
    'mar': 3,
    'apr': 4,
    'may': 5,
    'june': 6,
    'july': 7,
    'aug': 8,
    'sep': 9,
    'oct': 10,
    'nov': 11,
    'dec': 12,
}  # TODO: obviously add more from CLDR
'''Month names to int.'''


def guess_datetime_format(lines, threshold=5):
    '''Guess whether order of the year, month, day and 12/24 hour.

    Returns:
        tuple: First item is either str ``ymd``, ``dmy``, ``mdy``
        or ``None``.
        Second item is either True for 12-hour time or False for 24-hour time
        or None.
    '''
    time_12_score = 0
    time_24_score = 0
    date_ymd_score = 0
    date_dmy_score = 0
    date_mdy_score = 0

    for line in lines:
        if HOUR_PERIOD_PATTERN.search(line):
            time_12_score += 1
        else:
            time_24_score += 1

        if ISO_8601_DATE_PATTERN.search(line):
            date_ymd_score += 1
        elif MMM_DD_YY_PATTERN.search(line):
            date_mdy_score += 1
        else:
            match = NN_NN_NNNN_PATTERN.search(line)

            if match:
                num_1 = int(match.group(1))
                num_2 = int(match.group(2))

                if num_1 > 12:
                    date_dmy_score += 1
                elif num_2 > 12:
                    date_mdy_score += 1

        time_score = time_12_score + time_24_score
        date_score = date_ymd_score + date_dmy_score + date_mdy_score
        if time_score >= threshold and date_score >= threshold:
            break

    if date_ymd_score or date_dmy_score or date_mdy_score:
        top = max([
            (date_ymd_score, 'ymd'),
            (date_dmy_score, 'dmy'),
            (date_mdy_score, 'mdy'),
            ],
            key=lambda item: item[0]
        )
        date_format = top[1]
    else:
        date_format = None

    if time_12_score or time_24_score:
        hour_period = True if time_12_score > time_24_score else False
    else:
        hour_period = None

    return (date_format, hour_period)


def parse_datetime(text, date_format=None, hour_period=None):
    '''Parse datetime string into datetime object.'''
    datetime_now = datetime.datetime.utcnow()
    year = datetime_now.year
    month = datetime_now.month
    day = datetime_now.day
    hour = 0
    minute = 0
    second = 0
    date_ok = False

    # Let's do time first
    match = TIME_PATTERN.search(text)

    if match:
        hour_str = match.group(1)
        hour = int(hour_str)
        minute = int(match.group(2))

        if match.group(3):
            second = int(match.group(3))

        if hour_period and hour < 12:
            # FIXME: this isn't quite right, still need to check the actual
            # string
            hour += 12

    # Now try dates
    if date_format == 'ymd' or not date_format:
        match = ISO_8601_DATE_PATTERN.search(text)
        if match:
            date_ok = True
            year = int(match.group(1))
            month = int(match.group(2))
            day = int(match.group(3))

    if not date_ok and (date_format == 'myd' or not date_format):
        match = MMM_DD_YY_PATTERN.search(text)
        if match:
            date_ok = True
            month_str = match.group(1)
            month = parse_month(month_str)
            day = int(match.group(2))
            year_str = match.group(3)
            if year_str:
                if len(year_str) == 4:
                    year = int(year_str)

            if year == datetime_now.year and month > datetime_now.month:
                # Sometimes year is not shown within 6 months
                year -= 1

    if not date_ok:
        match = NN_NN_NNNN_PATTERN.search(text)
        if match:
            date_ok = True
            num_1 = int(match.group(1))
            num_2 = int(match.group(2))
            year = int(match.group(3))

            if year < 100:
                year = y2k(year)

            if date_format == 'mdy' or num_2 > 12:
                month = num_1
                day = num_2
            else:
                day = num_1
                month = num_2

    if date_ok:
        return datetime.datetime(year, month, day, hour, minute, second,
                                 tzinfo=datetime.timezone.utc)
    else:
        raise ValueError('Failed to parse date')


def parse_month(text):
    '''Parse month string into int.'''
    text = text.lower()
    try:
        return MONTH_MAP[text]
    except KeyError:
        pass

    try:
        return MONTH_MAP[text[:3]]
    except KeyError:
        pass

    raise ValueError('Month not found.')


def y2k(year):
    '''Convert two digit year to four digit year.'''
    assert 0 <= year <= 99, 'Not a two digit year {}'.format(year)
    return year + 1000 if year >= 69 else year + 2000
