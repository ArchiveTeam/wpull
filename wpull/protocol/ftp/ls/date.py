'''Date and time parsing'''
import datetime
import json
import os.path
import re
import sys
import unicodedata
import pprint


AM_STRINGS = {'a. m', 'am', 'पूर्व', 'vorm', 'ص', '上午', '午前'}
'''Set of AM day period strings.'''
PM_STRINGS = {'nachm', 'अपर', 'م', 'p. m', '下午', 'pm', '午後'}
'''Set of PM day period strings.'''

MONTH_MAP = {
    '10月': 10,
    '11月': 11,
    '12月': 12,
    '1月': 1,
    '2月': 2,
    '3月': 3,
    '4月': 4,
    '5月': 5,
    '6月': 6,
    '7月': 7,
    '8月': 8,
    '9月': 9,
    'abr': 4,
    'ago': 8,
    'août': 8,
    'apr': 4,
    'aug': 8,
    'avr': 4,
    'cze': 6,
    'dec': 12,
    'dez': 12,
    'déc': 12,
    'dic': 12,
    'ene': 1,
    'feb': 2,
    'fev': 2,
    'févr': 2,
    'gru': 12,
    'jan': 1,
    'janv': 1,
    'juil': 7,
    'juin': 6,
    'jul': 7,
    'juli': 7,
    'jun': 6,
    'juni': 6,
    'kwi': 4,
    'lip': 7,
    'lis': 11,
    'lut': 2,
    'mai': 5,
    'maj': 5,
    'mar': 3,
    'mars': 3,
    'may': 5,
    'märz': 3,
    'nov': 11,
    'oct': 10,
    'okt': 10,
    'out': 10,
    'paź': 10,
    'sep': 9,
    'sept': 9,
    'set': 9,
    'sie': 8,
    'sty': 1,
    'wrz': 9,
    'авг': 8,
    'апр': 4,
    'дек': 12,
    'июля': 7,
    'июня': 6,
    'марта': 3,
    'мая': 5,
    'нояб': 11,
    'окт': 10,
    'сент': 9,
    'февр': 2,
    'янв': 1,
    'أبريل': 4,
    'أغسطس': 8,
    'أكتوبر': 10,
    'ديسمبر': 12,
    'سبتمبر': 9,
    'فبراير': 2,
    'مارس': 3,
    'مايو': 5,
    'نوفمبر': 11,
    'يناير': 1,
    'يوليو': 7,
    'يونيو': 6,
    'अक्टू': 10,
    'अग': 8,
    'अप्रै': 4,
    'जन': 1,
    'जुला': 7,
    'जून': 6,
    'दिसं': 12,
    'नवं': 11,
    'फ़र': 2,
    'मई': 5,
    'मार्च': 3,
    'सितं': 9
}
'''Month names to int.'''


DAY_PERIOD_PATTERN = re.compile(
    r'({})\b'.format('|'.join(AM_STRINGS | PM_STRINGS)), re.IGNORECASE)
'''Regex pattern for AM/PM string.'''

ISO_8601_DATE_PATTERN = re.compile(r'(\d{4})(?!\d)[\w./-](\d{1,2})(?!\d)[\w./-](\d{1,2})')
'''Regex pattern for dates similar to YYYY-MM-DD.'''

MMM_DD_YY_PATTERN = re.compile(r'([^\W\d_]{3,4})\s{0,4}(\d{1,2})\s{0,4}(\d{0,4})')
'''Regex pattern for dates similar to MMM DD YY.

Example: Feb 09 90
'''

NN_NN_NNNN_PATTERN = re.compile(r'(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})')
'''Regex pattern for dates similar to NN NN YYYY.

Example: 2/9/90
'''

TIME_PATTERN = re.compile(
    r'(\d{1,2}):(\d{2}):?(\d{0,2})\s?(' +
    '|'.join(AM_STRINGS | PM_STRINGS) + '|\b)?')
'''Regex pattern for time in HH:MM[:SS]'''


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
        line = unicodedata.normalize('NFKD', line).lower()

        if DAY_PERIOD_PATTERN.search(line):
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
        day_period = True if time_12_score > time_24_score else False
    else:
        day_period = None

    return (date_format, day_period)


def parse_datetime(text, date_format=None, is_day_period=None,
                   datetime_now=None):
    '''Parse datetime string into datetime object.'''
    datetime_now = datetime_now or \
        datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)
    year = datetime_now.year
    month = datetime_now.month
    day = datetime_now.day
    hour = 0
    minute = 0
    second = 0
    date_ok = False
    start_index = float('+inf')
    end_index = float('-inf')
    ambiguous_year = False

    text = unicodedata.normalize('NFKD', text).lower()

    # Let's do time first
    match = TIME_PATTERN.search(text)

    if match:
        hour_str = match.group(1)
        hour = int(hour_str)
        minute = int(match.group(2))
        day_period = match.group(4)

        if match.group(3):
            second = int(match.group(3))

        if day_period and is_day_period and hour < 13:
            if day_period.lower() in PM_STRINGS:
                if hour != 12:
                    hour += 12
            elif hour == 12:
                hour = 0

        start_index = match.start()
        end_index = match.end()

    # Now try dates
    if date_format == 'ymd' or not date_format:
        match = ISO_8601_DATE_PATTERN.search(text)
        if match:
            date_ok = True
            year = int(match.group(1))
            month = int(match.group(2))
            day = int(match.group(3))

            start_index = min(start_index, match.start())
            end_index = max(end_index, match.end())

    if not date_ok and (date_format == 'mdy' or not date_format):
        match = MMM_DD_YY_PATTERN.search(text)
        if match:
            date_ok = True
            month_str = match.group(1)
            month = parse_month(month_str)
            day = int(match.group(2))
            year_str = match.group(3)

            if year_str and len(year_str) == 4:
                year = int(year_str)
            else:
                ambiguous_year = True

            start_index = min(start_index, match.start())
            end_index = max(end_index, match.end())

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

            start_index = min(start_index, match.start())
            end_index = max(end_index, match.end())

    if date_ok:
        guess_date = datetime.datetime(year, month, day, hour, minute, second,
                                       tzinfo=datetime.timezone.utc)

        if ambiguous_year and guess_date > datetime_now:
            # Sometimes year is not shown within 6 months
            # Year is shown for dates in the future
            guess_date = guess_date.replace(year=year - 1)

        return guess_date, start_index, end_index

    else:
        raise ValueError('Failed to parse date from {}'.format(repr(text)))


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

    raise ValueError('Month {} not found.'.format(repr(text)))


def y2k(year):
    '''Convert two digit year to four digit year.'''
    assert 0 <= year <= 99, 'Not a two digit year {}'.format(year)
    return year + 1000 if year >= 69 else year + 2000


DEFAULT_LANGUAGE_CODES = (
    'zh', 'es', 'en', 'hi', 'ar',
    'pt', 'ru', 'ja',
    'de', 'fr', 'pl',
    )


def parse_cldr_json(directory, language_codes=DEFAULT_LANGUAGE_CODES,
                    massage=True):
    '''Parse CLDR JSON datasets to for date time things.'''

    am_strings = set()
    pm_strings = set()
    month_to_int = {}

    for lang in language_codes:
        path = os.path.join(directory, 'main', lang, 'ca-gregorian.json')

        with open(path) as in_file:
            doc = json.load(in_file)

        months_dict = doc['main'][lang]['dates']['calendars']['gregorian']['months']['format']['abbreviated']
        day_periods_dict = doc['main'][lang]['dates']['calendars']['gregorian']['dayPeriods']['format']['abbreviated']

        for month, month_str in months_dict.items():
            if massage:
                month_str = unicodedata.normalize('NFKD', month_str).lower().strip('.')

            month_to_int[month_str] = int(month)

        am_str = day_periods_dict['am']
        pm_str = day_periods_dict['pm']

        if massage:
            am_str = unicodedata.normalize('NFKD', am_str).lower().strip('.')
            pm_str = unicodedata.normalize('NFKD', pm_str).lower().strip('.')

        am_strings.add(am_str)
        pm_strings.add(pm_str)

    print(pprint.pformat(am_strings))
    print(pprint.pformat(pm_strings))
    print(pprint.pformat(month_to_int))

if __name__ == '__main__':
    parse_cldr_json(sys.argv[1])
