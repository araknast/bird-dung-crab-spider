# Bird-dung Crab Spider
This is a spider that crawls the web. The source code for the spider itself is
located in spid/spiders/mainspider.py, the rest is ssdb code, scrapy
boilerplate and helper scripts.

This is just a spider. To actually search things you will need [PRtest](https://github.com/araknast/prtest).

It's terribly written but it works™, so for right now it's enough.

The spider will crawl in breadth-first order, and process the first 200 links
on any page. The spider will ignore links that:
- Have the"nofollow" attribute set
- Are longer than 190 characters
- Link to the same ~~domain~~ page
- Contain query strings

Additionally, the spider will not crawl pages that:
- Have urls longer than 190 characters
- Have already been crawled
- Do not contain html
- Contain content that is not in English

# Requirements
- python3
- pyssdb
- ssdb
- scrapy
- pycld2

# Using
- Clone this repo.
- Run `./ssdb_setup.sh` to get the latest ssdb version.
- Run `./start_server.sh` to start the db.
- Wait until "started ssdb server" appears in the terminal.
- In another terminal run `./startcrawl`.
- The spider will begin crawling the web and writing the results to the db.
- To stop the crawl, hit Ctrl-C in the terminal running the spider.
- To stop it faster, hit Ctrl-C again.
- To resume the crawl, run `./startcrawl` again.
- To discard crawl progress, run `./endcrawl`.

# Config
- The `blacklist` file tells the spider which sites not to crawl, separated by newlines.
    - The spider uses dumb substring matching. Putting 'wikipedia.org' will
      prevent the spider from crawling 'wikipedia.org', 'en.wikipedia.org', and
      even 'someotherwebsite.com/wikipedia.org'
- The `topsites` file tells the spider where to start crawling from.
- The rest of the spiders settings can be modified by editing the
  `custom_settings` dictionary in the `spid/spiders/mainspider.py` file.
    - Documentation for Scrapy settings can be found [here](https://docs.scrapy.org/en/latest/topics/settings.html)

# Data
Each time the spider crawls a website it will do the following:
1. Add an inverted index entry for each word on the site
2. Add its domain to the referrers list for each link on the site
3. Log the number of total links on the domain to the db
4. Add its domain name to the db

- The referrers for each domain are stored as a zset with keys in the format
  `r:<domain>`.
- The inverted index for any word is stored as a zset with keys in the format
  `w:<word>`.
    - Each entry is a full url and *not* a domain name
    - The score for each entry corresponds to the occurrences of that word on
      the site.
- The number of links on each domain is is stored as an integer value with
  keys in the format `nl:<domain>`.
- The PageRanks for each domain are stored in the hset `pr` where each key
  member is a domain name and each value is the corresponding PageRank.
    - The spider will initialize the PageRank of any new page to 0. Calculation
      should happen after the spider has stopped.

# Gotchas
- When parsing a page, only the first 5000  words will be processed
- Pages that are not crawled but are linked to other pages will still count
  towards their referrers `nl:` and will also get an `r:` entry. They will not
  get an inverted index entry.
- The spider will break if the blackist is empty, just blacklist example.com or
something if you don't want a blacklist.
- This spider makes a lot of requests very quickly, if you have a weak
  DNS server, or weak internet, requests might start failing.  I reccommend
CloudFlare's `1.1.1.1` DNS.
