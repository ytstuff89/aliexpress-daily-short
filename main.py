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

# ------------------------- PRODUCT PICK -------------------------
def ddg_search_aliexpress():
    # Unikamy limitów – losujemy z listy sprawdzonych linków
    sample = [
        "https://www.aliexpress.com/item/1005005136453309.html",
        "https://www.aliexpress.com/item/1005006227833009.html",
        "https://www.aliexpress.com/item/1005005902550895.html",
        "https://www.aliexpress.com/item/1005006069462704.html",
        "https://www.aliexpress.com/item/1005006434825098.html",
    ]
    return random.choice(sample)

def fetch(url):
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=25)
    r.raise_for_status()
    return r.text

def parse_product(html, url):
    soup = BeautifulSoup(html, "lxml")

    # title
    title = None
    ogt = soup.find("meta", property="og:title")
    if ogt and ogt.get("content"): title = ogt["content"].strip()
    if not title:
        t = soup.find("title")
        if t: title = t.get_text().strip()

    # images
    images = []
    for m in soup.find_all("meta", {"property": "og:image"}):
        c = m.get("content")
        if c and c not in images: images.append(c)
    for script in soup.find_all("script"):
        txt = script.get_text(" ", strip=False)
        if "image" in txt and (".jpg" in txt or ".png" in txt):
            for u in re.findall(r'https?://[^"\']+\.(?:jpg|jpeg|png)', txt, flags=re.I):
                if any(k in u for k in ("ae03","ae01","alicdn","aliexpress")):
                    if u not in images: images.append(u)

    # price (best-effort)
    price = None
    ogd = soup.find("meta", property="og:description")
    if ogd and ogd.get("content"):
        m = re.search(r'(\$\s?\d+[\.,]?\d*|\d+[\.,]?\d*\s*(USD|PLN|€|EUR|zł))', ogd["content"])
        if m: price = m.group(0)
    if not price:
        txt = soup.get_text(" ", strip=True)
        m = re.search(r'(\$\s?\d+[\.,]?\d*|\d+[\.,]?\d*\s*(USD|PLN|€|EUR|zł))', txt)
        if m: price = m.group(0)

    return {
        "title": title or "Cheap AliExpress Gadget",
        "images": images[:6] if images else [],
        "price": price or "Budget price",
        "url": url
    }

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
    seen = set()
    for u in urls:
        if u in seen: continue
        seen.add(u)
        img = safe_get_image(u)
        if img is None: continue
        fitted = ImageOps.fit(img, target, method=Image.LANCZOS, centering=(0.5,0.5))
        imgs.append(fitted)
        if len(imgs) >= 6:
            break
    return imgs

def _wrap(draw, text, max_width, font):
    lines, line = [], ""
    for word in text.split():
        test = (line + " " + word).strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        w = bbox[2] - bbox[0]
        if w <= max_width:
            line = test
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines

def _overlay_text(img, title, price, cta):
    W, H = img.size
    overlay = Image.new("RGBA", (W,H), (0,0,0,0))
    odraw = ImageDraw.Draw(overlay)
    # paski
    odraw.rectangle([0,0,W,190], fill=(0,0,0,120))
    odraw.rectangle([0,H-140,W,H], fill=(0,0,0,120))
    # fonty
    try:
        font_big = ImageFont.truetype("DejaVuSans-Bold.ttf", 48)
        font_mid = ImageFont.truetype("DejaVuSans.ttf", 42)
    except:
        font_big = ImageFont.load_default()
        font_mid = ImageFont.load_default()
    draw = ImageDraw.Draw(overlay)
    # tytuł
    lines = _wrap(draw, title[:100], W-120, font_big)
    y = 28
    for ln in lines[:2]:
        draw.text((60,y), ln, font=font_big, fill=(255,255,255,255))
        y += 54
    # cena
    draw.text((60, y+10), f"Price: {price}", font=font_mid, fill=(255,255,255,255))
    # CTA
    cta_lines = _wrap(draw, cta, W-120, font_mid)
    yb = H-120
    for ln in cta_lines[:2]:
        draw.text((60,yb), ln, font=font_mid, fill=(255,255,255,255))
        yb += 46
    out = img.convert("RGBA")
    out = Image.alpha_composite(out, overlay).convert("RGB")
    return out

def write_script(title, price, url):
    base = f"""Quick look at a cheap gadget from AliExpress!
Product: {title}. Price: {price}.
Useful, affordable and fun to try.
Pros: low price, easy to use. Cons: not premium build.
Check buyer reviews & photos. Link below!"""
    return " ".join([l.strip() for l in base.splitlines() if l.strip()])

def tts_gtts(text, out_path="voice.mp3"):
    tts = gTTS(text=text, lang="en")
    tts.save(out_path)
    return out_path

def build_video(images, voice_path, out_path="short.mp4", title="", price=""):
    W, H = 1080, 1920
    duration_total = 45
    per = max(5, duration_total // max(1, len(images)))
    processed = []
    for im in images or [Image.new("RGB",(W,H),(0,0,0))]:
        with_text = _overlay_text(im, title, price, "Follow for more cheap finds!")
        processed.append(with_text)

    clips = []
    for im in processed:
        arr = np.array(im)  # PIL -> numpy
        c = ImageClip(arr).set_duration(per).set_position("center")
        clips.append(c)

    seq = concatenate_videoclips(clips, method="compose").set_fps(30).resize((W,H))
    audio = AudioFileClip(voice_path)
    seq = seq.set_audio(audio)
    seq.write_videofile(out_path, codec="libx264", audio_codec="aac", fps=30)
    return out_path

# ------------------------- EMAIL -------------------------
def send_email(subject, body, attachment_path):
    user = os.environ["GMAIL_USER"]
    app_pw = os.environ["GMAIL_APP_PASSWORD"]
    to_addr = os.environ.get("RECIPIENT_EMAIL", user)

    msg = EmailMessage()
    msg["From"] = user
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.set_content(body)

    with open(attachment_path, "rb") as f:
        msg.add_attachment(f.read(), maintype="video", subtype="mp4", filename="short.mp4")

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(user, app_pw)
        s.send_message(msg)

# ------------------------- MAIN -------------------------
def main():
    url = ddg_search_aliexpress()
    html = fetch(url)
    meta = parse_product(html, url)
    imgs = prepare_images(meta["images"])
    script = write_script(meta["title"], meta["price"], meta["url"])
    voice = tts_gtts(script)
    video = build_video(imgs, voice, "short.mp4", title=meta["title"], price=meta["price"])

    subject = f"Daily AliExpress Short - {datetime.utcnow().strftime('%Y-%m-%d')}"
    body = f"{meta['title']}\n{meta['price']}\n{meta['url']}"
    send_email(subject, body, video)

if __name__ == "__main__":
    main()
