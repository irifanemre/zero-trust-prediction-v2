"""CERT sürüm biçimleri: r5+'da file.csv her dosya işlemini, email.csv her etkinliği içerir. r4.2 anlamı korunur — yalnız
taşınabilir medyaya kopya ve yalnız gönderim sayılır. Bozuk tarihli cevap anahtarı satırı yükleyiciyi çökertmez."""

import logging

import pandas as pd

from ztp.data.cert import load_cert_dataset

LDAP = "employee_name,user_id,email,role,business_unit,functional_unit,department,team,supervisor\n"
USERS = ["AAA0001", "BBB0002"]
T = "01/05/2010 10:00:00"


def _write(d, name, text):
    (d / name).write_text(text, encoding="utf-8")


def _release(tmp_path, name, r5: bool):
    d = tmp_path / name
    (d / "LDAP").mkdir(parents=True)
    rows = "".join(f"User {u},{u},{u.lower()}@dtaa.com,Engineer,1,1,Dept,Team,Boss\n" for u in USERS)
    _write(d / "LDAP", "2010-01.csv", LDAP + rows)
    _write(
        d, "logon.csv", "id,date,user,pc,activity\n" + "".join(f"{{L{i}}},{T},{u},PC-{i},Logon\n" for i, u in enumerate(USERS))
    )
    if r5:
        _write(d, "device.csv", f"id,date,user,pc,file_tree,activity\n{{D1}},{T},AAA0001,PC-0,R:\\,Connect\n")
        _write(d, "http.csv", f"id,date,user,pc,url,content\n{{H1}},{T},AAA0001,PC-0,http://example.com/a,x y\n")
        _write(
            d,
            "email.csv",
            "id,date,user,pc,to,cc,bcc,from,activity,size,attachments,content\n"
            f"{{E1}},{T},AAA0001,PC-0,x@ext.com,,,a@dtaa.com,Send,1000,,c\n"
            f"{{E2}},{T},AAA0001,PC-0,a@dtaa.com,,,x@ext.com,View,9999,,c\n",
        )
        _write(
            d,
            "file.csv",
            "id,date,user,pc,filename,activity,to_removable_media,from_removable_media,content\n"
            f"{{F1}},{T},AAA0001,PC-0,R:\\a.doc,File Copy,True,False,D0-CF abc\n"
            f"{{F2}},{T},AAA0001,PC-0,C:\\b.doc,File Open,False,False,D0-CF abcdef\n"
            f"{{F3}},{T},AAA0001,PC-0,C:\\c.doc,File Write,False,True,D0-CF abcdefgh\n",
        )
    else:
        _write(d, "device.csv", f"id,date,user,pc,activity\n{{D1}},{T},AAA0001,PC-0,Connect\n")
        _write(d, "http.csv", f"id,date,user,pc,url,content\n{{H1}},{T},AAA0001,PC-0,http://example.com/a,x y\n")
        _write(
            d,
            "email.csv",
            f"id,date,user,pc,to,cc,bcc,from,size,attachments,content\n{{E1}},{T},AAA0001,PC-0,x@ext.com,,,a@dtaa.com,1000,0,c\n",
        )
        _write(d, "file.csv", f"id,date,user,pc,filename,content\n{{F1}},{T},AAA0001,PC-0,a.doc,D0-CF abc\n")
    return d


def _load(d, answers=None):
    return load_cert_dataset(str(d), pd.Timestamp("2010-01-01"), pd.Timestamp("2010-01-10"), answers_dir=answers)


def test_r5_counts_only_removable_copies_and_sent_mail(tmp_path):
    ev = _load(_release(tmp_path, "r5.2", r5=True)).events
    assert list(ev.loc[ev.source == "file_server", "event_id"]) == ["{F1}"]
    assert list(ev.loc[ev.source == "email", "event_id"]) == ["{E1}"]
    assert ev.loc[ev.source == "email", "bytes_out"].tolist() == [1000]
    assert (ev.source == "dlp").sum() == 1  # file_tree alanı yok sayılır, connect okunur


def test_r42_format_unchanged(tmp_path):
    ev = _load(_release(tmp_path, "r4.2", r5=False)).events
    assert list(ev.loc[ev.source == "file_server", "event_id"]) == ["{F1}"]
    assert list(ev.loc[ev.source == "email", "event_id"]) == ["{E1}"]


def test_malformed_answer_date_is_logged_not_fatal(tmp_path, caplog):
    d = _release(tmp_path, "r5.2", r5=True)
    ans = tmp_path / "answers"
    ans.mkdir()
    _write(
        ans,
        "insiders.csv",
        "dataset,scenario,details,user,start,end\n"
        "5.2,1,x.csv,AAA0001,01/05/2010 09:00:00,01/06/2010 09:00:00\n"
        "5.2,4,y.csv,BBB0002,/21/2010 11:43:39,01/07/2010 17:55:00\n",
    )
    with caplog.at_level(logging.WARNING, logger="ztp.data.cert"):
        data = _load(d, str(ans))
    assert [g["sid"] for g in data.ground_truth] == ["AAA0001"]
    assert "BBB0002" in caplog.text and "değerlendirilemedi" in caplog.text


def test_only_users_restricts_directory_answers_and_events(tmp_path):
    d = _release(tmp_path, "r5.2", r5=True)
    ans = tmp_path / "answers"
    ans.mkdir()
    _write(
        ans,
        "insiders.csv",
        "dataset,scenario,details,user,start,end\n"
        "5.2,1,x.csv,AAA0001,01/05/2010 09:00:00,01/06/2010 09:00:00\n"
        "5.2,2,y.csv,BBB0002,01/05/2010 09:00:00,01/06/2010 09:00:00\n",
    )
    data = load_cert_dataset(
        str(d), pd.Timestamp("2010-01-01"), pd.Timestamp("2010-01-10"), answers_dir=str(ans), only_users=["BBB0002"]
    )
    assert data.directory["sid"].tolist() == ["BBB0002"]
    assert [g["sid"] for g in data.ground_truth] == ["BBB0002"]
    assert set(data.events["actor_raw"]) == {"BBB0002"}
