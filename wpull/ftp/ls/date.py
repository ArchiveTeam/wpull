'''Date and time parsing'''
import re
import unicodedata
import datetime

PM_STR = ('pm', '오후', '下午', '午後')
'''P.M. Strings.'''

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


def parse_datetime(text):
    '''Parse datetime string into datetime object.'''
    text = unicodedata.normalize('NFKD', text)
    datetime_now = datetime.datetime.utcnow()
    year = datetime_now.year
    month = datetime_now.month
    day = datetime_now.day
    hour = 0
    minute = 0
    second = 0
    time_score = 0
    date_score = 0

    # Let's do time first
    match = re.search(r'(\d{1,2}):(\d{2}):?(\d{0,2}) ?(\w{0,2})', text)

    if match:
        time_score += 1
        hour_str = match.group(1)
        hour = int(hour_str)
        minute = int(match.group(2))

        if match.group(3):
            second = int(match.group(3))

        hour_period = match.group(4)

        if hour_period and \
                not (len(hour_str) == 2 and hour_str.startswith('0')) and \
                hour <= 12:
            # If the hour does not look like 24 hour time, skip
            # Otherwise, we need to check if AM/PM
            if hour_period in PM_STR:
                hour += 12
                if hour > 24:
                    hour = 0
                    day += 1

    # Now try dates
    # Try something like ISO 8601.
    match = re.match(r'(\d{4}).(\d{1,2}).(\d{1,2})', text)

    if match:
        date_score += 1
        year = int(match.group(1))
        month = int(match.group(2))
        day = int(match.group(3))

    if not date_score:
        # Try MMM DD YY
        match = re.match(r'(\w{3,4})\s+(\d{1,2})\s+(\d{0,4})', text)

        if match:
            date_score += 1
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

    # Try DD MM YYYY
    if not date_score:
        match = re.match(r'(\d{1,2}).(\d{1,2}).(\d{4})', text)
        if match:
            date_score += 1
            day = int(match.group(1))
            month = int(match.group(2))
            year = int(match.group(3))

    # TODO: try MM DD YY

    if date_score or time_score:
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
