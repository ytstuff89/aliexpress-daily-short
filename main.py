# main.py — full auto, no external API
import os, re, io, random, subprocess, textwrap, time
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageOps, ImageDraw, ImageFont
import numpy as np
from moviepy.editor import ImageClip, AudioFileClip, concatenate_videoclips

# ---------- CONST ----------
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
HEAD = {"User-Agent": UA, "Accept-Language":"en-US,en;q=0.8"}
W, H = 1080, 1920
TARGET_SECONDS = 45
MIN_IMGS, MAX_IMGS = 3, 4

# ---------- HELPERS ----------
def http_get(url, retry=3, sleep=2):
    for i in range(retry):
        r = requests.get(url, headers=HEAD, timeout=25)
        if r.status_code == 200 and r.text:
            return r.text
        time.sleep(sleep)
    raise RuntimeError(f"GET failed: {url}")

def pick_from(seq):
    return random.choice(seq)

# ---------- 1) FIND PRODUCT (AliExpress search HTML, no API) ----------
KEYWORDS = [
    "gadget", "kitchen gadget", "car accessory", "phone accessory",
    "tool", "mini fan", "usb gadget", "desk gadget"
]

def search_aliexpress_links(q):
    # public search HTML (server-side rendered enough to parse links)
    url = f"https://www.aliexpress.com/wholesale?SearchText={requests.utils.quote(q)}"
    html = http_get(url)
    # parse item links like /item/100500...html
    links = re.findall(r'//www\.aliexpress\.com/item/\d+\.html', html)
    # normalize to https
    links = [("https:" + L) if L.startswith("//") else L for L in links]
    # filter duplicates
    out, seen = [], set()
    for u in links:
        if u not in seen:
            seen.add(u); out.append(u)
    return out

def pick_product_url():
    random.shuffle(KEYWORDS)
    for kw in KEYWORDS:
        links = search_aliexpress_links(kw)
        # prefer english-language listings
        links = [u for u in links if "/item/" in u]
        if links:
            return pick_from(links[:20])
    # ultimate fallback
    return "https://www.aliexpress.com/item/1005005145894174.html"

# ---------- 2) SCRAPE PRODUCT PAGE ----------
IMG_CDN_PAT = re.compile(r'https://[a-z0-9\.-]*alicdn\.com/[^\s"\'\\]+?\.(?:jpg|jpeg|png)', re.I)

def scrape_product(url):
    html = http_get(url)
    soup = BeautifulSoup(html, "lxml")

    # Title
    title = None
    m = soup.find("meta", property="og:title")
    if m and m.get("content"): title = m["content"].strip()
    if not title:
        t = soup.find("title")
        if t: title = t.get_text().strip()
    if not title:
        title = "AliExpress Gadget"

    # Price (best effort)
    price = None
    md = soup.find("meta", property="og:description")
    if md and md.get("content"):
        pm = re.search(r'(\$\s?\d+[\.,]?\d*|\d+[\.,]?\d*\s*(USD|PLN|EUR|€|zł))', md["content"])
        if pm: price = pm.group(0)
    if not price:
        txt = soup.get_text(" ", strip=True)
        pm = re.search(r'(\$\s?\d+[\.,]?\d*|\d+[\.,]?\d*\s*(USD|PLN|EUR|€|zł))', txt)
        if pm: price = pm.group(0)
    if not price:
        price = "budget price"

    # Images: take from page <img> + scripts pointing to alicdn
    imgs = []
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or ""
        if src.startswith("//"): src = "https:" + src
        if src.startswith("http") and ("alicdn" in src or "aliexpress" in src):
            if src.lower().endswith((".jpg",".jpeg",".png")):
                imgs.append(src)

    for s in soup.find_all("script"):
        for u in IMG_CDN_PAT.findall(s.get_text(" ", strip=False)):
            imgs.append(u)

    # clean & keep only full-size (try to upgrade size)
    clean = []
    seen = set()
    for u in imgs:
        # upgrade small -> large if pattern present
        u = re.sub(r'_(?:\d+x\d+|Q\d+|jpg_)?\.(jpg|jpeg|png)$', r'.\1', u)
        if u not in seen:
            seen.add(u); clean.append(u)

    # keep 3-4
    photos = clean[:MAX_IMGS] if len(clean) >= MIN_IMGS else clean

    return {"title": title, "price": price, "url": url, "images": photos}

# ---------- 3) IMAGE PREP ----------
def download_image(url):
    try:
        r = requests.get(url, headers=HEAD, timeout=25)
        r.raise_for_status()
        return Image.open(io.BytesIO(r.content)).convert("RGB")
    except Exception:
        return None

def fit_9x16(img):
    return ImageOps.fit(img, (W, H), method=Image.LANCZOS, centering=(0.5,0.5))

def gather_frames(urls):
    frames = []
    for u in urls:
        im = download_image(u)
        if im is None: continue
        frames.append(fit_9x16(im))
        if len(frames) >= MAX_IMGS: break
    # hard fallback
    if not frames:
        r = requests.get("https://picsum.photos/1080/1920", timeout=20)
        frames = [Image.open(io.BytesIO(r.content)).convert("RGB")]
    return frames

# ---------- 4) CAPTIONS & OVERLAYS ----------
def wrap(draw, text, max_w, font):
    lines, line = [], ""
    for w in text.split():
        test = (line + " " + w).strip()
        bbox = draw.textbbox((0,0), test, font=font)
        if (bbox[2]-bbox[0]) <= max_w:
            line = test
        else:
            if line: lines.append(line)
            line = w
    if line: lines.append(line)
    return lines

def overlay(img, title, price, caption):
    o = Image.new("RGBA", (W,H), (0,0,0,0))
    d = ImageDraw.Draw(o)
    d.rectangle([0,0,W,210], fill=(0,0,0,150))
    d.rectangle([0,H-200,W,H], fill=(0,0,0,160))
    try:
        f_big = ImageFont.truetype("DejaVuSans-Bold.ttf", 56)
        f_mid = ImageFont.truetype("DejaVuSans.ttf", 46)
    except:
        f_big = ImageFont.load_default(); f_mid = ImageFont.load_default()

    # top
    y=34
    for ln in wrap(d, title[:100], W-120, f_big)[:2]:
        d.text((60,y), ln, fill=(255,255,255,255), font=f_big); y+=64
    d.text((60,y+6), f"Price: {price}", fill=(255,255,255,255), font=f_mid)

    # bottom
    lines = wrap(d, caption, W-120, f_mid)[:4]
    yb = H-190-(len(lines)*48)
    for ln in lines:
        d.text((60,yb), ln, fill=(255,255,255,255), font=f_mid); yb+=48

    out = img.convert("RGBA")
    return Image.alpha_composite(out, o).convert("RGB")

# ---------- 5) SCRIPT (naturalny, bez „Reason 1…”) ----------
def build_script(title, price):
    return (
        f"{title}. "
        f"Price {price}. "
        "Quick look at what you actually get. "
        "Small, cheap, and useful for everyday tasks. "
        "Build quality is okay for the money and reviews say it does the job. "
        "If you're into budget tech finds, this one’s worth a look. "
        "Check the link for details."
    )

def split_for_scenes(text, n):
    words = text.split()
    n = max(1,n)
    chunk = max(1, len(words)//n)
    parts=[]
    for i in range(0,len(words),chunk):
        parts.append(" ".join(words[i:i+chunk]))
        if len(parts)==n: break
    while len(parts)<n: parts.append("")
    return parts

# ---------- 6) TTS (espeak-ng tuned; fallback gTTS) ----------
def tts_to_mp3(text, out="voice.mp3"):
    try:
        subprocess.run(["espeak-ng","--version"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        wav = "voice.wav"
        # en-us+m7 — męski; s=165 tempo; p=52 pitch (bardziej ludzki)
        subprocess.run(["espeak-ng","-v","en-us+m7","-s","165","-p","52","-w",wav,text], check=True)
        subprocess.run(["ffmpeg","-y","-i",wav,"-ar","44100","-ac","2",out],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try: os.remove(wav)
        except: pass
    except Exception:
        from gtts import gTTS
        gTTS(text=text, lang="en").save(out)
    # duration
    aud = AudioFileClip(out); dur=float(aud.duration); aud.close()
    return out, dur

# ---------- 7) BUILD VIDEO ----------
def build_video(frames, title, price, script_text, voice_mp3, out="short.mp4"):
    audio = AudioFileClip(voice_mp3)
    
    # ile mamy zdjęć i scen
    n = len(frames)
    if n == 0: raise RuntimeError("No frames found")
    n = max(MIN_IMGS, min(MAX_IMGS, n))
    frames = frames[:n]

    parts = split_for_scenes(script_text, n)
    parts = parts[:n]  # dopasowanie długości

    target = max(TARGET_SECONDS, audio.duration)
    per = max(4.5, target / n)

    clips = []
    for i in range(n):
        fr = overlay(frames[i], title, price, parts[i])
        clip = ImageClip(np.array(fr)).set_duration(per).set_position("center")
        clips.append(clip)

    seq = concatenate_videoclips(clips, method="compose").set_fps(30)

    if seq.duration < audio.duration:
        delta = audio.duration - seq.duration
        clips[-1] = clips[-1].set_duration(clips[-1].duration + delta)
        seq = concatenate_videoclips(clips, method="compose").set_fps(30)

    seq = seq.set_audio(audio)
    seq.write_videofile(out, codec="libx264", audio_codec="aac", fps=30)
    audio.close()
    return out

# ---------- 8) MAIN ----------
def main():
    url = pick_product_url()
    meta = scrape_product(url)
    frames = gather_frames(meta["images"])
    script_text = build_script(meta["title"], meta["price"])
    voice_mp3, _ = tts_to_mp3(script_text, "voice.mp3")
    build_video(frames, meta["title"], meta["price"], script_text, voice_mp3, out="short.mp4")
    print("OK:", meta["title"], meta["url"])

if __name__ == "__main__":
    main()
