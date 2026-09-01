# -*- coding: utf-8 -*-
# 字幕 → 逐字稿。把偵察時抓到的 .vtt/.srt 正規化成 transcribe.py 一模一樣的輸出，
# 讓「字幕優先」路徑可以完全跳過下載音訊＋whisper，下游做筆記那步不用改。
# 用法：
#   python subclean.py <subs_dir> <transcript_dir>          （Mac/Linux 用 python3）
# 產出（與 transcribe.py 同名同格式，所以兩條路徑可以混用）：
#   <transcript_dir>/<stem>.timestamped.txt
#   <transcript_dir>/<stem>.fulltext.txt
#
# 滾動字幕去重的作法參考 htlin222/sum-the-yt 的 vtt_to_srt()（MIT），
# 另加「前綴重疊」處理——YouTube 自動字幕更常見的是「上一句整段重印＋接新字」，
# 只比對完全相同會漏掉，逐字稿會膨脹好幾倍。
import os, sys, re, glob

if len(sys.argv) < 3:
    print("用法: python subclean.py <subs_dir> <transcript_dir>（Mac/Linux 用 python3）", flush=True)
    sys.exit(2)
SUBS, TR = sys.argv[1], sys.argv[2]
os.makedirs(TR, exist_ok=True)

_CJK = re.compile(r"[぀-ヿ㐀-䶿一-鿿豈-﫿]")
_TS = re.compile(
    r"(\d{1,2}:\d{2}:\d{2}[.,]\d{3}|\d{1,2}:\d{2}[.,]\d{3})\s*-->\s*"
    r"(\d{1,2}:\d{2}:\d{2}[.,]\d{3}|\d{1,2}:\d{2}[.,]\d{3})"
)
# 字幕檔常帶語言尾碼：001.en-orig.vtt / 001.zh-Hant.srt → stem 一律取 001
_LANG_SUFFIX = re.compile(r"\.[A-Za-z]{2,3}(-[A-Za-z0-9]+)*$")


def sep_for(text=""):
    # 與 transcribe.py 同規則：CJK 段落間不加空白，其餘語言用空白
    return "" if _CJK.search(text or "") else " "


def _atomic_write(path, text):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, path)


def _to_seconds(ts):
    ts = ts.strip().replace(",", ".")
    parts = ts.split(":")
    if len(parts) == 2:
        parts = ["0"] + parts
    h, m, s = parts
    return int(h) * 3600 + int(m) * 60 + float(s)


def ts(s):
    h = int(s // 3600); m = int((s % 3600) // 60); s = int(s % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def parse_cues(text):
    """回傳 [(start_sec, cue_text)]，已去掉 <c>／<00:00:01.000> 之類的 inline tag。"""
    lines = text.splitlines()
    cues, i = [], 0
    while i < len(lines):
        m = _TS.search(lines[i])
        if not m:
            i += 1
            continue
        start = _to_seconds(m.group(1))
        i += 1
        buf = []
        while i < len(lines) and lines[i].strip() and not _TS.search(lines[i]):
            t = re.sub(r"<[^>]+>", "", lines[i])          # <c.colorE5E5E5>、<00:00:01.000>
            t = re.sub(r"^\s*\d+\s*$", "", t)             # SRT 的序號行
            t = re.sub(r"\s+", " ", t).strip()
            if t:
                buf.append(t)
            i += 1
        joined = " ".join(buf).strip()
        if joined:
            cues.append((start, joined))
    return cues


def dedupe(cues):
    """去掉滾動字幕的重複：① 與上一句完全相同就丟；② 上一句是新句的前綴就只留新增的尾巴。"""
    out = []
    for start, text in cues:
        if out:
            prev = out[-1][1]
            if text == prev:
                continue
            if len(text) > len(prev) and text.startswith(prev):
                text = text[len(prev):].strip()
                if not text:
                    continue
        out.append((start, text))
    return out


exts = ("*.vtt", "*.srt")
files = sorted({f for e in exts for f in glob.glob(os.path.join(SUBS, e))})
if not files:
    print(f"[error] {SUBS} 裡沒有任何 .vtt/.srt 字幕檔", flush=True)
    sys.exit(3)

done = 0
for f in files:
    stem = os.path.splitext(os.path.basename(f))[0]
    stem = _LANG_SUFFIX.sub("", stem) or stem
    base = os.path.join(TR, stem)
    if os.path.exists(base + ".fulltext.txt"):
        print(f"[skip] {stem}（已有逐字稿）", flush=True)
        continue
    with open(f, encoding="utf-8", errors="ignore") as fh:
        cues = dedupe(parse_cues(fh.read()))
    if not cues:
        print(f"[warn] {os.path.basename(f)} 解析不出任何字幕段落，略過", flush=True)
        continue
    texts = [c[1] for c in cues]
    _atomic_write(base + ".timestamped.txt", "".join(f"[{ts(s)}] {t}\n" for s, t in cues))
    _atomic_write(base + ".fulltext.txt", sep_for("".join(texts)).join(texts))
    print(f"[ok] {stem}: {len(cues)} 段 / {sum(len(t) for t in texts)} 字", flush=True)
    done += 1

print(f"[done] 產出 {done} 份逐字稿 → {TR}", flush=True)
sys.exit(0 if done or files else 3)
