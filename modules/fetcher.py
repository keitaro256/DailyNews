"""fetcher.py v4.5 - CDX via HTTPS, parallel Wayback prefetch, faster timeouts"""
import requests, re, time, urllib.parse as _uparse
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed

VN_DOMAINS = ['vnexpress.net','cafef.vn','nhandan.vn','baochinhphu.vn','tuoitre.vn','thanhnien.vn',
    'dantri.com.vn','vietnamnet.vn','ictnews.vietnamnet.vn','vov.vn','zingnews.vn',
    'nld.com.vn','laodong.vn','tienphong.vn','vtcnews.vn','kenh14.vn','genk.vn',
    'soha.vn','cafebiz.vn','ndh.vn','vietstock.vn']

def _is_vn_url(url):
    if not url: return False
    return any(d in url.lower() for d in VN_DOMAINS)

def _is_vn_text(title):
    if not title: return False
    vn = 'àáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵđ'
    return sum(1 for c in title.lower() if c in vn) >= 2

FINANCE_KW = ['stock','market','economy','gdp','inflation','interest rate','fed ','bank','invest',
    'finance','revenue','profit','earnings','wall street','nasdaq','dow','s&p','bitcoin','crypto',
    'bond','commodity','oil price','gold price','trade war','tariff',
    'cổ phiếu','chứng khoán','kinh tế','lãi suất','ngân hàng','tài chính','đầu tư','thị trường','lạm phát',
    'doanh thu','lợi nhuận','xuất khẩu','nhập khẩu']
POLITICS_KW = ['president','congress','senate','election','political','government','diplomat','sanction',
    'military','defense','war ','conflict','nato','united nations','treaty','legislation',
    'supreme court','white house','parliament','minister','ambassador',
    'chính trị','chính phủ','quốc hội','thủ tướng','chủ tịch','bộ trưởng','ngoại giao','quốc phòng',
    'an ninh','đảng','bầu cử','luật','nghị định','pháp luật','tòa án']
TECH_KW = ['ai ','artificial intelligence','machine learning','openai','chatgpt','google','apple',
    'microsoft','meta ','nvidia','startup','silicon valley','software','robot','autonomous',
    'chip','semiconductor','quantum','blockchain','cloud computing',
    'công nghệ','trí tuệ nhân tạo','phần mềm','khởi nghiệp','bán dẫn','robot','tự động','số hóa']

def classify_topic(title, desc='', source=''):
    text = f"{title} {desc} {source}".lower()
    s = {'finance':0,'politics':0,'tech_ai':0}
    for kw in FINANCE_KW:
        if kw in text: s['finance']+=1
    for kw in POLITICS_KW:
        if kw in text: s['politics']+=1
    for kw in TECH_KW:
        if kw in text: s['tech_ai']+=1
    b = max(s, key=s.get)
    return b if s[b]>0 else 'general'

def estimate_importance(title, desc='', source=''):
    text = f"{title} {desc}".lower()
    score = 3
    if any(w in text for w in ['breaking','exclusive','urgent','nóng','khẩn cấp','đột phá']): score+=2
    if any(w in text for w in ['war','crisis','crash','record','historic','chiến tranh','khủng hoảng','kỷ lục']): score+=1
    if any(s in source.lower() for s in ['reuters','bloomberg','guardian','deutsche welle','wsj','vnexpress','chính phủ','nhân dân']): score+=1
    return min(5,max(1,score))

INTL_FEEDS = {
    'finance': [
        ('Yahoo Finance','https://finance.yahoo.com/news/rssindex','finance'),
        ('Yahoo Finance','https://finance.yahoo.com/rss/topstories','finance'),
        ('CNBC','https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10001147','finance'),
        ('MarketWatch','https://feeds.marketwatch.com/marketwatch/topstories/','finance'),
    ],
    'politics': [
        ('The Guardian','https://www.theguardian.com/world/rss','politics'),
        ('Deutsche Welle','https://rss.dw.com/rdf/rss-en-top','politics'),
        ('Al Jazeera','https://www.aljazeera.com/xml/rss/all.xml','politics'),
        ('NPR World','https://feeds.npr.org/1004/rss.xml','politics'),
    ],
    'tech_ai': [
        ('TechCrunch','https://techcrunch.com/feed/','tech_ai'),
        ('The Verge','https://www.theverge.com/rss/index.xml','tech_ai'),
        ('Ars Technica','https://feeds.arstechnica.com/arstechnica/index','tech_ai'),
        ('Wired','https://www.wired.com/feed/rss','tech_ai'),
    ],
}
VN_FEEDS = {
    'finance': [
        ('VnExpress KD','https://vnexpress.net/rss/kinh-doanh.rss','finance'),
        ('CafeF','https://cafef.vn/vi-mo-dau-tu.rss','finance'),
        ('CafeF CK','https://cafef.vn/thi-truong-chung-khoan.rss','finance'),
        ('CafeF TC','https://cafef.vn/tai-chinh-ngan-hang.rss','finance'),
        ('CafeBiz','https://cafebiz.vn/rss/ngan-hang-tai-chinh.rss','finance'),
    ],
    'politics': [
        ('VnExpress TG','https://vnexpress.net/rss/the-gioi.rss','politics'),
        ('VnExpress TS','https://vnexpress.net/rss/thoi-su.rss','politics'),
        ('Tuoi Tre','https://tuoitre.vn/rss/the-gioi.rss','politics'),
    ],
    'tech_ai': [
        ('VnExpress CN','https://vnexpress.net/rss/so-hoa.rss','tech_ai'),
        ('Genk','https://genk.vn/rss/home.rss','tech_ai'),
        ('VietnamNet CN','https://vietnamnet.vn/rss/cong-nghe.rss','tech_ai'),
    ],
}

# ═══════════════════════════════════════════════════════════════════════════════
# WAYBACK-SPECIFIC FEEDS — Only sources with PROVEN reliable archive.org coverage.
# These are used when fetching historical dates (force Wayback mode). Smaller set
# means faster parallel queries and much higher hit rate.
# ═══════════════════════════════════════════════════════════════════════════════
INTL_WAYBACK_FEEDS = {
    'finance': [
        # Al Jazeera's /all feed has economic/business stories mixed in
        ('Al Jazeera','https://www.aljazeera.com/xml/rss/all.xml','finance'),
        # TechCrunch has fintech / startup funding / crypto coverage
        ('TechCrunch','https://techcrunch.com/feed/','finance'),
    ],
    'politics': [
        ('Al Jazeera','https://www.aljazeera.com/xml/rss/all.xml','politics'),
        # BBC main RSS — very popular, heavily crawled by Wayback
        ('BBC News','https://feeds.bbci.co.uk/news/rss.xml','politics'),
        # NPR top stories — widely archived
        ('NPR Top','https://feeds.npr.org/1001/rss.xml','politics'),
    ],
    'tech_ai': [
        ('TechCrunch','https://techcrunch.com/feed/','tech_ai'),
        ('The Verge','https://www.theverge.com/rss/index.xml','tech_ai'),
        # Hacker News — heavily archived aggregator for tech/AI news
        ('Hacker News','https://news.ycombinator.com/rss','tech_ai'),
    ],
}

# Vietnamese news: Wayback coverage is VERY sparse for VN sites.
# We include the most popular VN feeds — some archives may exist, but hit rate is low.
VN_WAYBACK_FEEDS = {
    'finance': [
        ('VnExpress KD','https://vnexpress.net/rss/kinh-doanh.rss','finance'),
    ],
    'politics': [
        ('VnExpress TG','https://vnexpress.net/rss/the-gioi.rss','politics'),
        ('Tuoi Tre TG','https://tuoitre.vn/rss/the-gioi.rss','politics'),
    ],
    'tech_ai': [
        ('VnExpress CN','https://vnexpress.net/rss/so-hoa.rss','tech_ai'),
    ],
}

def _parse_pub_date(item):
    for tag_name in ['pubDate','published','dc:date','updated']:
        tag = item.find(tag_name)
        if tag and tag.string:
            text = tag.string.strip()
            try: return parsedate_to_datetime(text).strftime('%Y-%m-%d')
            except: pass
            for fmt in ('%Y-%m-%dT%H:%M:%S%z','%Y-%m-%dT%H:%M:%SZ','%Y-%m-%d %H:%M:%S','%Y-%m-%d'):
                try: return datetime.strptime(text[:25],fmt).strftime('%Y-%m-%d')
                except: continue
    return ''

def _date_matches(pub_date, target_date, tolerance_days=1):
    """Check if pub_date matches target_date within tolerance (for timezone differences)."""
    if not pub_date or not target_date:
        return True  # No strict requirement
    if pub_date == target_date:
        return True
    try:
        from datetime import datetime as _dt, timedelta as _td
        pd = _dt.strptime(pub_date, '%Y-%m-%d')
        td = _dt.strptime(target_date, '%Y-%m-%d')
        return abs((pd - td).days) <= tolerance_days
    except:
        return False

def _parse_rss(url, target_date='', timeout=15):
    try:
        headers = {'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0',
                   'Accept':'application/rss+xml, application/xml, text/xml, */*'}
        resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, 'lxml-xml')
        items = []
        for item in soup.find_all('item'):
            t = item.find('title')
            d = item.find('description')
            l = item.find('link')
            title = t.get_text(strip=True) if t else ''
            desc = ''
            if d:
                raw = d.get_text(strip=True)
                ds = BeautifulSoup(raw, 'html.parser')
                desc = ds.get_text(strip=True)[:800]  # Longer descriptions
            link = ''
            if l:
                link = l.get_text(strip=True)
                if not link: link = l.get('href','')
                if not link and l.next_sibling:
                    ns = str(l.next_sibling).strip()
                    if ns.startswith('http'): link = ns
            pub = _parse_pub_date(item)
            if target_date and pub and not _date_matches(pub, target_date, tolerance_days=1): continue
            if title and link: items.append({'title':title,'description':desc,'url':link,'pub_date':pub})
        if not items:
            for entry in soup.find_all('entry'):
                t = entry.find('title')
                s = entry.find('summary') or entry.find('content')
                l = entry.find('link')
                pub = _parse_pub_date(entry)
                if target_date and pub and not _date_matches(pub, target_date, tolerance_days=1): continue
                title = t.get_text(strip=True) if t else ''
                link = l.get('href','') if l else ''
                desc = ''
                if s:
                    ds = BeautifulSoup(s.get_text(strip=True),'html.parser')
                    desc = ds.get_text(strip=True)[:800]
                if title and link: items.append({'title':title,'description':desc,'url':link,'pub_date':pub})
        return items
    except Exception as e:
        print(f"[Fetcher] RSS error {url}: {e}")
        return []

def _cdx_query(url, from_ts, to_ts, timeout=15):
    """Query Wayback CDX API for ALL snapshots within a time range.
    Returns list of (timestamp, original_url) tuples. Much more flexible than availability API."""
    try:
        # Use HTTPS — HTTP port 80 is often blocked on corporate/home networks
        cdx_url = (f"https://web.archive.org/cdx/search/cdx?"
                   f"url={_uparse.quote(url, safe='')}&"
                   f"from={from_ts}&to={to_ts}&"
                   f"output=json&limit=30&filter=statuscode:200")
        resp = requests.get(cdx_url, timeout=timeout,
                            headers={'User-Agent':'Mozilla/5.0 NewsReader/4.4'})
        if resp.status_code != 200:
            return []
        text = resp.text.strip()
        if not text or text == '[]':
            return []
        data = resp.json()
        if not data or len(data) < 2:
            return []
        header = data[0]
        try:
            ts_idx = header.index('timestamp')
            orig_idx = header.index('original')
        except ValueError:
            return []
        results = []
        for row in data[1:]:
            if len(row) > max(ts_idx, orig_idx):
                results.append((row[ts_idx], row[orig_idx]))
        return results
    except Exception as e:
        # Shortened log to reduce noise
        etype = type(e).__name__
        print(f"[CDX] {etype} for {url[:60]}...")
        return []


def fetch_wayback_rss(feed_url, target_date, timeout=15):
    """Fetch RSS snapshot from Wayback Machine for a past date.
    
    Strategy (CDX-based): 1 query with broad window, smart scoring.
    """
    try:
        target_dt = datetime.strptime(target_date, '%Y-%m-%d')
    except:
        return []
    
    # Single query with broad window — no slow fallback retry
    from_ts = (target_dt - timedelta(days=5)).strftime('%Y%m%d')
    to_ts = (target_dt + timedelta(days=21)).strftime('%Y%m%d')
    
    snapshots = _cdx_query(feed_url, from_ts, to_ts, timeout)
    
    if not snapshots:
        return []
    
    # Score each snapshot: prefer target+1 to target+3
    best = None
    best_score = float('inf')
    for ts, orig in snapshots:
        try:
            snap_dt = datetime.strptime(ts[:8], '%Y%m%d')
            diff = (snap_dt - target_dt).days
            if 1 <= diff <= 3:
                score = diff
            elif diff == 0:
                score = 4
            elif 4 <= diff <= 7:
                score = 5 + (diff - 3)
            elif 8 <= diff <= 14:
                score = 10 + (diff - 7)
            elif diff < 0:
                score = 50 + abs(diff)
            else:
                score = 20 + (diff - 14)
            if score < best_score:
                best_score = score
                best = (ts, orig, diff)
        except: continue
    
    if not best:
        return []
    
    best_ts, best_orig, diff = best
    raw_url = f"https://web.archive.org/web/{best_ts}id_/{feed_url}"
    
    return _parse_rss(raw_url, target_date=target_date, timeout=timeout)

def fetch_news(date, existing_urls, count_per_topic=3, cutoff_hour=None, global_urls=None, use_wayback=None):
    """Fetch news articles for a date.
    
    use_wayback:
      - None (default): auto — use Wayback if date is >2 days ago AND regular RSS returns nothing
      - True: always try Wayback (force historical mode)
      - False: only use regular RSS (no fallback)
    """
    all_articles = []
    today = datetime.now().strftime('%Y-%m-%d')
    if date > today: return []
    all_seen = set(existing_urls)  # always dedupe against same-date articles
    
    # Determine days ago for auto mode
    try:
        days_ago = (datetime.strptime(today, '%Y-%m-%d') - datetime.strptime(date, '%Y-%m-%d')).days
    except:
        days_ago = 0
    
    # Auto-detect Wayback need: past date >2 days old (regular RSS won't have articles that old)
    auto_wayback = (use_wayback is None) and (days_ago > 2)
    force_wayback = use_wayback is True
    use_wb = (force_wayback or auto_wayback) and (date < today)
    
    # CRITICAL: When using Wayback for historical fetch, DON'T dedupe against global_urls.
    # Historical articles may coincidentally share URLs with current-date articles,
    # but we still want to save them under the historical date.
    if global_urls and not use_wb:
        all_seen |= global_urls
    
    target_filter = date if date < today else ''
    
    # ── CHOOSE FEED SET BASED ON MODE ────────────────────────────────────────
    # Regular RSS mode: use the full feed set (many sources, current news)
    # Wayback mode: use curated well-archived sources (fewer, high hit rate)
    if use_wb:
        intl_feeds = INTL_WAYBACK_FEEDS
        vn_feeds = VN_WAYBACK_FEEDS
        total_feeds = sum(len(f) for f in intl_feeds.values()) + sum(len(f) for f in vn_feeds.values())
        print(f"[Fetcher] Wayback mode: dùng {total_feeds} nguồn chuyên cho archive (thay vì nguồn thường)")
    else:
        intl_feeds = INTL_FEEDS
        vn_feeds = VN_FEEDS
    
    # ── PARALLEL WAYBACK PREFETCH ────────────────────────────────────────────
    # Instead of sequentially hitting archive.org for each feed (taking minutes),
    # dispatch all Wayback queries in parallel with a thread pool.
    wayback_items = {}  # feed_url -> list of items
    if use_wb:
        all_feed_urls = []
        for region_feeds_dict in [intl_feeds, vn_feeds]:
            for feeds in region_feeds_dict.values():
                for _, feed_url, _ in feeds:
                    if feed_url not in all_feed_urls:
                        all_feed_urls.append(feed_url)
        
        print(f"[Wayback] Dispatching parallel queries for {len(all_feed_urls)} curated feeds…")
        t_start = time.time()
        
        def _one_wb(url):
            try:
                items = fetch_wayback_rss(url, date, timeout=15)
                return url, items
            except Exception as e:
                return url, []
        
        # 8 parallel workers — balances speed with being kind to archive.org
        with ThreadPoolExecutor(max_workers=8) as ex:
            futures = [ex.submit(_one_wb, url) for url in all_feed_urls]
            for fut in as_completed(futures):
                try:
                    url, items = fut.result(timeout=30)
                    wayback_items[url] = items
                    if items:
                        print(f"[Wayback] ✓ {url[:60]} → {len(items)} bài")
                except Exception:
                    pass
        
        elapsed = time.time() - t_start
        hits = sum(1 for v in wayback_items.values() if v)
        print(f"[Wayback] Hoàn tất sau {elapsed:.1f}s — {hits}/{len(all_feed_urls)} nguồn có archive")

    for region_feeds, category in [(intl_feeds,'international'),(vn_feeds,'vietnam')]:
        for topic, feeds in region_feeds.items():
            topic_articles = []
            for source_name, feed_url, default_topic in feeds:
                if len(topic_articles) >= count_per_topic: break
                
                # Step 1: try regular RSS (skip if force_wayback=True)
                items = [] if force_wayback else _parse_rss(feed_url, target_date=target_filter)
                
                # Step 2: Wayback fallback — use prefetched cache (parallel fetched above)
                if not items and use_wb:
                    items = wayback_items.get(feed_url, [])
                    if items:
                        print(f"[Fetcher] Wayback: {source_name} → {len(items)} bài cho {date}")
                
                for item in items:
                    if len(topic_articles) >= count_per_topic: break
                    if not item['title'] or item['url'] in all_seen: continue
                    if category=='international' and (_is_vn_url(item['url']) or _is_vn_text(item['title'])): continue
                    real_topic = classify_topic(item['title'], item['description'], source_name)
                    if real_topic == 'general': real_topic = default_topic
                    article = {
                        'date':date,'category':category,'topic':real_topic,'source':source_name,
                        'title':item['title'],'description':item['description'],'url':item['url'],
                        'title_vi': item['title'] if category=='vietnam' else '',
                        'description_vi': item['description'] if category=='vietnam' else '',
                        'importance': estimate_importance(item['title'],item['description'],source_name),
                    }
                    all_seen.add(item['url'])
                    topic_articles.append(article)
                time.sleep(0.3)
            all_articles.extend(topic_articles)
    return all_articles

# ── Ad filtering ──────────────────────────────────────────────────────────────
AD_TEXT_RE = [
    re.compile(r'(subscribe|sign up|newsletter|đăng ký nhận)', re.I),
    re.compile(r'(advertisement|sponsored|quảng cáo|tài trợ)', re.I),
    re.compile(r'(cookie|privacy policy|terms of service|điều khoản)', re.I),
    re.compile(r'(download our app|tải ứng dụng)', re.I),
    re.compile(r'(related articles|bài viết liên quan|tin cùng chuyên mục)', re.I),
    re.compile(r'(all rights reserved|bản quyền|copyright)', re.I),
    re.compile(r'(bình luận|ý kiến bạn đọc|comment below)', re.I),
    re.compile(r'(most popular|most read|tin đọc nhiều)', re.I),
    re.compile(r'(accept all|reject all|manage cookies)', re.I),
    re.compile(r'(share on|chia sẻ lên|follow us on)', re.I),
    re.compile(r'^(share|tweet|email|print|in bài)$', re.I),
    re.compile(r'(read more|xem tiếp|đọc thêm)\s*[→»>]?\s*$', re.I),
]
AD_CLASS_RE = re.compile(
    r'(ad[s_-]|banner|promo|sponsor|social|share|related|sidebar|widget|'
    r'comment|footer|nav|menu|breadcrumb|tag-?list|popup|modal|overlay|'
    r'newsletter|signup|login|search|pagination|author-bio|recommended|'
    r'outbrain|taboola|trending)', re.I)


def _is_ad(text):
    if not text or len(text)<20: return True
    return any(p.search(text) for p in AD_TEXT_RE)

def _safe_classes(el):
    try:
        if el is None: return ''
        c = el.get('class', None)
        if c is None: return ''
        if isinstance(c, list): return ' '.join(c)
        return str(c)
    except: return ''

def _safe_attr(el, attr, default=''):
    try:
        if el is None: return default
        v = el.get(attr, default)
        return v if v is not None else default
    except: return default

def _is_ad_element(el):
    """Check if an element looks like ad/noise — safe, never crashes."""
    try:
        c = _safe_classes(el)
        i = _safe_attr(el, 'id', '')
        return bool(AD_CLASS_RE.search(f"{c} {i}"))
    except: return False

def _light_clean(soup):
    """Light cleaning: only remove scripts/styles/iframes. Does NOT touch structural elements."""
    try:
        to_rm = list(soup.find_all(['script','style','iframe','noscript']))
        for t in to_rm:
            try: t.decompose()
            except: pass
    except: pass
    return soup

def _find_article(soup):
    """Find the main article container on a LIGHTLY cleaned soup."""
    # Try specific selectors (ordered by specificity)
    selectors = [
        # VnExpress
        lambda s: s.find(True, class_=re.compile(r'fck_detail', re.I)),
        # Generic article body
        lambda s: s.find(True, class_=re.compile(r'article[-_]?(body|content|detail|text)', re.I)),
        lambda s: s.find(True, class_=re.compile(r'(post|entry|story)[-_]?(body|content|detail|text)', re.I)),
        lambda s: s.find(True, class_=re.compile(r'(detail[-_]?content|content[-_]?detail|main[-_]?content)', re.I)),
        # By ID
        lambda s: s.find(True, id=re.compile(r'(article|content|story)[-_]?(body|detail|text|main)', re.I)),
        # By itemprop
        lambda s: s.find(True, attrs={'itemprop': 'articleBody'}),
        # Simple article tag
        lambda s: s.find('article'),
        # Class contains "content" but not "sidebar"
        lambda s: s.find(True, class_=re.compile(r'^(main-?content|page-?content|post-?content|entry-?content)$', re.I)),
    ]
    for sel in selectors:
        try:
            result = sel(soup)
            if result and len(result.get_text(strip=True)) > 100:
                return result
        except: pass
    # Fallback: body
    try: return soup.find('body')
    except: return soup

def fetch_article_content(url):
    """Fetch article — find article FIRST, then filter. Never crashes."""
    # ── Fetch HTML ────────────────────────────────────────────────────────
    html_text = None
    errors = []
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0',
        'Accept': 'text/html,application/xhtml+xml,*/*',
        'Accept-Language': 'en-US,en;q=0.9,vi;q=0.8',
    }
    # Direct
    try:
        resp = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
        resp.raise_for_status()
        html_text = resp.text
    except Exception as e:
        errors.append(str(type(e).__name__))
    # Google cache fallback
    if not html_text:
        try:
            resp = requests.get(f"https://webcache.googleusercontent.com/search?q=cache:{url}",
                                headers=headers, timeout=12, allow_redirects=True)
            if resp.status_code == 200 and len(resp.text) > 500:
                html_text = resp.text
        except Exception as e:
            errors.append(f"cache:{type(e).__name__}")

    if not html_text:
        return {'title':'','paragraphs':[],'images':[],'url':url,'success':False,
                'error':f'Không kết nối được ({", ".join(errors)}). Trang có thể bị chặn.'}

    # ── Parse ─────────────────────────────────────────────────────────────
    try:
        soup = BeautifulSoup(html_text, 'lxml')

        # Step 1: Light clean (only scripts/styles)
        soup = _light_clean(soup)

        # Step 2: Find article container BEFORE heavy cleaning
        article = _find_article(soup)

        # Step 3: Extract title from full soup (before cleaning article)
        title = ''
        try:
            h1 = soup.find('h1')
            if h1: title = h1.get_text(strip=True)
        except: pass
        if not title:
            try:
                t = soup.find('title')
                if t: title = t.get_text(strip=True)
            except: pass

        # Step 4: Extract paragraphs from article container
        # We do NOT heavy-clean the article — instead we filter paragraphs individually
        paragraphs, seen = [], set()
        try:
            elements = article.find_all(['p','h2','h3','h4','blockquote','li'])
        except:
            elements = []

        for el in elements:
            try:
                text = el.get_text(strip=True)
                if not text or len(text) < 20: continue
                if text in seen: continue

                # Skip if this element or its parent is ad-like
                if _is_ad_element(el): continue
                try:
                    if el.parent and _is_ad_element(el.parent): continue
                except: pass

                # Skip ad-like text content
                if _is_ad(text): continue

                seen.add(text)
                tag_name = 'p'
                try: tag_name = el.name or 'p'
                except: pass
                paragraphs.append({'text': text, 'tag': tag_name})
            except: continue

        # Step 5: Images from article container
        images = []
        try:
            for img in article.find_all('img'):
                try:
                    src = _safe_attr(img, 'src', '') or _safe_attr(img, 'data-src', '')
                    if not src: continue
                    if src.startswith('//'): src = 'https:' + src
                    elif src.startswith('/'): src = urljoin(url, src)
                    if not src.startswith('http'): continue
                    try:
                        w = _safe_attr(img, 'width', '')
                        h = _safe_attr(img, 'height', '')
                        if (w and int(w)<50) or (h and int(h)<50): continue
                    except: pass
                    sl = src.lower()
                    if any(x in sl for x in ['pixel','track','beacon','logo','icon','avatar',
                                              'badge','button','banner','sponsor','1x1']): continue
                    if any(e in sl for e in ['.jpg','.jpeg','.png','.webp','.gif']):
                        images.append({'src':src, 'alt':_safe_attr(img,'alt','')})
                except: continue
        except: pass

        return {'title':title or '','paragraphs':paragraphs,'images':images[:5],'url':url,'success':True}

    except Exception as e:
        return {'title':'','paragraphs':[],'images':[],'url':url,'success':False,
                'error':f'Lỗi phân tích: {type(e).__name__}'}
