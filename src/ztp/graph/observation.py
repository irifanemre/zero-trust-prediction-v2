"""Gözlem grafı oluşturma (düşük maliyet, tüm kullanıcılar, müşteri bazında izole) — 11.3, Prensip 2."""

from __future__ import annotations

from typing import Sequence

import pandas as pd

from ztp.graph.store import NetworkXGraphStore


class ObservationGraphBuilder:
    """11.3 Graf oluşturma (düşük maliyet): log akışından kullanıcı–cihaz–kaynak–uygulama–konum kenarları, gün bazında toplanarak."""

    def __init__(self, store: NetworkXGraphStore, critical_assets: Sequence[str]):
        self.store = store
        self.critical = set(critical_assets)
        for a in self.critical:
            self.store.g.add_node(f"resource:{a}", ntype="resource", critical=True)

    def ingest_day(self, ev_day: pd.DataFrame) -> int:
        ev = ev_day[ev_day["canonical"].notna()]
        n = 0
        specs = [
            ("device", "kullandi", "device"),
            ("resource", "eristi", "resource"),
            ("app", "kullandi", "app"),
            ("country", "baglandi", "geo"),
            ("src_ip", "baglandi", "ip"),
        ]
        for col, etype, ntype in specs:
            sub = ev[ev[col].notna()]
            if sub.empty:
                continue
            # observed=True: anahtar kategorik olduğunda (resource/app/country/src_ip) o gün görülmeyen kategoriler
            # için hayalet kenar üretilmesini önler; nesne dtype'ıyla birebir aynı sonucu verir.
            agg = sub.groupby(["canonical", col], observed=True).agg(
                count=("event_id", "size"), first_ts=("time", "min"), last_ts=("time", "max")
            )
            for (sid, val), r in agg.iterrows():
                self.store.add_edge(f"user:{sid}", f"{ntype}:{val}", etype, r["first_ts"], count=int(r["count"]))
                self.store.g[f"user:{sid}"][f"{ntype}:{val}"]["rel"][etype]["last_ts"] = r["last_ts"]
                n += 1
        # cihaz → süreç (LOLBins: süreç adı değil ebeveyn-çocuk ilişkisi izlenir, 2.3)
        edr = ev[(ev["source"] == "edr") & ev["process"].notna()]
        if not edr.empty:
            agg = edr.groupby(["device", "process", "parent_process"], observed=True).agg(
                count=("event_id", "size"), first_ts=("time", "min")
            )
            for (dev, proc, parent), r in agg.iterrows():
                self.store.add_edge(
                    f"device:{dev}", f"process:{parent}>{proc}", "calistirdi", r["first_ts"], count=int(r["count"])
                )
                n += 1
        return n
