import scrapy
import redis
import re
import os
import signal
import pycld2 as cld2
from scrapy.spiders import Rule
from scrapy.linkextractors import LinkExtractor
from scrapy.exceptions import CloseSpider
from twisted.internet.error import DNSLookupError
from twisted.internet.error import ConnectionDone
#import pyssdb
#db = pyssdb.Client()
db = redis.Redis("localhost", "8888")
seed_sites = ""
WORDS_RE = re.compile("[a-z']{3,}")

with open("topsites", "r") as sites_file:
    seed_sites = [ s.strip() for s in sites_file.readlines() ]
seed_sites.reverse()

with open("blacklist", "r") as blacklist_file:
    blacklist = [ s.strip() for s in blacklist_file.readlines() ]

print(seed_sites)
print(blacklist)

class WebSpider(scrapy.Spider):
    name = "web"

    custom_settings = {
        "LOG_LEVEL": "INFO",
        "SCHEDULER_DISK_QUEUE": "scrapy.squeues.PickleFifoDiskQueue",
        "SCHEDULER_MEMORY_QUEUE": "scrapy.squeues.FifoMemoryQueue",
        "SCHEDULER_PRIORITY_QUEUE": "scrapy.pqueues.DownloaderAwarePriorityQueue",
        "DEPTH_PRIORITY": 1,
        "CONCURRENT_REQUESTS": 16,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 1,
        "REACTOR_THREADPOOL_MAXSIZE": 30,
        "AUTOTHROTTLE_ENABLED": True,
        "AUTOTHROTTLE_TARGET_CONCURRENCY": 1,
        "COOKIES_ENABLED": False,
        "RETRY_ENABLED": True,
        "RETRY_TIMES": 1,
        "DOWNLOAD_TIMEOUT": 180,
        "REDIRECT_ENABLED": True,
        "REDIRECT_MAX_TIMES": 3,
        "AJAXCRAWL_ENABLED": True,
        "USER_AGENT": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_12_6)", # change this if u want
        "ROBOTSTXT_OBEY": True,
        "TELNETCONSOLE_PASSWORD": "thisisthescrapytelnetpassword",

    }

    start_urls = seed_sites

    @staticmethod
    def link_filter(link):
        return (
            (link.attrib["href"][:7] == "https:/"
            or
            link.attrib["href"][:7] == "http://")
            and
            "rel" in link.attrib and link.attrib["rel"] != "nofollow"
        )
        
    def errback(self, failure):
        # log all errback failures,
        # in case you want to do something special for some errors,
        # you may need the failure's type

        request = failure.request
        #elif isinstance(failure.value, TimeoutError):
        if failure.check(TimeoutError):
            self.logger.error("TimeoutError on {}".format(request.url))
        elif failure.check(DNSLookupError):
            self.logger.error("DNS error on {}".format(request.url))
        else:
            self.logger.error("{} error on {}".format(str(repr(failure)), request.url))

    def parse(self, response):
        page = response.url.split("/")[-2]
        page_url = str(response.url)
        redirector_url = response.request.meta.get("redirect_urls")
        if redirector_url:
            redirector_url = redirector_url[0]
            self.logger.info("(redirected from {})".format(redirector_url))
        else:
            redirector_url = page_url # there is no redirector_url

        for url in blacklist:
            if url in page_url:
                print("{} is in blacklisted urls".format(page_url))
                return

        self.logger.info("handling " + page_url)
        content_type = response.headers[b'Content-Type'].decode().lower()
        if "text/html" not in content_type:
            self.logger.info("not html, skipping...")
            return
        elif "charset=" in content_type:
            if (
                "charset=utf-8" not in content_type
                and
                "charset=utf8" not in content_type
                and
                "charset=ascii" not in content_type
               ):
                self.logger.info("weird encoding \"{}\" skipping... ".format(content_type))
                return

        if len(bytes(page_url, 'utf-8')) > 190:
            self.logger.info("url too long, skipping...")
            return

        content = "".join(response.xpath("//text()").getall())
        page_tld = page_url.split("/")[2].split(".")[-1]
        cld_reliable, content_num_bytes, content_details = cld2.detect(content, hintTopLevelDomain=page_tld)
        content_lang = content_details[0][0]
        if content_lang != "ENGLISH":
            self.logger.info("content in {}, skipping...".format(content_lang.lower()))
            return
#        elif not cld_reliable:
#            self.logger.info("can't tell what language this is, processing anyway...")

        link_elements = response.css("a[href]")
        link_elements = list(filter(self.link_filter, link_elements))
        link_strings = list(map(lambda x: x.attrib['href'].strip().replace(" ", "%20"), link_elements))
        if len(link_strings) > 200:
            link_strings = link_strings[:200]
#        link_strings = list(filter(lambda x: "?" not in x and x != page_url, link_strings))

        link_strings = list(filter(lambda x: 
                                    "?" not in x 
                                    and 
                                    ".".join(page_url.split("/")[2].split(".")[-2:]) not in x
                                    and len(bytes(x, 'utf-8')) < 190
                                    , link_strings))

        link_string = ""
        word = ""

        try:
            matches = list(set(WORDS_RE.finditer(content.lower())))
            if len(matches) > 3000:
                matches = matches[:3000]
            for match in matches:
                word = match.group().replace("'", "")
                if not word:
                    continue
                if len(bytes(word, 'utf-8')) < 190:
                    # w = word
                    db.zincrby("w:" + word, 1, redirector_url)

            for link_string in link_strings:
                # r = referrer
                db.zadd("r:" + link_string, {redirector_url: 0})

            # nl = num links on the page
            db.set("nl:" + redirector_url, len(link_strings))

            # pr = pageRanks
            db.zadd("pr", {str(redirector_url): 0})
            
        except redis.exceptions.ResponseError:
            self.logger.error("<<<<<<<< ERROR WRITING TO REDIS >>>>>>>>>")
            self.logger.info("link string was: \"{}\"".format(link_string))
            self.logger.info("page url was: \"{}\"".format(page_url))
            self.logger.info("word was: \"{}\"".format(word))
            self.logger.error("<<<<<<<< LETS HOPE THE DB ISNT DEAD >>>>>>>>>")
            try:
                db.set("key", "value")
            except redis.exceptions.ResponseError:
                self.logger.error("<<<<<<<< OH GOD THE DB IS DEAD HELP >>>>>>>>>")
                os.remove(os.getcwd() + "/DB_IS_OK")
                os.kill(os.getpid(), signal.SIGINT)
                os.kill(os.getpid(), signal.SIGINT)
                #raise CloseSpider("error writing to db, shutting down...")
            else:
                self.logger.error("<<<<<<<< PHEW EVERYTHING IS FINE >>>>>>>>>")

        self.logger.info("revindexed " + page_url)
        link_requests = list(map(lambda x: scrapy.http.Request(x, errback=self.errback), link_strings))
        return link_requests
