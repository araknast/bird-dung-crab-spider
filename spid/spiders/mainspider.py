import re
import os
import scrapy
import signal
import pyssdb
import pycld2 as cld2
from scrapy.spiders import Rule
from scrapy.linkextractors import LinkExtractor
from scrapy.exceptions import CloseSpider
from twisted.internet.error import DNSLookupError
from twisted.internet.error import ConnectionDone

db = pyssdb.Client()
seed_sites = ""
WORDS_RE = re.compile("[a-z']{3,}")

with open("topsites", "r") as sites_file:
    seed_sites = [s.strip() for s in sites_file.readlines()]
seed_sites.reverse()

with open("blacklist", "r") as blacklist_file:
    blacklist = [s.strip() for s in blacklist_file.readlines()]

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
        "DEPTH_LIMIT": 10,
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
        "USER_AGENT": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_12_6)",  # change this if u want
        "ROBOTSTXT_OBEY": True,
        "TELNETCONSOLE_PASSWORD": "thisisthescrapytelnetpassword",
    }

    start_urls = seed_sites

    @staticmethod
    def link_filter(link):
        return (
            (
                link.attrib["href"][:7] == "https:/"
                or link.attrib["href"][:7] == "http://"
            )
            and "rel" in link.attrib
            and link.attrib["rel"] != "nofollow"
        )

    @staticmethod
    def index(content, max_word_len, max_words, key, redirector_url):
        matches = list(WORDS_RE.finditer(content))
        words = list(map(lambda x: x.group(), matches))
        words = list(filter(lambda x: len(x) < max_word_len, words))

        if len(words) > max_words:
            words = words[:max_words]

        for word in words:
            word = word.replace("'", "")
            if word:
                db.zincr(key + word, redirector_url, 1)

    def errback(self, failure):
        request = failure.request
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
        depth = response.request.meta.get("depth")
        priority = response.request.priority
        if redirector_url:
            redirector_url = redirector_url[0]
            self.logger.info("(redirected from {})".format(redirector_url))
        else:
            redirector_url = page_url  # there is no redirector_url
        
        redirector_domain = redirector_url.split("/")[2]

        for url in blacklist:
            if url in page_url:
                print("{} is in blacklisted urls".format(page_url))
                return

        self.logger.info(
            "handling {} (depth: {} priority: {})".format(page_url, depth, priority)
        )
        content_type = response.headers[b"Content-Type"].decode().lower()
        if "text/html" not in content_type:
            self.logger.info("not html, skipping...")
            return
        elif "charset=" in content_type:
            if (
                "charset=utf-8" not in content_type
                and "charset=utf8" not in content_type
                and "charset=\"utf8\"" not in content_type
                and "charset=iso-8859-1" not in content_type
                and "charset=\"iso-8859-1\"" not in content_type
                and "charset=ascii" not in content_type
            ):
                self.logger.info(
                    'weird encoding "{}" skipping... '.format(content_type)
                )
                return

        if len(bytes(page_url, "utf-8")) > 190:
            self.logger.info("url too long, skipping...")
            return

        page_title = response.xpath("//title//text()").get()
        if page_title is None:
            page_title = ""
        else:
            page_title = page_title.lower()

        #        div_content = response.xpath("//div//text()").getall()
        # a_content = " ".join(response.xpath("//a[@href]//text()").getall()).lower()
        p_content = response.xpath("//p//text()").getall()
        script_content = response.xpath("//script//text()").getall()

        #        content = set(div_content + p_content) - set(script_content)
        content = set(p_content) - set(script_content)
        content = " ".join(content).lower()

        page_tld = page_url.split("/")[2].split(".")[-1]
        cld_reliable, content_num_bytes, content_details = cld2.detect(
            content, hintTopLevelDomain=page_tld
        )
        content_lang = content_details[0][0]
        #        if content_lang != "ENGLISH" and cld_reliable:
        if content_lang != "ENGLISH":
            self.logger.info("content in {}, skipping...".format(content_lang.lower()))
            return
        #        elif not cld_reliable:
        #            self.logger.info("can't tell what language this is, processing anyway...")

        link_elements = response.css("a[href]")
        link_elements = list(filter(self.link_filter, link_elements))
        link_strings = list(
            map(lambda x: x.attrib["href"].strip().replace(" ", "%20"), link_elements)
        )
        if len(link_strings) > 200:
            link_strings = link_strings[:200]

        link_strings = list(
            filter(
                lambda x: "?" not in x
                and page_url not in x
                and len(bytes(x, "utf-8")) < 190,
                link_strings,
            )
        )

        link_string = ""
        word = ""

        try:
# a content isnt very useful
#            self.index(
#                content=a_content,
#                max_word_len=32,
#                max_words=1000,
#                key="a:",
#                redirector_url=redirector_url,
#            )
            self.index(
                content=page_title,
                max_word_len=32,
                max_words=32,
                key="t:",
                redirector_url=redirector_url,
            )

            self.index(
                content=content,
                max_word_len=32,
                max_words=5000,
                key="w:",
                redirector_url=redirector_url,
            )
            for i in range(1, 7):
                h_content = " ".join(
                    response.xpath("//h{}//text()".format(i)).getall()
                ).lower()
                if h_content:
                    self.index(
                        content=h_content,
                        max_word_len=32,
                        max_words=32,
                        key="h{}:".format(i),
                        redirector_url=redirector_url,
                    )

            for link_string in link_strings:
                link_string = link_string.split("/")[2] # extract the domain name
                db.zset("r:" + link_string, redirector_domain, 0)

            domain_nl = db.get("nl:" + redirector_domain)
            page_nl = len(link_strings)
            if domain_nl is None:
                domain_nl = 0
            domain_nl = int(page_nl) + int(domain_nl)

            db.set("nl:" + redirector_domain, domain_nl)

            db.hset("pr", redirector_domain, "0")

        except pyssdb.error:
            self.logger.error("<<<<<<<< ERROR WRITING TO SSDB >>>>>>>>>")
            self.logger.info('link string was: "{}"'.format(link_string))
            self.logger.info('page url was: "{}"'.format(page_url))
            self.logger.info('word was: "{}"'.format(word))
            self.logger.error("<<<<<<<< LETS HOPE THE DB ISNT DEAD >>>>>>>>>")
            try:
                db.set("key", "value")
            except pyssdb.error:
                self.logger.error("<<<<<<<< OH GOD THE DB IS DEAD HELP >>>>>>>>>")
                os.remove(os.getcwd() + "/DB_IS_OK")
                os.kill(os.getpid(), signal.SIGINT)
                os.kill(os.getpid(), signal.SIGINT)
            else:
                self.logger.error("<<<<<<<< PHEW EVERYTHING IS FINE >>>>>>>>>")

        self.logger.info("revindexed " + page_url)
        link_requests = list(
            map(lambda x: scrapy.http.Request(x, errback=self.errback), link_strings)
        )
        return link_requests
