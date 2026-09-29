"""Komut satırı arayüzü: sentetik/CERT koşuları, kural testleri, analist etiketi."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Optional, Sequence

import pandas as pd

from ztp.ablation import format_ablation, run_ablation
from ztp.config import TenantConfig
from ztp.data.cert import CERT_PATH_ENV, load_cert_dataset, resolve_cert_dir
from ztp.data.files import dataset_from_files
from ztp.data.synthetic import SyntheticOrg
from ztp.detection.catalog import load_catalog
from ztp.detection.testing import run_rule_tests
from ztp.feedback import FP_REASONS, LabelStore
from ztp.pipeline import ZeroTrustPredictionPipeline
from ztp.response import authorize_containment
from ztp.schema import DAY
from ztp.state import StateStore

LOG = logging.getLogger(__name__)


def cmd_label(args) -> None:
    out = Path(args.out) / args.tenant
    store = LabelStore(out / "labels.json")
    p = out / "cases" / f"{args.label}.json"
    if not p.exists():
        sys.exit(f"Vaka bulunamadı: {p}")
    case = json.loads(p.read_text(encoding="utf-8"))
    vault = (
        json.loads((out / "identity_vault.RESTRICTED.json").read_text(encoding="utf-8"))
        if (out / "identity_vault.RESTRICTED.json").exists()
        else {}
    )
    case["_sid"] = vault.get(case["kullanici"], {}).get("sid")
    rec = store.add(case, args.decision, args.analyst, args.reason, args.note or "")
    print("Etiket kaydedildi:", json.dumps(rec, ensure_ascii=False, indent=2))
    ok, msg = authorize_containment(case, rec)
    print("Müdahale yetkisi:", msg)
    print("Geri besleme metrikleri:", json.dumps(store.metrics(), ensure_ascii=False, indent=2))


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Zero Trust Prediction — mimari doğrulama (MVP) script'i")
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--synthetic", action="store_true", help="sentetik kurum + enjekte senaryolar (kör test/regresyon)")
    src.add_argument(
        "--cert-dir",
        nargs="?",
        const="",
        help=f"CERT sürüm dizini (ör. C:/data/cert_r4.2/r4.2); değersiz verilirse {CERT_PATH_ENV} ortam değişkeni okunur",
    )
    ap.add_argument("--answers-dir", help="CERT cevap anahtarı dizini (varsayılan: <cert-dir>/../answers)")
    # günlük servis modu: durum deposundan devam eder, yalnızca verilen günün olaylarını işler
    ap.add_argument("--daily", metavar="YYYY-MM-DD", help="artımlı gün işleme (durum deposu gerekir)")
    ap.add_argument("--events", help="OCSF-lite olay dosyası (csv/parquet) — --daily ile")
    ap.add_argument("--directory", help="İK/AD dizin dosyası (csv/parquet) — --daily ile")
    ap.add_argument("--leases", help="IP kiralama dosyası (ip,sid,start,end)")
    ap.add_argument("--leaves", help="izin takvimi dosyası (sid,start,end,tur)")
    ap.add_argument("--state", action="store_true", help="toplu koşu sonunda durumu kaydet (günlük moda geçiş için)")
    ap.add_argument("--force", action="store_true", help="su seviyesi geçilmiş günü yeniden işle")
    ap.add_argument(
        "--train-prediction", action="store_true", help="koşu sonunda 7g olasılık modelini eğit (zamansal holdout ile raporla)"
    )
    ap.add_argument(
        "--ablation", action="store_true", help="19.5 ablasyon: bileşenleri tek tek kapatıp kapsama/precision farkını ölç"
    )
    ap.add_argument("--config", help="müşteri yapılandırma dosyası (YAML); komut satırı değerleri dosyayı ezer")
    ap.add_argument("--tenant", default="musteri-A")
    ap.add_argument("--users", type=int, default=150)
    ap.add_argument("--days", type=int, default=30, help="değerlendirme penceresi (gün)")
    ap.add_argument("--warmup", type=int, default=21, help="risk serisi ısınma günü (vaka üretilmez)")
    ap.add_argument("--budget", type=int, default=8, help="alarm bütçesi N = analist kapasitesi (13.5)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument(
        "--honeytokens",
        action="store_true",
        help="sentetik veriye tuzak varlıklar + S10 tuzak etkileşimi senaryosu ekle (aldatma katmanı)",
    )
    ap.add_argument("--end", help="değerlendirme son günü (YYYY-MM-DD); varsayılan bugün")
    ap.add_argument("--out", default="./ztp_out")
    ap.add_argument("--detections-dir", help="detection-as-code YAML dizini (yoksa gömülü katalog)")
    ap.add_argument("--llm", default="none", choices=["none", "ollama", "anthropic"])
    ap.add_argument("--ollama-model", default="llama3.1")
    ap.add_argument("--test-rules", action="store_true", help="kural birim testlerini çalıştır ve çık")
    ap.add_argument("--label", help="vaka kimliği — analist kararı yaz")
    ap.add_argument("--decision", choices=["gercek_pozitif", "yanlis_pozitif", "belirsiz"])
    ap.add_argument("--reason", choices=sorted(FP_REASONS))
    ap.add_argument("--analyst", default="analist")
    ap.add_argument("--note")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    args.users_given = any(a.startswith("--users") for a in (argv if argv is not None else sys.argv[1:]))
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    catalog = load_catalog(args.detections_dir)
    if args.test_rules:
        print("Detection-as-code birim testleri (19.1 Katman 1):")
        return 0 if run_rule_tests(catalog) else 1
    if args.label:
        if not args.decision:
            sys.exit("--decision zorunlu")
        cmd_label(args)
        return 0
    if args.daily:
        return cmd_daily(args, catalog)
    if not args.synthetic and args.cert_dir is None and not (args.events and args.directory):
        args.synthetic = True
        LOG.info("Kaynak belirtilmedi; sentetik veri kullanılıyor")

    end = pd.Timestamp(args.end).normalize() if args.end else pd.Timestamp.utcnow().tz_localize(None).normalize()
    overrides = dict(
        tenant_id=args.tenant, alarm_budget_per_day=args.budget, llm_backend=args.llm, ollama_model=args.ollama_model
    )
    cfg = TenantConfig.from_yaml(args.config, **overrides) if args.config else TenantConfig(**overrides)
    if args.synthetic:
        n_days = cfg.long_window_days + args.warmup + args.days
        data = SyntheticOrg(
            n_users=args.users, n_days=n_days, eval_days=args.days, end_day=end, seed=args.seed, honeytokens=args.honeytokens
        ).build()
    elif args.events and args.directory:  # toplu ısınma dosyalardan (günlük moda geçiş öncesi): --state ile durum kaydedilir
        if not args.end:
            sys.exit("Dosya girişinde --end zorunludur")
        data = dataset_from_files(args.events, args.directory, args.leases, args.leaves, cfg.critical_assets)
        cfg.available_sources = tuple(sorted(set(data.events["source"].unique()) | {"hr"}))
    else:
        if not args.end:
            sys.exit("CERT için --end (veri aralığı içinde bir gün, ör. 2010-11-30) zorunludur")
        start_hist = end - (cfg.long_window_days + args.warmup + args.days) * DAY
        cert_dir = resolve_cert_dir(args.cert_dir or None)
        answers = args.answers_dir or str(cert_dir.parent / "answers")
        data = load_cert_dataset(
            str(cert_dir), start_hist, end, max_users=(args.users if args.users_given else None), answers_dir=answers
        )
        # 11.1 kademeli işlevsellik: yalnızca mevcut kaynaklar (CERT'te EDR/VPN yok; r1'de e-posta/dosya da yok)
        cfg.available_sources = tuple(sorted(set(data.events["source"].unique()) | {"hr"}))
        LOG.info("Mevcut kaynaklar: %s", cfg.available_sources)
    start = end - (args.days - 1) * DAY
    if args.ablation:
        table = run_ablation(cfg, data, catalog, Path(args.out), start, end, args.warmup)
        print(format_ablation(table))
        return 0
    state = StateStore(Path(args.out) / cfg.tenant_id / cfg.state_file) if args.state else None
    pipe = ZeroTrustPredictionPipeline(cfg, data, catalog, Path(args.out), state=state)
    pipe.run(start, end, args.warmup)
    if args.train_prediction:
        rep = pipe.train_prediction_model()
        if rep.get("egitildi"):
            ho, hs, h = rep.get("holdout_model") or {}, rep.get("holdout_sezgisel") or {}, rep.get("holdout", {})
            print(
                f"Tahmin modeli eğitildi ({rep['kaynak']}, n={rep['model']['n_train']}, pozitif={rep['model']['positives']}). "
                f"Holdout ({h.get('gun')} gün, {h.get('satir')} satır, {h.get('pozitif')} pozitif) — "
                f"Brier: model {ho.get('brier')} vs sezgisel {hs.get('brier')} (taban {ho.get('brier_taban')}) | "
                f"AUC: model {ho.get('auc')} vs sezgisel {hs.get('auc')} | ECE: model {ho.get('ece')} vs sezgisel {hs.get('ece')}"
                + ("  ⚠ holdout'ta pozitif yok: kalibrasyon ölçülemedi" if not h.get("pozitif") else "")
            )
            print("Katsayılar:", rep["katsayilar"])
        else:
            print(f"Tahmin modeli eğitilmedi: {rep.get('neden')}")
    return 0


def cmd_daily(args, catalog) -> int:
    """Günlük servis: `ztp --daily 2026-09-17 --events gun.parquet --directory dizin.csv --config musteri.yaml --out ./ztp_out`.
    Su seviyesi aşılmamış günler sırayla işlenir; aynı gün ikinci kez `--force` olmadan işlenmez (idempotent)."""
    if not args.directory:
        sys.exit("--daily için --directory zorunludur")
    overrides = dict(
        tenant_id=args.tenant, alarm_budget_per_day=args.budget, llm_backend=args.llm, ollama_model=args.ollama_model
    )
    cfg = TenantConfig.from_yaml(args.config, **overrides) if args.config else TenantConfig(**overrides)
    data = dataset_from_files(args.events, args.directory, args.leases, args.leaves, cfg.critical_assets)
    state = StateStore(Path(args.out) / cfg.tenant_id / cfg.state_file)
    day = pd.Timestamp(args.daily).normalize()
    events = data.events
    if len(events):
        events = events[events["time"].dt.normalize() == day]
        if events.empty:
            LOG.warning("%s için olay yok — gün yine de işlenir (uyarı hacmi düşüşü sağlık metriğine yansır)", day.date())
    pipe = ZeroTrustPredictionPipeline(cfg, data, catalog, Path(args.out), state=state)
    try:
        cases = pipe.run_incremental(day, events, force=args.force)
    except ValueError as exc:  # idempotentlik: su seviyesi geçilmiş gün
        print(str(exc), file=sys.stderr)
        return 2
    print(f"{day.date()}: {len(cases)} vaka, su seviyesi → {state.watermark.date()}, durum: {state.path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
