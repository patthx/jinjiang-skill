#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
zh-novel-voice 文风自检
    python check.py 稿子.txt --style classical
    python check.py 稿子.txt --style modern --out 报告.txt

所有基线与黑名单均取自两部源作品的全文实测,不是凭感觉列的。
"""
import argparse, io, os, re, sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ---- 源作品实测基线(每万汉字) -------------------------------------------
BASELINE = {
    "classical": {   # 源文本 A（古典江湖类）594,322 汉字 / 13,942 句
        "avg_sent_len": 42.6, "comma_per_sent": 3.25,
        "post_attrib": 0.10, "short_para_pct": 9.1,
        "words": {"道：": 50.5, "说：": 0.2, "便": 34.8, "却": 19.4, "竟": 10.4,
                  "似的": 8.4, "只见": 2.9, "倘若": 2.8, "谁知": 2.6, "好像": 6.2,
                  "感到": 0.02, "情绪": 0.2, "氛围": 0.0, "内心深处": 0.0,
                  "静静": 0.3, "而是": 0.6, "一丝": 0.6, "一抹": 0.1,
                  "涌起": 0.07, "眼眶": 0.3, "不禁": 0.1},
    },
    "modern": {    # 源文本 B（当代科幻类）1,255,851 汉字 / 47,416 句
        "avg_sent_len": 26.5, "comma_per_sent": 1.54,
        "post_attrib": 0.70, "short_para_pct": 9.0,
        "words": {"道：": 1.0, "说：": 13.9, "便": 3.7, "却": 3.5, "竟": 2.9,
                  "似的": 1.3, "只见": 0.1, "倘若": 0.02, "谁知": 0.1, "好像": 2.7,
                  "感到": 1.4, "情绪": 2.3, "缓缓": 0.6, "轻轻": 0.5,
                  "微微": 0.9, "静静": 0.2, "仿佛": 0.8, "不由自主": 0.1,
                  "一抹": 0.1, "涌起": 0.0, "眼眶": 0.1, "不禁": 0.3},
    },
}

RANGES = {
    "classical": {
        "avg_sent_len":   (34, 56,   "平均句长(汉字/句)"),
        "comma_per_sent": (2.4, 4.6, "每句逗号数"),
        "short_para_pct": (4, 20,    "短段落占比%(<=12汉字)"),
        "post_attrib":    (0.0, 0.28, "后置归属占比"),
    },
    "modern": {
        "avg_sent_len":   (19, 34,   "平均句长(汉字/句)"),
        "comma_per_sent": (1.0, 2.2, "每句逗号数"),
        "short_para_pct": (4, 20,    "短段落占比%(<=12汉字)"),
        "post_attrib":    (0.42, 1.0, "后置归属占比"),
    },
}

# 风格词下限:达不到就不是这个作者
FLOORS = {
    "classical": [("便", 18), ("道：", 25), ("似的", 3.5), ("却", 8)],
    "modern":  [("说：", 6)],
}

# 风格词上限:超了就跑到另一个包去了 / 或是 AI 腔
CEIL = {
    "classical": [("说：", 2), ("感到", 0.6), ("情绪", 1.2), ("氛围", 0.5),
               ("内心深处", 0.3), ("静静", 1.5), ("而是", 2.0), ("一丝", 2.0)],
    "modern":  [("道：", 3), ("便", 9), ("只见", 0.6), ("约莫", 0.3),
               ("不料", 0.3), ("倘若", 0.4), ("谁知", 0.5), ("似的", 3.5),
               ("缓缓", 1.6), ("轻轻", 1.6), ("微微", 2.2), ("静静", 1.0),
               ("仿佛", 2.2), ("不由自主", 1.0)],
}

# 两包共同上限:源作品里都近乎为零
UNIVERSAL_CEIL = [("一抹", 0.5), ("涌起", 0.3), ("眼眶", 1.0), ("不禁", 1.2)]

# ---- 硬禁短语:两部源作品全文 0 次命中,出现即 FAIL ----------------------
BANNED = [
    "心头一颤", "心中涌起", "像潮水一样", "无法言喻", "难以名状",
    "百感交集", "思绪万千", "眼中闪过一丝", "仿佛过了一个世纪",
    "时间仿佛静止", "心脏漏跳了一拍", "一股暖流", "苦涩的笑容",
    "勾起一抹", "嘴角泛起", "眼底闪过", "深邃的眼眸", "顿了顿，开口道",
    "指节泛白", "喉结滚动", "呼吸一滞", "如坠冰窖", "命运的齿轮",
    "仿佛整个世界", "温柔而坚定", "破碎又美丽", "了然于心",
]

# ---- 软禁短语:源作品用过但极罕见。值 = 两书合计命中次数 ----------------
SOFT = {
    "五味杂陈": 2, "空气仿佛凝固": 1, "嘴角勾起": 1, "眼神复杂": 9,
    "不易察觉": 9, "若有所思地点了点头": 1, "深深地吸了一口气": 1,
    "说不清道不明": 17, "如潮水般": 4, "陷入了沉思": 1, "沉默了许久": 1,
    "复杂的神色": 2, "微微一怔": 2, "不由得一愣": 1, "唯一的光": 2,
}

# 注:下列词曾被本 skill 误判为 AI 腔,实测两个源文本都在用,不禁 ——
#   不动声色地(13/22) 意味深长(11/6) 脊背发凉(2/4) 涌上心头(5/2)
#   淡淡道(2/11) 挑了挑眉(2/7) 汗毛倒竖(2/4) 沉声道(12/0,古典体专用)

SENT_END = "。！？"


def read_text(path):
    for enc in ("utf-8", "utf-8-sig", "gb18030"):
        try:
            return io.open(path, encoding=enc).read()
        except (UnicodeDecodeError, LookupError):
            continue
    return io.open(path, encoding="utf-8", errors="replace").read()


def analyse(text):
    han = len(re.findall(r"[\u4e00-\u9fff]", text)) or 1
    sent = len(re.findall("[%s]" % SENT_END, text)) or 1
    paras = [p.strip().strip("\u3000") for p in text.splitlines()]
    paras = [p for p in paras if len(p) > 1] or ["x"]
    short = sum(1 for p in paras
                if len(re.findall(r"[\u4e00-\u9fff]", p)) <= 12)
    pre = len(re.findall(r"[^，。！？“”\s]{1,6}(?:道|说)：“", text))
    post = len(re.findall(r"”[^，。！？“”\s]{1,8}(?:道|说)[。，]", text))
    return {
        "han": han, "sent": sent, "paras": len(paras),
        "avg_sent_len": han / sent,
        "comma_per_sent": text.count("，") / sent,
        "short_para_pct": short / len(paras) * 100,
        "post_attrib": post / (pre + post) if (pre + post) else 0.0,
        "pre": pre, "post": post, "text": text,
        "per10k": lambda w: text.count(w) / han * 10000,
    }


def flag(ok):
    return "  OK  " if ok else " FAIL "


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--style", choices=["classical", "modern"], required=True)
    ap.add_argument("--out")
    a = ap.parse_args()

    if not os.path.exists(a.file):
        sys.exit("找不到文件: %s" % a.file)

    m = analyse(read_text(a.file))
    base, rng = BASELINE[a.style], RANGES[a.style]
    per10k, out, fails = m["per10k"], [], 0
    bw = base["words"]

    name = {"classical": "古典江湖体", "modern": "当代白描体"}[a.style]
    out.append("=" * 64)
    out.append("文风自检 · %s" % name)
    out.append("样本 %d 汉字 / %d 句 / %d 段  |  归属 前置%d 后置%d"
               % (m["han"], m["sent"], m["paras"], m["pre"], m["post"]))
    if m["han"] < 800:
        out.append("!! 样本 <800 汉字,指标波动大,仅供参考")
    out.append("=" * 64)

    out.append("\n[结构指标]                       本稿     原著   目标区间")
    for key, (lo, hi, label) in rng.items():
        ok = lo <= m[key] <= hi
        fails += 0 if ok else 1
        out.append("  %s %-18s %7.2f  %7.2f   %.2f-%.2f"
                   % (flag(ok), label, m[key], base[key], lo, hi))

    out.append("\n[风格词 下限]                     本稿     原著     要求")
    for w, fl in FLOORS[a.style]:
        v = per10k(w); ok = v >= fl
        fails += 0 if ok else 1
        out.append("  %s %-18s %7.2f  %7.2f    >=%.1f"
                   % (flag(ok), "「%s」/万字" % w, v, bw.get(w, 0), fl))

    out.append("\n[风格词 上限]                     本稿     原著     要求")
    for w, ce in CEIL[a.style] + UNIVERSAL_CEIL:
        v = per10k(w); ok = v <= ce
        fails += 0 if ok else 1
        out.append("  %s %-18s %7.2f  %7.2f    <=%.1f"
                   % (flag(ok), "「%s」/万字" % w, v, bw.get(w, 0), ce))

    hits, soft = [], []
    for i, line in enumerate(m["text"].splitlines(), 1):
        for b in BANNED:
            if b in line:
                hits.append((i, b, line.strip()[:42]))
        for b in SOFT:
            if b in line:
                soft.append((i, b, line.strip()[:42]))

    out.append("\n[AI腔硬禁短语]  两部源作品 0 次命中")
    if hits:
        fails += len(hits)
        for i, b, sn in hits[:40]:
            out.append("   FAIL  第%-5d行 「%s」  %s…" % (i, b, sn))
        if len(hits) > 40:
            out.append("   ...另有 %d 处" % (len(hits) - 40))
    else:
        out.append("    OK   未命中")

    out.append("\n[AI腔软禁短语]  源作品极罕见,酌情替换(不计 FAIL)")
    if soft:
        for i, b, sn in soft[:20]:
            out.append("   WARN  第%-5d行 「%s」(原著共%d次)  %s…"
                       % (i, b, SOFT[b], sn))
        if len(soft) > 20:
            out.append("   ...另有 %d 处" % (len(soft) - 20))
    else:
        out.append("    OK   未命中")

    out.append("\n" + "=" * 64)
    out.append("通过,可以交稿。" if fails == 0
               else "%d 项未通过 → 回到 references/ai-flavor.md 洗稿。" % fails)
    out.append("=" * 64)

    rep = "\n".join(out)
    print(rep)
    if a.out:
        io.open(a.out, "w", encoding="utf-8").write(rep + "\n")
        print("\n报告已写入 %s" % a.out)
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
