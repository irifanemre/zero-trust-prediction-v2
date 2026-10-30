"""7 günlük ufuk olasılığı: sezgisel başlangıç modeli, etiketten öğrenen lojistik model ve kalibrasyon ölçümü.

Doküman kısıtları:
- 14.5: denetimli model ancak yeterli etiket (200) biriktiğinde devreye alınır; 14.6: model skoru kural skorunu
  EZMEZ, ona eklenir; her çıktı özellik katkısıyla açıklanır; model sürümlenir ve geri alınabilir; modelsiz hâlin
  performansı kontrol grubu olarak ölçülmeye devam eder.
- 4.2: tahmin "kişinin niyeti" değil, 7 gün içinde doğrulanmış vakaya konu olma olasılığıdır.

Bu modül üç şey sağlar:
1. `HeuristicModel` — katsayıları elle verilmiş, açıklanabilir lojistik (kalibrasyon BAŞLANGIÇ değeri).
2. `LogisticModel` — aynı özellik vektörü üzerinde etiketten öğrenen, JSON olarak saklanabilen (pickle yok) model.
3. `calibration_report` — Brier, Brier beceri skoru, AUC ve güvenilirlik tablosu: "olasılık %30 dediğinde gerçekten
   %30 mu?" sorusunun ölçülebilir cevabı. Ölçülemeyen tahmin, tahmin değildir (1.3 ruhu).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from ztp.stats import sigmoid

# Özellik vektörü sırası sabittir (model sürümleriyle uyum için değiştirilmez; yeni özellik = yeni MODEL_VERSION)
PREDICTION_FEATURES: Tuple[str, ...] = (
    "risk_egim_7g",
    "rejim_degisim_skoru",
    "risk_ewma_kisa",
    "risk_ewma_uzun",
    "risk_pozitif_gun_7g",
    "mevcut_yuzdelik",
    "ayrilik_bildirimi",
    "yetki_var",
    "yeni_hesap",
    "usb_7g_toplam",
    "veri_hacmi_z",
    "hacim_trend_14g",
    "yeni_hassas_uygulama",
)
MODEL_VERSION = "pred-lr-1"


def feature_vector(ueba: dict, pred: dict, current_pct: float) -> Dict[str, float]:
    """Sinyal sözlüklerinden sabit sıralı, sonlu (NaN'sız) özellik vektörü."""

    def num(v, default=0.0):
        try:
            f = float(v)
        except (TypeError, ValueError):
            return default
        return f if math.isfinite(f) else default

    return {
        "risk_egim_7g": num(pred.get("risk_egim_7g")),
        "rejim_degisim_skoru": num(pred.get("rejim_degisim_skoru")),
        "risk_ewma_kisa": num(pred.get("risk_ewma_kisa")),
        "risk_ewma_uzun": num(pred.get("risk_ewma_uzun")),
        "risk_pozitif_gun_7g": num(pred.get("risk_pozitif_gun_7g")),
        "mevcut_yuzdelik": num(current_pct),
        "ayrilik_bildirimi": num(ueba.get("ayrilik_bildirimi")),
        "yetki_var": float(num(ueba.get("yetki_degisim_gun"), -1) >= 0),
        "yeni_hesap": float(num(ueba.get("hesap_yasi_gun"), 999) < 30),
        "usb_7g_toplam": num(ueba.get("usb_7g_toplam")),
        "veri_hacmi_z": max(-5.0, min(20.0, num(ueba.get("veri_hacmi_z")))),
        "hacim_trend_14g": max(-5.0, min(20.0, num(pred.get("hacim_trend_14g")))),
        "yeni_hassas_uygulama": num(ueba.get("yeni_hassas_uygulama")),
    }


class HeuristicModel:
    """Elle kalibre edilmiş başlangıç modeli. Katsayılar POC değeridir; etiketli veriyle ölçülür ve yerini öğrenen modele bırakır."""

    name = "sezgisel-v1"

    def predict(self, f: Dict[str, float]) -> Tuple[float, Dict[str, float]]:
        comp = {
            "yorunge": 1.5 * min(max(f["risk_egim_7g"], 0.0), 2.0),
            "rejim": 0.6 * min(max(f["rejim_degisim_skoru"], 0.0), 5.0),
            "mevcut_seviye": 3.0 * f["mevcut_yuzdelik"],
            "ayrilik": 0.7 * f["ayrilik_bildirimi"],
            "yetki": 0.5 * f["yetki_var"],
            "yeni_hesap": 0.4 * f["yeni_hesap"],
        }
        return sigmoid(-3.5 + sum(comp.values())), comp


@dataclass
class LogisticModel:
    """Standartlaştırılmış özellikler üzerinde lojistik regresyon; katsayılar JSON'da saklanır (pickle yok, denetlenebilir)."""

    coef: List[float]
    intercept: float
    mean: List[float]
    scale: List[float]
    n_train: int
    positives: int
    trained_at: str
    sinif_agirligi: bool = False  # eğitimde dengeleme uygulandı mı (kalibrasyon ↔ sıralama takası; denetim için kayıtlı)
    version: str = MODEL_VERSION
    features: Tuple[str, ...] = PREDICTION_FEATURES
    name: str = field(default="lojistik", init=False)

    @classmethod
    def fit(cls, X: np.ndarray, y: np.ndarray, C: float = 1.0, sinif_agirligi: bool = False) -> "LogisticModel":
        """`sinif_agirligi=False` (varsayılan): kalibre olasılık hedeflenir.

        Sınıf ağırlığı bir TAKASTIR, iyileştirme değil. Dengeleme azınlık sınıfının olasılıklarını taban oranının
        çok üstüne şişirir: Brier ve ECE bozulur, "olasılık %30 dediğinde gerçekten %30 mu?" sorusunun cevabı
        "hayır" olur. Buna karşılık SIRALAMA (AUPRC, recall@bütçe) iyileşebilir — ki 30'luk bütçede analistin
        gördüğü şey sıradır, mutlak olasılık değil.

        Bu yüzden anahtar var ama varsayılanda kapalı ve ikisi birlikte raporlanır: aynı modelin kalibrasyonu ve
        sıralaması ayrı ayrı ölçülmeden hangisinin tercih edileceğine karar verilemez (14.5).
        """
        from sklearn.linear_model import LogisticRegression

        X = np.asarray(X, dtype=float)
        y = np.asarray(y, dtype=int)
        if X.ndim != 2 or X.shape[1] != len(PREDICTION_FEATURES):
            raise ValueError("özellik boyutu uyumsuz")
        if y.sum() < 5 or (len(y) - y.sum()) < 5:
            raise ValueError("eğitim için her sınıftan en az 5 örnek gerekir")
        mean, scale = X.mean(axis=0), X.std(axis=0)
        scale[scale == 0] = 1.0
        lr = LogisticRegression(C=C, max_iter=2000, class_weight=("balanced" if sinif_agirligi else None))
        lr.fit((X - mean) / scale, y)
        return cls(
            coef=[float(c) for c in lr.coef_[0]],
            intercept=float(lr.intercept_[0]),
            mean=[float(m) for m in mean],
            scale=[float(s) for s in scale],
            n_train=int(len(y)),
            positives=int(y.sum()),
            trained_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            sinif_agirligi=bool(sinif_agirligi),
        )

    def _z(self, f: Dict[str, float]) -> np.ndarray:
        x = np.array([f.get(k, 0.0) for k in self.features], dtype=float)
        return (x - np.array(self.mean)) / np.array(self.scale)

    def predict(self, f: Dict[str, float]) -> Tuple[float, Dict[str, float]]:
        """Olasılık ve özellik katkıları (katsayı × standartlaştırılmış değer): 'hangi özellik ne kadar katkı verdi' (14.6)."""
        z = self._z(f)
        contrib = {k: float(c * v) for k, c, v in zip(self.features, self.coef, z)}
        p = sigmoid(self.intercept + sum(contrib.values()))
        top = dict(sorted(contrib.items(), key=lambda kv: -abs(kv[1]))[:5])
        return p, top

    def predict_many(self, X: np.ndarray) -> np.ndarray:
        Z = (np.asarray(X, dtype=float) - np.array(self.mean)) / np.array(self.scale)
        return 1.0 / (1.0 + np.exp(-(self.intercept + Z @ np.array(self.coef))))

    def to_dict(self) -> dict:
        return dict(
            version=self.version,
            features=list(self.features),
            coef=self.coef,
            intercept=self.intercept,
            mean=self.mean,
            scale=self.scale,
            n_train=self.n_train,
            positives=self.positives,
            trained_at=self.trained_at,
            sinif_agirligi=self.sinif_agirligi,
        )

    @classmethod
    def from_dict(cls, d: dict) -> "LogisticModel":
        if d.get("version") != MODEL_VERSION or tuple(d.get("features", ())) != PREDICTION_FEATURES:
            raise ValueError(f"Model sürümü/özellik kümesi uyumsuz: {d.get('version')} (beklenen {MODEL_VERSION})")
        return cls(
            coef=list(d["coef"]),
            intercept=float(d["intercept"]),
            mean=list(d["mean"]),
            scale=list(d["scale"]),
            n_train=int(d["n_train"]),
            positives=int(d["positives"]),
            trained_at=str(d["trained_at"]),
            sinif_agirligi=bool(d.get("sinif_agirligi", False)),  # eski modellerde alan yok → dengeleme yok
        )


def rows_to_matrix(rows: Sequence[dict]) -> np.ndarray:
    return np.array([[float(r["ozellikler"].get(k, 0.0)) for k in PREDICTION_FEATURES] for r in rows], dtype=float)


def auc_score(p: np.ndarray, y: np.ndarray) -> Optional[float]:
    """Sıra tabanlı AUC (Mann–Whitney); tek sınıf varsa None."""
    p, y = np.asarray(p, dtype=float), np.asarray(y, dtype=int)
    pos, neg = p[y == 1], p[y == 0]
    if len(pos) == 0 or len(neg) == 0:
        return None
    order = np.argsort(np.concatenate([pos, neg]))
    ranks = np.empty(len(order), dtype=float)
    ranks[order] = np.arange(1, len(order) + 1)
    # bağlı değerler için ortalama sıra
    allp = np.concatenate([pos, neg])
    for v in np.unique(allp):
        idx = np.where(allp == v)[0]
        if len(idx) > 1:
            ranks[idx] = ranks[idx].mean()
    r_pos = ranks[: len(pos)].sum()
    return float((r_pos - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def auprc_score(p: np.ndarray, y: np.ndarray) -> Optional[float]:
    """Precision–Recall eğrisinin altındaki alan (ortalama kesinlik).

    Neden AUC yerine bu: AUROC paydasında NEGATİF sayısı var. 2801 kullanıcıda 1 insider varken (1:2800) negatif
    sınıf her şeyi domine eder ve AUROC yüksek görünür — r6.2'de 0,775 çıktı, oysa precision@1 0,003'tü. AUPRC'nin
    tabanı pozitif sınıfın oranıdır (burada 0,0001), yani "şans seviyesi" baştan görünür ve bir modelin gerçekten
    şansın üstünde olup olmadığı okunabilir. Dengesiz veride literatürün önerdiği ölçüt budur.

    Hesap, adım fonksiyonuna sağdan toplamla yapılır (sklearn'ün `average_precision_score`'u ile aynı tanım):
        AP = Σ_k (R_k − R_{k−1}) · P_k
    Bağlı skorlar tek eşik gibi işlenir; aksi hâlde sıralama rastgele kopar ve değer yapay şişer.
    """
    p, y = np.asarray(p, dtype=float), np.asarray(y, dtype=int)
    if len(p) == 0 or y.sum() == 0 or y.sum() == len(y):
        return None
    sira = np.argsort(-p, kind="stable")
    ys, ps = y[sira], p[sira]
    tp = np.cumsum(ys)
    fp = np.cumsum(1 - ys)
    # bağlı skor grubunun yalnız SON indeksi bir eşiktir (grubun ortasında kesmek tanımsızdır)
    son = np.r_[ps[1:] != ps[:-1], True]
    tp, fp = tp[son], fp[son]
    precision = tp / np.maximum(tp + fp, 1)
    recall = tp / y.sum()
    return float(np.sum(np.diff(np.r_[0.0, recall]) * precision))


def calibration_report(p: Sequence[float], y: Sequence[int], bins: int = 10) -> dict:
    """Brier skoru, Brier beceri skoru (taban oranına göre), AUC ve güvenilirlik tablosu."""
    p, y = np.asarray(p, dtype=float), np.asarray(y, dtype=int)
    n = len(p)
    if n == 0:
        return dict(n=0)
    base = float(y.mean())
    brier = float(np.mean((p - y) ** 2))
    brier_base = float(np.mean((base - y) ** 2)) if 0 < base < 1 else None
    edges = np.linspace(0, 1, bins + 1)
    table = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (p >= lo) & ((p < hi) if hi < 1 else (p <= hi))
        if m.any():
            table.append(
                dict(
                    aralik=f"{lo:.1f}–{hi:.1f}",
                    n=int(m.sum()),
                    ort_tahmin=round(float(p[m].mean()), 3),
                    gozlenen=round(float(y[m].mean()), 3),
                )
            )
    ece = float(sum(r["n"] * abs(r["ort_tahmin"] - r["gozlenen"]) for r in table) / n)
    return dict(
        n=n,
        pozitif=int(y.sum()),
        taban_orani=round(base, 4),
        brier=round(brier, 4),
        brier_taban=round(brier_base, 4) if brier_base is not None else None,
        brier_beceri=round(1 - brier / brier_base, 3) if brier_base else None,
        auc=round(auc_score(p, y), 3) if auc_score(p, y) is not None else None,
        # AUPRC ve tabanı YAN YANA: tek başına AUPRC de yorumlanamaz, taban oranına göre okunur (1.3)
        auprc=round(ap, 4) if (ap := auprc_score(p, y)) is not None else None,
        auprc_taban=round(base, 4) if 0 < base < 1 else None,
        auprc_kat=(round(ap / base, 1) if ap is not None and 0 < base < 1 else None),
        ece=round(ece, 4),
        guvenilirlik=table,
    )
