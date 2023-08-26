"""Status check."""
import re
from pathlib import Path
from typing import List

import requests
from bs4 import BeautifulSoup, Tag
from google_play_scraper import app as gplay_app
from google_play_scraper.exceptions import GooglePlayScraperException

from src.downloader.sources import (
    APK_COMBO_GENERIC_URL,
    APK_MIRROR_BASE_URL,
    APK_MIRROR_PACKAGE_URL,
    APK_MONK_APK_URL,
    APK_MONK_ICON_URL,
    PLAY_STORE_APK_URL,
    not_found_icon,
    revanced_api,
)
from src.exceptions import APKComboIconScrapError, APKMirrorIconScrapError, APKMonkIconScrapError, UnknownError
from src.patches import Patches
from src.utils import apkmirror_status_check, bs4_parser, handle_request_response, request_header

no_of_col = 6
combo_headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) Gecko/20100101 Firefox/116.0"}


def apkcombo_scrapper(package_name: str) -> str:
    """Apkcombo scrapper."""
    apkcombo_url = APK_COMBO_GENERIC_URL.format(package_name)
    try:
        r = requests.get(apkcombo_url, headers=combo_headers, allow_redirects=True, timeout=60)
        soup = BeautifulSoup(r.text, bs4_parser)
        avatar = soup.find(class_="avatar")
        if not isinstance(avatar, Tag):
            raise APKComboIconScrapError(url=apkcombo_url)
        icon_element = avatar.find("img")
        if not isinstance(icon_element, Tag):
            raise APKComboIconScrapError(url=apkcombo_url)
        url = icon_element.get("data-src")
        return re.sub(r"=.*$", "", url)  # type: ignore[arg-type]
    except UnknownError as e:
        raise APKComboIconScrapError(url=apkcombo_url) from e


def bigger_image(possible_links: List[str]) -> str:
    """Select image with higher dimension."""
    higher_dimension_url = ""
    max_dimension = 0

    for url in possible_links:
        dimensions = url.split("_")[-1].split(".")[0].split("x")
        width = int(dimensions[0])
        height = int(dimensions[1])

        area = width * height

        if area > max_dimension:
            max_dimension = area
            higher_dimension_url = url

    return higher_dimension_url


def apkmonk_scrapper(package_name: str) -> str:
    """APKMonk scrapper."""
    apkmonk_url = APK_MONK_APK_URL.format(package_name)
    icon_logo = APK_MONK_ICON_URL.format(package_name)
    r = requests.get(apkmonk_url, headers=combo_headers, allow_redirects=True, timeout=60)
    if head := BeautifulSoup(r.text, bs4_parser).head:
        parsed_head = BeautifulSoup(str(head), bs4_parser)
        href_elements = parsed_head.find_all(href=True)
        possible_link = []
        for element in href_elements:
            href_value = element.get("href")
            if href_value.startswith(icon_logo):
                possible_link.append(href_value)
        if possible_link:
            return bigger_image(possible_link)
    raise APKMonkIconScrapError(url=apkmonk_url)


def apkmirror_scrapper(package_name: str) -> str:
    """Apkmirror URL."""
    response = apkmirror_status_check(package_name)
    search_url = APK_MIRROR_PACKAGE_URL.format(package_name)
    if response["data"][0]["exists"]:
        return _extracted_from_apkmirror_scrapper(search_url)
    raise APKMirrorIconScrapError(url=search_url)


def _extracted_from_apkmirror_scrapper(search_url: str) -> str:
    r = requests.get(search_url, headers=request_header, timeout=60)
    soup = BeautifulSoup(r.text, bs4_parser)
    icon_element = soup.select_one("div.bubble-wrap > img")
    if not icon_element:
        raise APKMirrorIconScrapError(url=search_url)
    sub_url = str(icon_element["src"])
    new_width = 500
    new_height = 500
    new_quality = 100

    # regular expression pattern to match w=xx&h=xx&q=xx
    pattern = r"(w=\d+&h=\d+&q=\d+)"

    return APK_MIRROR_BASE_URL + re.sub(pattern, f"w={new_width}&h={new_height}&q={new_quality}", sub_url)


def gplay_icon_scrapper(package_name: str) -> str:
    """Scrap Icon from Gplay."""
    # noinspection PyBroadException
    try:
        return str(
            gplay_app(
                package_name,
            )["icon"]
        )
    except UnknownError as e:
        raise GooglePlayScraperException from e


def icon_scrapper(package_name: str) -> str:
    """Scrap Icon."""
    try:
        return gplay_icon_scrapper(package_name)
    except GooglePlayScraperException:
        try:
            return apkmirror_scrapper(package_name)
        except APKMirrorIconScrapError:
            try:
                return apkcombo_scrapper(package_name)
            except APKComboIconScrapError:
                try:
                    return apkmonk_scrapper(package_name)
                except APKMonkIconScrapError:
                    return not_found_icon
    except UnknownError:
        return not_found_icon


def generate_markdown_table(data: List[List[str]]) -> str:
    """Generate markdown table."""
    if not data:
        return "No data to generate for the table."

    table = (
        "| Package Name | App Icon | PlayStore link | APKMirror link|APKMonk Link| Supported?|\n"
        "|-------------|----------|----------------|---------------|------------------|----------|\n"
    )
    for row in data:
        if len(row) != no_of_col:
            msg = f"Each row must contain {no_of_col} columns of data."
            raise ValueError(msg)

        table += f"| {row[0]} | {row[1]} | {row[2]} | {row[3]} |{row[4]} |{row[5]} |\n"

    return table


def main() -> None:
    """Entrypoint."""
    response = requests.get(revanced_api, timeout=10)
    handle_request_response(response)

    patches = response.json()

    possible_apps = set()
    for patch in patches:
        for compatible_package in patch["compatiblePackages"]:
            possible_apps.add(compatible_package["name"])

    supported_app = set(Patches.support_app().keys())
    missing_support = sorted(possible_apps.difference(supported_app))
    output = "New app found which aren't supported.\n\n"
    data = [
        [
            app,
            f'<img src="{icon_scrapper(app)}" width=50 height=50>',
            f"[PlayStore Link]({PLAY_STORE_APK_URL.format(app)})",
            f"[APKMirror Link]({APK_MIRROR_PACKAGE_URL.format(app)})",
            f"[APKMonk Link]({APK_MONK_APK_URL.format(app)})",
            "<li>- [ ] </li>",
        ]
        for app in missing_support
    ]
    table = generate_markdown_table(data)
    output += table
    with Path("status.md").open("w", encoding="utf_8") as status:
        status.write(output)
    print(output)


if __name__ == "__main__":
    main()
