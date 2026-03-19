import re
import httpx

html = httpx.get("https://y.qq.com/", timeout=20).text
srcs = re.findall(r"<script[^>]+src=[\"']([^\"']+)[\"']", html, re.I)
full = []
for s in srcs:
    if s.startswith("//"):
        s = "https:" + s
    elif s.startswith("/"):
        s = "https://y.qq.com" + s
    full.append(s)

print("scripts", len(full))
keywords = ["login", "common", "vendor", "main", "index", "chunk"]
cands = [u for u in full if any(k in u.lower() for k in keywords)]
print("candidates", len(cands))

checked = 0
for u in cands[:30]:
    try:
        t = httpx.get(u, timeout=20).text
    except Exception:
        continue

    if (
        "qrconnect" in t.lower()
        or "open.weixin.qq.com" in t.lower()
        or ("wx" in t.lower() and "login" in t.lower())
    ):
        print("HIT", u)
        for pat in [
            r"https://open\\.weixin\\.qq\\.com[^\"']+",
            r"qrconnect[^\"']+",
            r"wx[0-9a-zA-Z]{15,}",
        ]:
            ms = re.findall(pat, t, re.I)
            if ms:
                print(" ", pat, ms[:5])
    checked += 1

print("checked", checked)
