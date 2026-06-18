"""
Search api used for TMDb
"""
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import List, Optional
    from ...http_client import HTTPClient

import re
from bs4 import BeautifulSoup, Tag
from thefuzz import fuzz

from ...media import Metadata, MetadataType, ExtraMetadata, AiringType

__all__ = ("TheMovieDB",)

class TheMovieDB():
    """Wrapper for themoviedb.org"""
    def __init__(self, http_client: HTTPClient) -> None:
        self.http_client = http_client

        self.base_url = "https://www.themoviedb.org"
        self.not_translated = "translated in English"

    def soup(self, query: str) -> BeautifulSoup:
        return BeautifulSoup(query, "html.parser")

    def search(self, query: str, limit: Optional[int]) -> List[Metadata]:
        limit = 20 if limit is None else limit

        metadata = []
        response = self.http_client.get(f"{self.base_url}/search", params = {"query": query})
        soup = self.soup(response.text)

        movie_items = soup.find("div", {"class": "movie"}).find_all("div", {"class": "card v4 tight"})
        tv_items = soup.find("div", {"class": "tv"}).find_all("div", {"class": "card v4 tight"})

        items: List[Tag] = movie_items + tv_items
        items.sort(key=lambda data: fuzz.ratio(query, data.find("h2").text), reverse=True)

        for item in items:
            release_date = item.find("span", {"class": "release_date"})
            id = item.find("a")["href"].split("/")[-1].split("-")[0]
            image = item.find("img")

            if image is not None:
                image = image["src"].replace("w94_and_h141_bestv2", "w600_and_h900_bestv2")

            metadata.append(Metadata(
                id = id,
                title = item.find("h2").text,
                type = MetadataType.SINGLE if "movie" in item.parent.parent.attrs["class"] else MetadataType.MULTI,
                image_url = image,
                year = release_date.text.split(" ")[-1] if release_date is not None else None,
                extra_func = lambda: self.__scrape_extra_metadata(item)
            ))

        return metadata[:limit]

    def scrape_episodes(self, metadata: Metadata):
        episodes_dict = {}
        url = f"{self.base_url}/tv/{metadata.id}/seasons"

        seasons_page = self.http_client.get(url, redirect=True)
        soup = self.soup(seasons_page)

        seasons = soup.findAll("div", {"class": "season_wrapper"})

        for num in range(len(seasons)):
            season = seasons[num]

            season_num = season.select("a:nth-child(1)")[0]["href"].split("/")[-1]
            episodes_text = season.find("h4").text

            if season_num == "0":
                continue

            episode_pattern = r"(\d+) Episodes"
            
            episodes = re.findall(episode_pattern, episodes_text)[0]

            episodes_dict[int(season_num)] = int(episodes)
        
        return episodes_dict

    def __scrape_extra_metadata(self, item: Tag) -> ExtraMetadata:
        cast = []
        alternate_titles = []
        genres = []
        people = []
        airing = None
        description = None

        description_tag = item.find("div", {"class": "overview"}).find("p")
        id = item.find("a")["href"]
        type = item.parent.parent.attrs["class"]
        url = f"{self.base_url}/{type}/{id}"

        page = self.http_client.get(url, redirect=True)
        cast_page = self.http_client.get(f"{url}/cast", redirect=True)

        soup = self.soup(page)
        soup_c = self.soup(cast_page)

        airing_status = soup.find("section", {"class": "facts left_column"}).find("p").contents[-1].text
        genre: List[Tag] = soup.find("span", {"class":"genres"}).findAll("a")
        people_credits = soup_c.find("ol", {"class":"people credits"})

        if description_tag is not None:
            description = description_tag.text

        if self.not_translated in description:
            description = None

        if "Released" in airing_status:
            airing = AiringType.RELEASED
        elif "Production" in airing_status:
            airing = AiringType.PRODUCTION
        elif "Returning" in airing_status:
            airing = AiringType.ONGOING
        elif "Canceled" in airing_status:
            airing = AiringType.CANCELED
        else:
            airing = AiringType.DONE

        if people_credits is not None:
            people = people_credits.findAll("li")

        for g in genre:
            genres.append(g.text)

        if soup.find_all("p", {"class": "wrap"}):
            alternate_titles.append(soup.find("p", {"class": "wrap"}).contents[-1].text)
        
        for i in people:
            cast.append(i.select("p:nth-child(1) > a:nth-child(1)")[0].text)

        return ExtraMetadata(
            description = description,
            alternate_titles = alternate_titles,
            cast = cast,
            genres = genres,
            airing = airing
        )