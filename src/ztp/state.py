"""Kalıcı durum deposu — günlük servis olarak çalışabilmek için (17.5 profil güncelliği, 13.5 açık vaka, 9.2 pencereler).

Ham olaylar SAKLANMAZ (20.1 saklama süreleri: ham olay 90 gün kaynak sistemde; burada yalnızca türev veri).
Saklananlar: varlık-gün özellikleri, cihaz-gün tablosu, veri kalitesi istatistikleri, gözlem grafı kenarları, tespit
geçmişi, risk serileri, yüzdelik havuzu, açık vakalar, takma ad eşlemesi, kuyruk geçmişi, tahmin satırları ve
su seviyesi (son işlenen gün). Tek dosya SQLite (stdlib): müşteri başına bir dosya, taşınabilir, yedeklenebilir.

Tasarım kuralı: toplu koşu (N gün) ile "durumu yükle → bir gün işle → durumu kaydet" döngüsü BİREBİR aynı sonucu
üretmelidir; bu, `tests/test_state.py` içindeki eşdeğerlik testiyle korunur.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Union

import pandas as pd

LOG = logging.getLogger(__name__)
SCHEMA_VERSION = 1
FROZENSET_COLS = ("apps", "devices", "countries", "resources", "honeytokens")
DICT_COLS = ("app_events", "device_events", "country_events", "resource_events", "evidence", "ad_users")
LIST_COLS = ("offhours_hours",)


def _json_default(o: Any) -> Any:
    if isinstance(o, (set, frozenset)):
        return sorted(o)
    if isinstance(o, pd.Timestamp):
        return o.isoformat()
    if hasattr(o, "item"):
        return o.item()
    return str(o)


class StateStore:
    def __init__(self, path: Union[str, Path]):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        self.conn.execute("CREATE TABLE IF NOT EXISTS frames (name TEXT PRIMARY KEY, columns TEXT NOT NULL, rows TEXT NOT NULL)")
        self.conn.commit()
        ver = self.get("schema_version")
        if ver is None:
            self.put("schema_version", SCHEMA_VERSION)
        elif int(ver) != SCHEMA_VERSION:
            raise RuntimeError(f"Durum deposu şema sürümü uyumsuz: {ver} ≠ {SCHEMA_VERSION} ({self.path})")

    # ---- anahtar-değer ---------------------------------------------------------
    def put(self, key: str, value: Any) -> None:
        self.conn.execute(
            "INSERT INTO kv(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, json.dumps(value, ensure_ascii=False, default=_json_default)),
        )
        self.conn.commit()

    def get(self, key: str, default: Any = None) -> Any:
        row = self.conn.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def keys(self) -> List[str]:
        return [r[0] for r in self.conn.execute("SELECT key FROM kv ORDER BY key")]

    # ---- veri çerçeveleri ------------------------------------------------------
    def put_frame(self, name: str, df: pd.DataFrame) -> None:
        """Set/dict/liste kolonları JSON'a, zaman kolonları ISO'ya çevrilerek saklanır."""
        cols = list(df.columns)
        rows: List[List[Any]] = []
        for rec in df.itertuples(index=False, name=None):
            rows.append([_encode(c, v) for c, v in zip(cols, rec)])
        self.conn.execute(
            "INSERT INTO frames(name, columns, rows) VALUES(?, ?, ?) ON CONFLICT(name) DO UPDATE SET columns=excluded.columns, rows=excluded.rows",
            (name, json.dumps(cols), json.dumps(rows, ensure_ascii=False, default=_json_default)),
        )
        self.conn.commit()

    def get_frame(self, name: str) -> Optional[pd.DataFrame]:
        row = self.conn.execute("SELECT columns, rows FROM frames WHERE name=?", (name,)).fetchone()
        if not row:
            return None
        cols, rows = json.loads(row[0]), json.loads(row[1])
        df = pd.DataFrame(rows, columns=cols)
        for c in cols:
            if c in ("day", "time", "first_ts", "last_ts") and len(df):
                df[c] = pd.to_datetime(df[c])
            elif c in FROZENSET_COLS and len(df):
                df[c] = df[c].apply(lambda v: frozenset(v) if isinstance(v, list) else frozenset())
        return df

    def frames(self) -> List[str]:
        return [r[0] for r in self.conn.execute("SELECT name FROM frames ORDER BY name")]

    # ---- su seviyesi -----------------------------------------------------------
    @property
    def watermark(self) -> Optional[pd.Timestamp]:
        v = self.get("watermark")
        return pd.Timestamp(v) if v else None

    def set_watermark(self, day: pd.Timestamp) -> None:
        self.put("watermark", str(pd.Timestamp(day).date()))

    def close(self) -> None:
        self.conn.close()


def _encode(col: str, v: Any) -> Any:
    if isinstance(v, (set, frozenset)):
        return sorted(v)
    if isinstance(v, pd.Timestamp):
        return None if pd.isna(v) else v.isoformat()
    if isinstance(v, float) and pd.isna(v):
        return None
    if hasattr(v, "item"):
        return v.item()
    return v


def frame_from_records(records: Iterable[dict], columns: Sequence[str]) -> pd.DataFrame:
    return pd.DataFrame(list(records), columns=list(columns))


def hits_to_records(hit_log: Dict[str, list]) -> List[dict]:
    out = []
    for sid, hits in hit_log.items():
        for h in hits:
            out.append(
                dict(
                    sid=sid,
                    rule_id=h.rule_id,
                    ad=h.ad,
                    katman=h.katman,
                    day=h.day.isoformat(),
                    severity=h.severity,
                    weight=h.weight,
                    attack=list(h.attack),
                    evidence=list(h.evidence),
                    sinyaller=h.sinyaller,
                    durum=h.durum,
                    aciklama=h.aciklama,
                    runbook=getattr(h, "runbook", ""),
                    kritik=bool(getattr(h, "kritik", False)),
                    kaynaklar=list(getattr(h, "kaynaklar", []) or []),
                )
            )
    return out


def hits_from_records(records: List[dict], hit_cls) -> Dict[str, list]:
    out: Dict[str, list] = {}
    for r in records:
        h = hit_cls(
            r["rule_id"],
            r["ad"],
            r["katman"],
            pd.Timestamp(r["day"]),
            float(r["severity"]),
            float(r["weight"]),
            list(r["attack"]),
            list(r["evidence"]),
            dict(r.get("sinyaller") or {}),
            r["durum"],
            r.get("aciklama", ""),
            r.get("runbook", ""),
            bool(r.get("kritik", False)),
            list(r.get("kaynaklar") or []),
        )
        out.setdefault(r["sid"], []).append(h)
    return out
