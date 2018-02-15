import os
import pickle
import re
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple, Dict
from urllib.parse import parse_qs, urlencode, urlsplit

from credentials import Credentials

try:
    import lxml

    BS4_PARSER = 'lxml'
except ImportError:
    BS4_PARSER = 'html.parser'
import requests
from bs4 import BeautifulSoup

ROOT_PATH = Path(__file__).resolve().parent

DOWNLOADS_PATH = ROOT_PATH / 'downloads'

if not DOWNLOADS_PATH.exists() and not DOWNLOADS_PATH.is_dir():
    os.mkdir(DOWNLOADS_PATH)

SESSION_FILE_PATH: Path = ROOT_PATH / 'session.bak'

CHUNK_SIZE = 1024

USER_AGENT = 'wallhavener .1'


class WallhavenerError(Exception):
    pass


class NoMorePagesError(WallhavenerError):
    pass


class WallhavenSearchRequester:
    LOGIN_URL = 'https://alpha.wallhaven.cc/auth/login'

    def __init__(self, creds: Optional[Credentials] = None) -> None:
        self.creds = creds
        self._session = None

    @property
    def session(self) -> requests.Session:
        if self._session is None:
            if SESSION_FILE_PATH.exists():
                with SESSION_FILE_PATH.open('rb') as f:
                    self._session = pickle.load(f)
            else:
                self._session = requests.Session()

        return self._session

    def do_auth(self):
        if not SESSION_FILE_PATH.is_file():
            username, password = self.creds.creds
            creds = {'username': username, 'password': password}

            response = self.session.get(self.LOGIN_URL)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, BS4_PARSER)
            token = soup.select('input[name="_token"]')[0]['value']
            creds['_token'] = token

            response = self.session.post(self.LOGIN_URL, data=creds)
            response.raise_for_status()

            if 'Your username/password combination was incorrect' in response.text:
                raise WallhavenerError('Incorrect username/password.')

            SESSION_FILE_PATH.touch()
            with SESSION_FILE_PATH.open('wb') as f:
                pickle.dump(self.session, f)

    def get(self, url, **requests_kwargs):
        # if we have credentials, we log in
        if self.creds:
            self.do_auth()

        headers: Dict[str, str] = requests_kwargs.get('headers', {})

        # Handle the fact that HTTP header names are case insensitive
        user_agent_header = None
        for header in headers:
            if header.casefold() == 'user-agent':
                user_agent_header = header
        if user_agent_header is not None:
            del headers[user_agent_header]

        headers['User-Agent'] = USER_AGENT
        requests_kwargs['headers'] = headers

        return self.session.get(url, **requests_kwargs)


def get_int_tup_as_str(rez_tuple: Tuple[int, int]) -> str:
    return f'{rez_tuple[0]}x{rez_tuple[1]}'


class Filter:
    _general: bool = True
    _anime: bool = False
    _people: bool = False
    _sfw: bool = True
    _sketchy: bool = True
    _nsfw: bool = True

    _resolutions: List[Tuple[int, int]] = []
    _resolution_filter: str = 'at_least'

    _ratios: List[Tuple[int, int]] = []
    _sort_by: str = 'toplist'
    _order: str = 'desc'
    _range: str = '1M'

    page = 1

    query = ''

    CATEGORY = ['general', 'anime', 'people']
    PURITY = ['sfw', 'sketchy', 'nsfw']
    RESOLUTIONS = [
        (1280, 720), (1280, 800), (1280, 960), (1280, 1024),
        (1600, 900), (1600, 1000), (1600, 1200), (1600, 1280),
        (1920, 1080), (1920, 1200), (1920, 1440), (1920, 1536),
        (2560, 1440), (2560, 1600), (2560, 1920), (2560, 2048),
        (3840, 2160), (3840, 2400), (3840, 2880), (3840, 3072)
    ]
    RATIOS = [(4, 3), (5, 4), (16, 9), (16, 10), (21, 9), (32, 9), (48, 9), (9, 16), (10, 16)]
    RESOLUTION_FILTERS = ['at_least', 'exactly']
    SORT_BYS = ['relevance', 'random', 'date_added', 'views', 'favorites', 'toplist']
    ORDERS = ['desc', 'asc']
    RANGES = ['1d', '3d', '1M', '1w', '3M', '6M', '1y']

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        return f'Filter(categories={self.categories}, purity={self.purity}, ' \
               f'resolutions={self.resolutions}, ' \
               f'resolution_filter={self.resolution_filter}, ' \
               f'ratios={self.ratios}, ' \
               f'sort_by={self.sort_by}, ' \
               f'order={self.order}, ' \
               f'range={self.range}, ' \
               f'query={self.query or None}' \
               f')'

    @classmethod
    def from_url(cls, url: str) -> 'Filter':
        f = Filter()

        parsed = parse_qs(urlsplit(url).query)

        category_default = bools_to_string([Filter._general, Filter._anime, Filter._people])

        category = parsed.get('categories', [category_default])[0]

        f.general = category[0]
        f.anime = category[1]
        f.people = category[2]

        purity_default = bools_to_string([Filter._sfw, Filter._sketchy, Filter._nsfw])

        purity = parsed.get('purity', [purity_default])[0]

        f = Filter()

        f.sfw = purity[0]
        f.sketchy = purity[1]
        f.nsfw = purity[2]

        resolutions = parsed.get('resolutions', None)
        if resolutions is not None:
            for rez in resolutions:
                f.add_resolution(rez.split('x'))

        ratios = parsed.get('ratios', None)
        if ratios is not None:
            for ratio in ratios:
                f.add_ratio(ratio.split('x'))

        if 'sorting' in parsed and parsed['sorting']:
            f.sort_by = parsed['sorting'][0]

        if 'order' in parsed and parsed['order']:
            f.order = parsed['order'][0]

        if 'topRange' in parsed and parsed['topRange']:
            f.range = parsed['topRange'][0]

        if 'q' in parsed and parsed['q']:
            f.query = parsed['q'][0]

        return f

    @property
    def credentials_required(self) -> bool:
        # credentials only required for nsfw filters...i think
        return self.nsfw

    @property
    def query_string(self) -> str:
        return urlencode(self.as_dict)

    @property
    def as_dict(self):
        d = {
            'q': self.query,
            'categories': self.categories,
            'purity': self.purity,
            'topRange': self.range,
            'sorting': self.sort_by,
            'order': self.order,
            'page': self.page,
            'ratios': self.ratios
        }
        if self.resolution_filter == 'at_least' and self.resolutions:
            # use the smallest resolution in our list
            d['atleast'] = get_int_tup_as_str(self.resolutions[0])

        else:
            d['resolutions'] = self.x_resolutions

        # remove False-y items
        d = {k: v for k, v in d.items() if v}

        return d

    @property
    def categories(self):
        return bools_to_string((self.general, self.anime, self.people))

    @property
    def purity(self):
        return bools_to_string((self.sfw, self.sketchy, self.nsfw))

    @property
    def resolutions(self) -> List[Tuple[int, int]]:
        return self._resolutions

    @resolutions.setter
    def resolutions(self, value: List[Tuple[int, int]]):
        misses = []
        for rez in value:
            if rez not in self.RESOLUTIONS:
                misses.append(rez)
        if misses:
            raise TypeError(f'{misses} not in valid resolutions: {self.RESOLUTIONS}')
        self._resolutions = value

    def add_resolution(self, value: Tuple[int, int]) -> None:
        if value not in self.RESOLUTIONS:
            raise TypeError(f'{value} not in valid resolutions: {self.RESOLUTIONS}')
        self._resolutions.append(value)
        self._resolutions.sort()

    @property
    def x_resolutions(self) -> str:
        return ','.join([get_int_tup_as_str(x) for x in self.resolutions])

    @property
    def x_ratios(self) -> str:
        return ','.join([get_int_tup_as_str(x) for x in self.ratios])

    @property
    def range(self) -> str:
        return self._range

    @range.setter
    def range(self, value: str):
        if value not in self.RANGES:
            raise TypeError(f'Only valid values for range are {self.RANGES}, not {value}.')
        self._range = value

    @property
    def resolution_filter(self) -> str:
        return self._resolution_filter

    @resolution_filter.setter
    def resolution_filter(self, value: str) -> None:
        if value not in self.RESOLUTION_FILTERS:
            raise TypeError(f'Only valid values for resolution_filter '
                            f'are {self.RESOLUTION_FILTERS}')
        self._resolution_filter = value

    @property
    def ratios(self) -> List[Tuple[int, int]]:
        return self._ratios

    def add_ratio(self, ratio: Tuple[int, int]) -> None:
        if ratio not in self.RATIOS:
            raise TypeError(f'Only valid values for ratio are {self.RATIOS}.')

        if ratio not in self._ratios:
            self._ratios.append(ratio)
            self._ratios.sort()

    @property
    def sort_by(self) -> str:
        return self._sort_by

    @sort_by.setter
    def sort_by(self, value: str) -> None:
        if value not in self.SORT_BYS:
            raise TypeError(f'Only valid values for sort_by are {self.SORT_BYS}')
        self._sort_by = value

    @property
    def order(self) -> str:
        return self._order

    @order.setter
    def order(self, value: str):
        if value not in self.ORDERS:
            raise TypeError(f'Only valid values for order are {self.ORDERS}')
        self._order = value

    @property
    def any_category_set(self) -> bool:
        return any([self._general, self._anime, self._people])

    @property
    def any_purity_set(self) -> bool:
        return any([self._sfw, self._sketchy, self._nsfw])

    def __getattr__(self, item):
        if item in self.CATEGORY:
            # if no category is set, all categories are set
            return getattr(self, f'_{item}') if self.any_category_set else True

        if item in self.PURITY:
            if not self.any_purity_set:
                # if no purity is set, only sfw is set
                if item == 'sfw':
                    return True
                else:
                    return False
            else:
                return getattr(self, f'_{item}')

        return getattr(self, item)

    def __setattr__(self, key, value):
        if key in self.CATEGORY + self.PURITY:
            super().__setattr__(f'_{key}', value)
        else:
            super().__setattr__(key, value)


class WallhavenResults:
    SEARCH_URL = 'https://alpha.wallhaven.cc/search'

    def __init__(self, page_num: int, fltr: Filter, requester: WallhavenSearchRequester) -> None:
        self.requested_page_num = page_num
        self.filter = fltr
        self.filter.page = page_num
        self.requester = requester

        self._contents: Optional[str] = None
        self._soup: Optional[BeautifulSoup] = None

    @property
    def is_authed(self):
        return bool(self.soup.select('input#search-nsfw')) \
               and not bool(self.soup.select('a.button.register'))

    @property
    def soup_current_page(self):
        return int(self.soup.select('li.current')[0].text)

    @property
    def soup_total_pages_count(self) -> int:
        page_count_header = self.soup.select('header.thumb-listing-page-header')
        if len(page_count_header) != 1:
            return 1
        text = page_count_header[0].text
        match = re.match(r'.*/ (\d+)', text)
        if not match:
            raise WallhavenerError('Cannot find page count in soup.')
        return int(match.groups()[0])

    @property
    def url(self):
        return f'{self.SEARCH_URL}?{self.filter.query_string}'

    @property
    def contents(self) -> str:
        if self._contents is None:
            self._contents = self._get()
        return self._contents

    def _get(self):
        response = self.requester.get(self.url)
        response.raise_for_status()
        with open('results.html', 'w') as f:
            f.write(response.text)

        return response.text

    @property
    def next_page_url(self):
        next_page_a_tags = self.soup.select('a[rel="next"]')
        if len(next_page_a_tags) == 0:
            raise NoMorePagesError("No more pages.")

        if not all([a['href'] == next_page_a_tags[0]['href'] for a in next_page_a_tags]):
            raise WallhavenerError("Not all 'next' page links on page point to same url.")

        return next_page_a_tags[0]['href']

    @property
    def next_page_number(self):
        parsed = parse_qs(urlsplit(self.next_page_url).query)
        next_page_number = int(parsed['page'][0])

        # if not next_page_number == self.page_num + 1:
        #     raise WallhavenerError(f'Invalid state.  Expected next page to be {self.page_num + 1}.'
        #                            f' Got page number of {next_page_number}.')

        return next_page_number

    def get_next_page_of_results(self) -> 'WallhavenResults':
        return WallhavenResults(self.next_page_number, self.filter, self.requester)

    @property
    def soup(self):
        if self._soup is None:
            self._soup = BeautifulSoup(self.contents, BS4_PARSER)
        return self._soup

    def __iter__(self):
        for li_tag in self.soup.select('section.thumb-listing-page > ul > li'):
            yield Preview(li_tag)


class Wallhaven:
    def __init__(self, fltr: Filter):
        self._credentials = Credentials()
        self.filter = fltr
        self.current_page: Optional[WallhavenResults] = None
        self.pages = {}

        self._requester = None

        self._total_pages = None

    @property
    def requester(self) -> WallhavenSearchRequester:
        if self._requester is None:
            self._requester = WallhavenSearchRequester(self._credentials if
                                                       self.filter.credentials_required else None)
        return self._requester

    def __iter__(self) -> Iterable['Preview']:
        if self.current_page is None:
            self.current_page = WallhavenResults(1, self.filter, self.requester)

        while self.current_page.soup_current_page <= self.current_page.soup_total_pages_count:
            if self.current_page.soup_current_page == 9:
                print('what')
            print(f'Yielding images from page {self.current_page.soup_current_page}/'
                  f'{self.current_page.soup_total_pages_count}')
            for wallpaper_preview in self.current_page:
                yield wallpaper_preview

            if self.current_page.soup_current_page == self.current_page.soup_total_pages_count:
                return

            self.current_page = WallhavenResults(self.current_page.soup_current_page + 1,
                                                 self.filter, self.requester)


def bools_to_string(bools: Sequence[bool]) -> str:
    return ''.join(['1' if b else '0' for b in bools])


class Preview:
    IMAGE_EXT = ['.jpg', '.png', '.bmp', '.gif']

    def __init__(self, li_tag: BeautifulSoup) -> None:
        self.li_tag = li_tag

        self.extension = None

    @property
    def id(self) -> str:
        return self.li_tag.figure['data-wallpaper-id']

    @property
    def url_without_ext(self) -> str:
        return f'https://wallpapers.wallhaven.cc/wallpapers/full/wallhaven-{self.id}'

    def get_file_path(self, extension: str = None) -> Path:
        if self.extension is None:
            raise ValueError("Cannot get a file path until we know the extension.")
        return DOWNLOADS_PATH / f'wallhaven-{self.id}{extension}'

    def download(self):
        for ext in self.IMAGE_EXT:
            url = f'{self.url_without_ext}{ext}'

            response = requests.get(url)
            if not response.ok:
                continue
            self.extension = ext

            file_path = self.get_file_path(ext)

            with file_path.open('wb') as fd:
                for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                    fd.write(chunk)
            return file_path

        raise WallhavenerError(f"Cannot find image url for {self.url_without_ext}")
