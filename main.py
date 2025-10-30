import os, re, io, random, time, smtplib, textwrap
from email.message import EmailMessage
from datetime import datetime
from duckduckgo_search import DDGS
import requests
from bs4 import BeautifulSoup
from gtts import gTTS
from PIL import Image, ImageOps
from moviepy.editor import ImageClip, AudioFileClip, concatenate_videoclips
from moviepy.editor import CompositeVideoClip, TextClip
from moviepy.video.fx.all import resize

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"

def ddg_search_aliexpress():
    # prosta lista linków losowych żeby uniknąć limitów DDG
    sample = [
        "https://www.aliexpress.com/item/1005005136453309.html",
        "https://www.aliexpress.com/item/1005006227833009.html",
        "https://www.aliexpress.com/item/1005005902550895.html",
        "https://www.aliexpress.com/item/1005006069462704.html",
        "https://www.aliexpress.com/item/1005006434825098.html",
    ]
    return random.choice(sample)

def fetch(url):
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
    r.raise_for_status()
    return r.text

def parse_product(html, url):
    soup = BeautifulSoup(html, "lxml")
    title = None
    ogt = soup.find("meta", property="og:title")
    if ogt and ogt.get("content"): title = ogt["content"].strip()
    if not title:
        t = soup.find("title")
        if t: title = t.get_text().strip()
    images = []
    for m in soup.find_all("meta", {"property": "og:image"}):
        c = m.get("content")
        if c and c not in images: images.append(c)
    for script in soup.find_all("script"):
        txt = script.get_text(" ", strip=False)
        if "image" in txt and (".jpg" in txt or ".png" in txt):
            for u in re.findall(r'https?://[^"\']+\.(?:jpg|jpeg|png)', txt, flags=re.I):
                if "ae03" in u or "ae01" in u or "alicdn" in u or "aliexpress" in u:
                    if u not in images: images.append(u)
    price = None
    ogd = soup.find("meta", property="og:description")
    if ogd and ogd.get("content"):
        m = re.search(r'(\$\s?\d+[\.\,]?\d*|\d+[\.\,]?\d*\s*(USD|PLN|€|EUR|zł|RUB|₽))', ogd["content"])
        if m: price = m.group(0)
    if not price:
        txt = soup.get_text(" ", strip=True)
        m = re.search(r'(\$\s?\d+[\.\,]?\d*|\d+[\.\,]?\d*\s*(USD|PLN|€|EUR|zł|RUB|₽))', txt)
        if m: price = m.group(0)
    return {
        "title": title or "Tani gadżet z AliExpress",
        "images": images[:8] if images else [],
        "price": price or "okazyjna cena",
        "url": url
    }

def safe_get_image(url):
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
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
        bg = ImageOps.fit(img, target, method=Image.LANCZOS, bleed=0.0, centering=(0.5,0.5))
        imgs.append(bg)
        if len(imgs) >= 6:
            break
    return imgs

def write_script_pl(title, price, url):
    base = f"""Quick look at a cheap gadget from AliExpress!
Product: {title}.
Price: {price}.
Why buy it? It's simple, useful and budget-friendly.
Pros: low price, easy to use, looks decent for what you pay.
Cons: don’t expect premium quality – you get what you pay for.
Tip: check reviews and photos before buying.
Link in bio. Grab it before the price goes up!
"""
    lines = [l.strip() for l in base.splitlines() if l.strip()]
    return " ".join(lines)

def tts_gtts_pl(text, out_path="voice.mp3"):
    tts = gTTS(text=text, lang="en")
    tts.save(out_path)
    return out_path

def build_video(images, voice_path, out_path="short.mp4", title="", price=""):
    W, H = 1080, 1920
    duration_total = 45
    per = max(5, duration_total // max(1, len(images)))
    clips = []
    for im in images:
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=92)
        buf.seek(0)
        c = ImageClip(buf).set_duration(per)
        zx = 1.06
        c1 = c.resize(lambda t: 1 + (zx-1)*(t/per)).set_position("center")
        clips.append(c1)
    if not clips:
        txt = TextClip("Cheap gadget from AliExpress", fontsize=72, font="Arial-Bold",
                       method="caption", size=(W-100,None), color="white").set_duration(duration_total)
        bg = TextClip("", size=(W,H), color=(0,0,0)).set_duration(duration_total)
        clips = [CompositeVideoClip([bg, txt.set_position("center")], size=(W,H))]
    seq = concatenate_videoclips(clips, method="compose")
    seq = seq.set_fps(30).resize((W,H))

    try:
    title_txt = TextClip(title[:60], fontsize=52, font="Arial-Bold",
                         method="caption", size=(W-120,None), color="white").set_duration(seq.duration)
except:
    title_txt = TextClip(title[:60], fontsize=52, color="white").set_duration(seq.duration)
    price_txt = TextClip(f"Price: {price}", fontsize=48, font="Arial",
                         method="caption", size=(W-120,None), color="white").set_duration(min(8, seq.duration))
    bar = TextClip("", size=(W,180), color=(0,0,0)).set_opacity(0.45).set_duration(seq.duration)
    try:
    cta = TextClip("Subscribe for more cheap finds!", fontsize=46, font="Arial",
                   method="caption", size=(W-120,None), color="white").set_duration(min(7, seq.duration))
except:
    cta = TextClip("Subscribe for more cheap finds!", fontsize=46, color="white").set_duration(min(7, seq.duration))

    comp = CompositeVideoClip(
        [
            seq,
            bar.set_position(("center","top")),
            title_txt.set_position(("center", 40)),
            price_txt.set_position(("center", 140)),
            cta.set_position(("center", H-160))
        ],
        size=(W,H)
    )

    audio = AudioFileClip(voice_path)
    comp = comp.set_audio(audio)
    comp.write_videofile(out_path, codec="libx264", audio_codec="aac", fps=30, preset="medium", threads=2)
    return out_path

def send_email_gmail_smtp(subject, body, attachment_path, to_addr):
    user = os.environ["GMAIL_USER"]
    app_pw = os.environ["GMAIL_APP_PASSWORD"]

    msg = EmailMessage()
    msg["From"] = user
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.set_content(body)

    with open(attachment_path, "rb") as f:
        data = f.read()
    msg.add_attachment(data, maintype="video", subtype="mp4", filename=os.path.basename(attachment_path))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(user, app_pw)
        s.send_message(msg)

def main():
    url = ddg_search_aliexpress()
    if not url:
        raise SystemExit("No AliExpress product found.")
    html = fetch(url)
    meta = parse_product(html, url)
    print("Product:", meta["title"], meta["price"], meta["url"])
    imgs = prepare_images(meta["images"])
    script = write_script_pl(meta["title"], meta["price"], meta["url"])
    voice = tts_gtts_pl(script, "voice.mp3")
    video = build_video(imgs, voice, "short.mp4", title=meta["title"], price=meta["price"])
    to_addr = os.environ.get("RECIPIENT_EMAIL", os.environ.get("GMAIL_USER"))
    subject = f"[Daily AliExpress Short] {datetime.utcnow().strftime('%Y-%m-%d')} - {meta['title'][:60]}"
    body = f"""Your ready short (45s) is attached.

Title: {meta['title']}
Price: {meta['price']}
Link: {meta['url']}
"""
    send_email_gmail_smtp(subject, body, video, to_addr)

if __name__ == "__main__":
    main()
