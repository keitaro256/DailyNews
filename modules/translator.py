import urllib.request, urllib.parse, json
from concurrent.futures import ThreadPoolExecutor

def _gtranslate(text: str, tl: str = 'vi') -> str:
    if not text or not text.strip():
        return text or ''
    chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
    parts = []
    for chunk in chunks:
        try:
            q = urllib.parse.urlencode({'client':'gtx','sl':'auto','tl':tl,'dt':'t','q':chunk})
            req = urllib.request.Request(
                f'https://translate.googleapis.com/translate_a/single?{q}',
                headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                parts.append(''.join(s[0] for s in data[0] if s and s[0]))
        except Exception:
            parts.append(chunk)
    return ' '.join(parts)

def translate(text: str, tl: str = 'vi') -> str:
    if not text or not text.strip():
        return text or ''
    try:
        return _gtranslate(text, tl)
    except Exception:
        return text or ''

def translate_many(texts: list, max_workers: int = 6, tl: str = 'vi') -> list:
    """Translate many texts in parallel. Returns list of same length/order."""
    if not texts:
        return []
    n = len(texts)
    results = [''] * n
    def _job(args):
        i, t = args
        if not t or not t.strip():
            results[i] = ''
            return
        try:
            results[i] = _gtranslate(t, tl)
        except Exception:
            results[i] = t
    workers = max(1, min(max_workers, n))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(_job, list(enumerate(texts))))
    return results

def translate_articles(articles: list) -> list:
    """Translate title + description of international articles in parallel."""
    tasks = []
    for i, a in enumerate(articles):
        try:
            if a.get('category') == 'international' and not a.get('title_vi'):
                if a.get('title'):
                    tasks.append((i, 'title_vi', a.get('title', '')))
                if a.get('description'):
                    tasks.append((i, 'description_vi', a.get('description', '')))
            elif a.get('category') == 'vietnam' and not a.get('title_vi'):
                a['title_vi'] = a.get('title', '')
                a['description_vi'] = a.get('description', '')
        except Exception:
            a.setdefault('title_vi', a.get('title', ''))
            a.setdefault('description_vi', a.get('description', ''))

    if tasks:
        translations = translate_many([t[2] for t in tasks], max_workers=8)
        for (i, field, orig), tr in zip(tasks, translations):
            articles[i][field] = tr or orig

    for a in articles:
        a.setdefault('title_vi', a.get('title', ''))
        a.setdefault('description_vi', a.get('description', ''))
    return articles

def translate_paragraphs(paragraphs: list, max_workers: int = 6) -> list:
    """Translate article paragraphs in parallel. Always returns same-length list."""
    if not paragraphs:
        return []
    texts, tags = [], []
    for p in paragraphs:
        if isinstance(p, dict):
            texts.append(p.get('text', ''))
            tags.append(p.get('tag', 'p'))
        else:
            texts.append(str(p))
            tags.append('p')
    translations = translate_many(texts, max_workers=max_workers)
    result = []
    for tr, tag, orig in zip(translations, tags, texts):
        result.append({'text': tr or orig, 'tag': tag})
    return result
