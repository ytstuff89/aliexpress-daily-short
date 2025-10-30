import os, re, io, random, smtplib
from email.message import EmailMessage
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from gtts import gTTS
from PIL import Image, ImageOps, ImageDraw, ImageFont
import numpy as np
from moviepy.editor import ImageClip, AudioFileClip, concatenate_videoclips

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"

# ------------------------- PRODUCT PICK (stabilne URL-e) -------------------------
def pick_aliexpress_url():
    sample = [
        "https://www.aliexpress.com/item/1005005136453309.html",
        "https://www.aliexpress.com/item/1005006227833009.html",
        "https://www.aliexpress.com/item/1005005902550895.html",
        "https://www.aliexpress.com/item/1005006069462704.html",
        "https://www.aliexpress.com/item/1005006434825098.html",
        "https://www.aliexpress.com/item/1005005145894174.html",
    ]
    return random.choice(sample)

# ------------------------- SCRAPE -------------------------
def fetch(url):
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=25)
    r.raise_for_status()
    return r.text

def parse_product(html, url):
    soup = BeautifulSoup(html, "lxml")

    # TITLE
    title = None
    ogt = soup.find("meta", property="og:title")
    if ogt and ogt.get("content"): title = ogt["content"].strip()
    if not title:
        t = soup.find("title")
        if t: title = t.get_text().strip()
    if not title:
        title = "AliExpress Gadget"

    # IMAGES (zbieramy z og:image + skryptów)
    images = []
    for m in soup.find_all("meta", {"property": "og:image"}):
        c = m.get("content")
        if c and c.startswith("http") and c not in images:
            images.append(c)

    patt = re.compile(r'https?://[^"\']+\.(?:jpg|jpeg|png)', re.I)
    for s in soup.find_all("script"):
        txt = s.get_text(" ", strip=False)
        for u in patt.findall(txt):
            if any(k in u for k in ("ae01", "ae03", "alicdn", "aliexpress", "img.alicdn")):
                if u not in images:
                    images.append(u)

    # PRICE (best-effort)
    price = None
    ogd = soup.find("meta", property="og:description")
    if ogd and ogd.get("content"):
        m = re.search(r'(\$\s?\d+[\.,]?\d*|\d+[\.,]?\d*\s*(USD|PLN|€|EUR|zł))', ogd["content"])
        if m: price = m.group(0)
    if not price:
        txt = soup.get_text(" ", strip=True)
        m = re.search(r'(\$\s?\d+[\.,]?\d*|\d+[\.,]?\d*\s*(USD|PLN|€|EUR|zł))', txt)
        if m: price = m.group(0)
    if not price:
        price = "Budget price"

    return {"title": title, "images": images[:6], "price": price, "url": url}

# ------------------------- MEDIA -------------------------
def safe_get_image(url):
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=25)
        r.raise_for_status()
        return Image.open(io.BytesIO(r.content)).convert("RGB")
    except:
        return None

def prepare_images(urls, target=(1080,1920)):
    imgs = []
    for u in urls:
        im = safe_get_image(u)
        if im is None: continue
        fitted = ImageOps.fit(im, target, method=Image.LANCZOS, centering=(0.5,0.5))
        imgs.append(fitted)
        if len(imgs) >= 6: break
    # fallback jeśli brak fot
    if not imgs:
        ph = requests.get("https://picsum.photos/1080/1920", timeout=20).content
        imgs = [Image.open(io.BytesIO(ph)).convert("RGB")]
    return imgs

def _wrap(draw, text, max_width, font):
    lines, line = [], ""
    for w in text.split():
        test = (line + " " + w).strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if (bbox[2]-bbox[0]) <= max_width:
            line = test
        else:
            if line: lines.append(line)
            line = w
    if line: lines.append(line)
    return lines

def _overlay(img, title, price, cta):
    W, H = img.size
    o = Image.new("RGBA", (W,H), (0,0,0,0))
    od = ImageDraw.Draw(o)
    od.rectangle([0,0,W,190], fill=(0,0,0,120))
    od.rectangle([0,H-140,W,H], fill=(0,0,0,120))
    try:
        f_big = ImageFont.truetype("DejaVuSans-Bold.ttf", 48)
        f_mid = ImageFont.truetype("DejaVuSans.ttf", 42)
    except:
        f_big = ImageFont.load_default(); f_mid = ImageFont.load_default()
    d = ImageDraw.Draw(o)
    y = 28
    for ln in _wrap(d, title[:100], W-120, f_big)[:2]:
        d.text((60,y), ln, fill=(255,255,255,255), font=f_big); y += 54
    d.text((60,y+10), f"Price: {price}", fill=(255,255,255,255), font=f_mid)
    yb = H-120
    for ln in _wrap(d, cta, W-120, f_mid)[:2]:
        d.text((60,yb), ln, fill=(255,255,255,255), font=f_mid); yb += 46
    out = img.convert("RGBA")
    return Image.alpha_composite(out, o).convert("RGB")

def write_script(title, price, url):
    txt = f"""Quick look at a cheap AliExpress find!
Product: {title}. Price: {price}.
Pros: affordable, useful. Always check reviews before buying.
Link in bio."""
    return " ".join([t.strip() for t in txt.splitlines() if t.strip()])

def tts_gtts(text, out="voice.mp3"):
    tts = gTTS(text=text, lang="en", tld="co.uk")
    tts.save(out)
    return out

def build_video(images, voice_path, out="short.mp4", title="", price=""):
    per = max(5, 45 // max(1, len(images)))
    processed = [_overlay(im, title, price, "Follow for more cheap finds!") for im in images]
    clips = [ImageClip(np.array(im)).set_duration(per).set_position("center") for im in processed]
    seq = concatenate_videoclips(clips, method="compose").set_fps(30)
    audio = AudioFileClip(voice_path)
    seq = seq.set_audio(audio)
    seq.write_videofile(out, codec="libx264", audio_codec="aac", fps=30)
    return out

# ------------------------- EMAIL (opcjonalnie) -------------------------
def maybe_send_email(attachment):
    user = os.environ.get("GMAIL_USER")
    app_pw = os.environ.get("GMAIL_APP_PASSWORD")
    to_addr = os.environ.get("RECIPIENT_EMAIL", user)
    if not (user and app_pw and to_addr):  # brak konfiguracji – pomijamy
        return
    msg = EmailMessage()
    msg["From"] = user; msg["To"] = to_addr
    msg["Subject"] = f"Daily AliExpress Short - {datetime.utcnow().strftime('%Y-%m-%d')}"
    msg.set_content("Video attached.")
    with open(attachment, "rb") as f:
        msg.add_attachment(f.read(), maintype="video", subtype="mp4", filename="short.mp4")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(user, app_pw); s.send_message(msg)

# ------------------------- MAIN -------------------------
def main():
    url = pick_aliexpress_url()
    html = fetch(url)
    meta = parse_product(html, url)
    imgs = prepare_images(meta["images"])
    voice = tts_gtts(write_script(meta["title"], meta["price"], meta["url"]))
    video = build_video(imgs, voice, "short.mp4", title=meta["title"], price=meta["price"])
    maybe_send_email(video)

if __name__ == "__main__":
    main()
