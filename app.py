import re

import httpx
import jinja2
from bs4 import BeautifulSoup
from cachetools import TTLCache, cached
# fuzzy dt
from dateutil.parser import parse as fuzzy_parse
from flask import Flask, request

cache = TTLCache(maxsize=100, ttl=3600)


@cached(cache)
def get_page_and_title(url):
    """Fetches the page and title from the given URL."""
    response = httpx.get(url, follow_redirects=True)

    if response.status_code == 404:
        # try with _albums_discography instead
        response = httpx.get(
            url.replace("_albums_discography", "_discography"), follow_redirects=True
        )
        print(response.status_code, url.replace("_albums_discography", "_discography"))

    if response.status_code == 404:
        # try with _albums_discography instead
        response = httpx.get(
            url.replace("_albums_discography", ""), follow_redirects=True
        )
        print("Trying without _albums_discography")

    page = BeautifulSoup(response.text, "html.parser")
    page_title = page.title.string if page.title else ""
    return page, page_title


def extract_bullet_with_released(text, text_to_search="Released: "):
    """Extracts the bullet point text and release date from a list item."""
    if text_to_search.lower() in text.lower():
        # remove text between []
        text = re.sub(r"\[.*?\]", "", text)
        # remove text between ()
        text = re.sub(r"\(.*?\)", "", text)
        return fuzzy_parse(text.split(text_to_search)[-1].strip())
    return None


# get table immediate after h3 that contains "albums" text
# get all items in title column
def get_info_from_table(page, header):
    results = []
    if not page:
        return results
    table = page.find("h2", string=lambda text: header.lower() in text.lower())
    if not table:
        # search for h2
        table = page.find("h3", string=lambda text: header.lower() in text.lower())
    if not table:
        print(f"No table found for {header}.")
        return results
    table = table.find_next("table")
    for i, row in enumerate(table.find_all("tr")):
        # skip header row
        if i < 2 or not row.find("th"):
            continue
        # first item
        title = re.sub(r"\[.*?\]", "", row.find("th").get_text(strip=True))
        details = row.find("td")
        # get first item of details list
        if details and details.find("li"):
            details = details.find("li").get_text(strip=True)
        elif details:
            details = details.get_text(strip=True)
        state = None
        released_date = extract_bullet_with_released(details)
        if released_date:
            state = "released"
        else:
            state = "scheduled"
            released_date = extract_bullet_with_released(
                details, text_to_search="Scheduled: "
            )

        results.append((title, state, released_date))

    return results


def generate_template(page_title, results):
    template = """
    <!DOCTYPE html>
    <html lang="en">
    <head>

        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{{ page_title }}</title>
        <link rel="alternate" href="https://granary.io/url?input=mf2-json&output=rss&url=https://music.jamesg.blog/?url={{ url }}" type="application/rss+xml" title="{{ page_title }} RSS Feed">
    </head>
    <body>
    <main class="h-feed">
    <h1 class="p-name">{{ page_title }}</h1>
    <ul>
    {% for title, state, released_date in results %}
        <li class="h-entry p-name">{{ title }} {{ state }} <date class="dt-published">{{ released_date.strftime('%Y-%m-%d') if released_date else 'TBD' }}</date></li>
    {% endfor %}
    </ul>
    </main>
    </body>
    </html>
    """

    template = jinja2.Template(template)
    output = template.render(results=results, page_title=page_title)

    return output


app = Flask(__name__)


@app.route("/")
def index():
    """Main route to display the discography."""
    if not request.args.get("url"):
        return "Please provide a URL parameter, e.g., ?url=The_Beatles."
    url = (
        "https://en.wikipedia.org/api/rest_v1/page/html/"
        + request.args.get("url", "The_Beatles").replace(" ", "_")
        + "_albums_discography"
    )
    page, page_title = get_page_and_title(url)
    results = get_info_from_table(page, "albums") + get_info_from_table(page, "EPs")
    return generate_template(
        page_title, results, request.args.get("url", "The_Beatles").replace(" ", "_")
    )


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
