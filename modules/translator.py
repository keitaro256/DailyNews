import urllib.request, urllib.parse, json, time

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
        result = _gtranslate(text, tl)
        time.sleep(0.1)
        return result
    except Exception:
        return text or ''

def translate_articles(articles: list) -> list:
    for a in articles:
        try:
            if a.get('category') == 'international' and not a.get('title_vi'):
                a['title_vi'] = translate(a.get('title', ''))
                a['description_vi'] = translate(a.get('description', '')) if a.get('description') else ''
            elif a.get('category') == 'vietnam' and not a.get('title_vi'):
                a['title_vi'] = a.get('title', '')
                a['description_vi'] = a.get('description', '')
        except Exception:
            a.setdefault('title_vi', a.get('title', ''))
            a.setdefault('description_vi', a.get('description', ''))
    return articles

def translate_paragraphs(paragraphs: list) -> list:
    """Translate paragraphs safely - always returns same-length list."""
    result = []
    for p in paragraphs:
        try:
            text = p.get('text', '') if isinstance(p, dict) else str(p)
            tag = p.get('tag', 'p') if isinstance(p, dict) else 'p'
            vi = translate(text)
            result.append({'text': vi or text, 'tag': tag})
        except Exception:
            # On any error, return original text
            text = p.get('text', '') if isinstance(p, dict) else str(p)
            tag = p.get('tag', 'p') if isinstance(p, dict) else 'p'
            result.append({'text': text, 'tag': tag})
    return result
