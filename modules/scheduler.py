import threading, time, json, os
from datetime import datetime

CFG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config.json')
DEFAULTS = {"extra_fetches": ["06:00"], "auto_translate": True, "keep_days": 30, "port": 8765, "articles_per_topic_per_fetch": 3}

def load_config() -> dict:
    if os.path.exists(CFG_PATH):
        try:
            cfg = json.load(open(CFG_PATH, encoding='utf-8'))
            for k, v in DEFAULTS.items(): cfg.setdefault(k, v)
            return cfg
        except Exception: pass
    return DEFAULTS.copy()

def save_config(cfg: dict):
    existing = load_config(); existing.update(cfg)
    with open(CFG_PATH, 'w', encoding='utf-8') as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)

def _hm(hhmm: str):
    try: h, m = hhmm.strip().split(':'); return int(h), int(m)
    except Exception: return None, None

class Scheduler:
    """
    Fixed daily fetch at 23:50 (saves as next day's date 'tomorrow').
    Plus optional extra fetches at user-defined times.
    Supports cumulative fetching: if a slot was missed, later slots fetch more articles.
    """
    def __init__(self, on_fetch, on_cleanup):
        self.on_fetch   = on_fetch    # (date, label, cutoff_hour, count_per_topic) -> int
        self.on_cleanup = on_cleanup
        self._fired = set()
        self._lock  = threading.Lock()

    def start(self):
        threading.Thread(target=self._loop, daemon=True).start()

    def _should_fire(self, date: str, key: str) -> bool:
        k = f"{date}|{key}"
        with self._lock:
            if k in self._fired: return False
            self._fired.add(k); return True

    def get_missed_slots(self, date: str, current_slot: str, cfg: dict) -> int:
        """Count how many earlier slots were missed today."""
        slots = sorted(cfg.get('extra_fetches', []))
        current_idx = -1
        for i, s in enumerate(slots):
            if s == current_slot:
                current_idx = i
                break
        if current_idx <= 0:
            return 0

        missed = 0
        for i in range(current_idx):
            k = f"{date}|{slots[i]}"
            with self._lock:
                if k not in self._fired:
                    missed += 1
        return missed

    def _loop(self):
        while True:
            try:
                cfg = load_config()
                now = datetime.now()
                today = now.strftime('%Y-%m-%d')
                hhmm  = now.strftime('%H:%M')
                base_count = cfg.get('articles_per_topic_per_fetch', 3)

                # ── Fixed 23:50 fetch — saves as TOMORROW's date ──────────
                if hhmm == '23:50':
                    from datetime import timedelta
                    tomorrow = (now + timedelta(days=1)).strftime('%Y-%m-%d')
                    if self._should_fire(today, '23:50'):
                        print(f"[Scheduler] 23:50 fixed fetch → saving as {tomorrow}")
                        self.on_fetch(tomorrow, '23:50 — Bản gốc ngày', cutoff_hour=23, count_per_topic=base_count)
                        self.on_cleanup()

                # ── User extra fetches (same day) ─────────────────────────
                for t in cfg.get('extra_fetches', []):
                    h, m = _hm(t)
                    if h is None: continue
                    if now.hour == h and now.minute == m:
                        if self._should_fire(today, t):
                            missed = self.get_missed_slots(today, t, cfg)
                            actual_count = base_count * (1 + missed)
                            label = f"{t} — Mốc {t}"
                            if missed > 0:
                                label += f" (+{missed} mốc bù)"
                            print(f"[Scheduler] {t} fetch: {actual_count}/topic (missed {missed} earlier slots)")
                            self.on_fetch(today, label, cutoff_hour=h, count_per_topic=actual_count)
            except Exception as e:
                print(f"[Scheduler] Error: {e}")
            time.sleep(28)

    def run_now(self, date: str, label: str, cutoff_hour: int = None, count_per_topic: int = None, use_wayback=None) -> int:
        """Manual fetch. If count_per_topic is None, auto-calculate based on missed slots.
        use_wayback: None=auto, True=force Wayback, False=RSS only."""
        cfg = load_config()
        base_count = cfg.get('articles_per_topic_per_fetch', 3)

        if count_per_topic is None:
            # Calculate missed slots
            slots = sorted(cfg.get('extra_fetches', []))
            now = datetime.now()
            current_time = now.strftime('%H:%M')

            # Find which slots should have fired by now
            missed = 0
            for t in slots:
                h, m = _hm(t)
                if h is None: continue
                if (h < now.hour) or (h == now.hour and m <= now.minute):
                    k = f"{date}|{t}"
                    with self._lock:
                        if k not in self._fired:
                            missed += 1
            count_per_topic = base_count * (1 + missed)
            if missed > 0:
                label += f" (+{missed} mốc bù, {count_per_topic}/chủ đề)"

        count = self.on_fetch(date, label, cutoff_hour=cutoff_hour, count_per_topic=count_per_topic, use_wayback=use_wayback)

        # Mark current time slot as fired
        now_hm = datetime.now().strftime('%H:%M')
        cfg_slots = sorted(cfg.get('extra_fetches', []))
        # Mark the closest past slot as fired
        for t in cfg_slots:
            h, m = _hm(t)
            if h is not None:
                now = datetime.now()
                if (h < now.hour) or (h == now.hour and m <= now.minute):
                    k = f"{date}|{t}"
                    with self._lock:
                        self._fired.add(k)

        return count

    def clear_date(self, date: str):
        with self._lock:
            self._fired = {k for k in self._fired if not k.startswith(date)}
