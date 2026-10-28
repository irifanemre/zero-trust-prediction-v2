"""Aldatma katmanı — honeytoken (tuzak hesap / tuzak kaynak / tuzak cihaz) etkileşimi.

Tuzak varlıkların meşru bir kullanımı yoktur; onlarla her etkileşim deterministik ve yüksek güvenilirlikli bir sinyaldir.
Bu katman istatistiksel katmanların tersine çalışır: baseline yok, akran kıyası yok, öğrenilen eşik yok, jitter yok.

- 13.5 "tek sinyal uyarı üretmez" ilkesinin AÇIK istisnasıdır: tek etkileşim kritik vaka üretir ve alarm bütçesinden
  bağımsız kuyruğa girer (kural tanımında `kritik: true`).
- Tuzak HESABIN kullanımı hesabın kendisine değil, kullanımın geldiği yere yazılır: cihaz sahibi → IP kiralaması →
  (ikisi de yoksa) tuzak hesabın kendi kimliği. Hiçbiri çözümlenemezse etkileşim "atfedilemeyen" kuyruğuna düşer;
  sessizce kaybolmaz (17.5).
- Tuzak listesi müşteri yapılandırmasıdır (`honeytokens:` — 17.1); kaynak adları fnmatch kalıbı olabilir.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from typing import FrozenSet, Iterable, Mapping, Optional, Tuple

import pandas as pd

TOKEN_COLUMN = "honeytoken"
KIND_ACCOUNT, KIND_RESOURCE, KIND_DEVICE = "hesap", "kaynak", "cihaz"
UNATTRIBUTED_COLUMNS = ["event_id", "time", "source", "actor_raw", "device", "src_ip", "token", "neden"]
# Yapılandırma alanı → tespit kategorisi. "gizli_dizgiler" (sahte API anahtarı, SSH key, cloud secret, DB parolası)
# AYRI bir kategori değildir: KIND_RESOURCE'a eşlenir, böylece aşağı akıştaki sinyal adları (tuzak_kaynak_sayisi) ve
# donmuş profil/özellik kodu değişmez — yalnız nerede arandığı değişir (komut satırı ve kaynak yolu metni).
_CONFIG_KEYS = {
    "hesaplar": KIND_ACCOUNT,
    "kaynaklar": KIND_RESOURCE,
    "cihazlar": KIND_DEVICE,
    "gizli_dizgiler": KIND_RESOURCE,
}
SECRET_FIELDS = ("cmdline", "resource", "process", "app")  # OCSF-lite'ta gizli dizginin görünebileceği metin alanları


@dataclass(frozen=True)
class HoneytokenRegistry:
    accounts: FrozenSet[str]  # aktör adı (küçük harf): tuzak AD hesabı, servis hesabı, ayrıcalıklı tuzak hesap
    resources: Tuple[str, ...]  # dosya/paylaşım yolu kalıpları (fnmatch, küçük harf)
    devices: FrozenSet[str]  # tuzak sunucu / host adları (küçük harf)
    secrets: FrozenSet[str] = frozenset()  # sahte API anahtarı / SSH key / cloud secret / DB parolası (tam dizgi)

    @classmethod
    def from_config(cls, spec: Optional[Mapping]) -> "HoneytokenRegistry":
        spec = dict(spec or {})
        unknown = set(spec) - set(_CONFIG_KEYS)
        if unknown:
            raise ValueError(f"honeytokens: bilinmeyen alan {sorted(unknown)} (beklenen: {sorted(_CONFIG_KEYS)})")
        vals = {}
        for key in _CONFIG_KEYS:
            items = spec.get(key) or []
            if not isinstance(items, (list, tuple)) or not all(isinstance(x, str) and x.strip() for x in items):
                raise ValueError(f"honeytokens.{key}: boş olmayan metin listesi olmalı")
            vals[key] = tuple(x.strip().lower() for x in items)
        return cls(
            frozenset(vals["hesaplar"]),
            vals["kaynaklar"],
            frozenset(vals["cihazlar"]),
            frozenset(vals["gizli_dizgiler"]),
        )

    @classmethod
    def empty(cls) -> "HoneytokenRegistry":
        return cls(frozenset(), (), frozenset())

    def __bool__(self) -> bool:
        return bool(self.accounts or self.resources or self.devices or self.secrets)

    def __len__(self) -> int:
        return len(self.accounts) + len(self.resources) + len(self.devices) + len(self.secrets)

    # ---- eşleştirme ----------------------------------------------------------
    def tag(self, ev: pd.DataFrame) -> pd.Series:
        """Her olay için etiket: 'hesap:<aktör>' | 'cihaz:<host>' | 'kaynak:<yol>' | None. Öncelik hesap > cihaz > kaynak."""
        out = pd.Series([None] * len(ev), index=ev.index, dtype=object)
        if not self or ev.empty:
            return out
        if self.resources:
            regex = "|".join(f"(?:{fnmatch.translate(p)})" for p in self.resources)
            res = ev["resource"].astype("string").str.lower()
            m = res.str.fullmatch(regex).fillna(False).astype(bool)
            out[m] = KIND_RESOURCE + ":" + ev.loc[m, "resource"].astype(str)
        if self.secrets:
            # Gizli dizgi, kendisini taşıyan metnin İÇİNDE geçer (komut satırı, dosya yolu, süreç adı, uygulama).
            # Tam eşleşme değil, içerme araması: `curl -H "Authorization: Bearer <sahte>"` gibi kullanımlar yakalanır.
            for field in SECRET_FIELDS:
                if field not in ev.columns:
                    continue
                txt = ev[field].astype("string").str.lower()
                for secret in self.secrets:
                    m = txt.str.contains(secret, regex=False, na=False).to_numpy(dtype=bool)
                    if m.any():
                        out[m] = KIND_RESOURCE + ":gizli:" + secret
        if self.devices:
            dev = ev["device"].astype("string").str.lower()
            m = dev.isin(self.devices).fillna(False).astype(bool)
            out[m] = KIND_DEVICE + ":" + ev.loc[m, "device"].astype(str)
        if self.accounts:
            act = ev["actor_raw"].astype("string").str.lower()
            m = act.isin(self.accounts).fillna(False).astype(bool)
            out[m] = KIND_ACCOUNT + ":" + ev.loc[m, "actor_raw"].astype(str)
        return out

    def apply(
        self,
        ev: pd.DataFrame,
        owner_of_device: Mapping[str, str],
        leases: pd.DataFrame,
        service_sids: Iterable[str],
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """Olayları etiketler ve tuzak hesap kullanımını kaynağına atfeder. Döndürür: (olaylar, atfedilemeyen kuyruğu).

        Kimlik çözümlemesinden (`IdentityResolver.resolve`) SONRA çağrılır; `canonical` ve `is_service` kolonlarını bekler."""
        ev = ev.copy()
        ev[TOKEN_COLUMN] = self.tag(ev)
        if not self or ev.empty:
            return ev, pd.DataFrame(columns=UNATTRIBUTED_COLUMNS)
        service = set(service_sids)
        acct = ev[TOKEN_COLUMN].astype("string").str.startswith(KIND_ACCOUNT + ":").fillna(False).astype(bool)
        if acct.any():
            sub = ev.loc[acct]
            owner = sub["device"].map(owner_of_device)
            # cihaz sahibi yoksa IP kiralaması (zaman aralıklı — 8.2), o da yoksa tuzak hesabın kendi kimliği
            lease_sid = _lease_lookup(sub, leases)
            attributed = owner.where(owner.notna(), lease_sid).where(lambda s: s.notna(), sub["canonical"])
            # eksik kimlik her pandas sürümünde None kalsın (NaN değil): aşağı akış `notna()` ve eşitlik kontrolleri tutarlı
            ev.loc[acct, "canonical"] = pd.Series(
                [v if isinstance(v, str) else None for v in attributed], index=sub.index, dtype=object
            )
            ev.loc[acct, "is_service"] = ev.loc[acct, "canonical"].isin(service)
        tagged = ev[TOKEN_COLUMN].notna()
        lost = tagged & (ev["canonical"].isna() | ev["is_service"].astype(bool))
        queue = pd.DataFrame(columns=UNATTRIBUTED_COLUMNS)
        if lost.any():
            q = ev.loc[lost, ["event_id", "time", "source", "actor_raw", "device", "src_ip", TOKEN_COLUMN]].copy()
            q["neden"] = ["servis hesabı" if s else "kimlik çözümlenemedi" for s in ev.loc[lost, "is_service"].astype(bool)]
            queue = q.rename(columns={TOKEN_COLUMN: "token"})[UNATTRIBUTED_COLUMNS]
        return ev, queue


def _lease_lookup(sub: pd.DataFrame, leases: pd.DataFrame) -> pd.Series:
    """Olayın kaynak IP'si o anda kime kiralıysa onun kimliği; yoksa NaN (IdentityResolver.resolve ile aynı kural)."""
    out = pd.Series([None] * len(sub), index=sub.index, dtype=object)
    if leases is None or leases.empty or sub["src_ip"].isna().all():
        return out
    px = sub[["event_id", "src_ip", "time"]].merge(leases, left_on="src_ip", right_on="ip", how="inner")
    px = px[(px["time"] >= px["start"]) & (px["time"] < px["end"])].drop_duplicates("event_id")
    if px.empty:
        return out
    hit = sub["event_id"].map(px.set_index("event_id")["sid"])
    return hit.where(hit.notna(), None)
