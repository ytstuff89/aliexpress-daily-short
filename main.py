# main.py  — pełny, gotowy plik
# Cel: 9:16 short ~45 s, 3–4 zdjęcia TEGO produktu, płynny męski lektor,
# napisy rozłożone na CAŁY film. Zero ImageMagick – wszystko PIL+MoviePy.

import os, re, io, random, subprocess, textwrap
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageOps, ImageDraw, ImageFont
import numpy as np
from moviepy.editor import (
    ImageClip, AudioFileClip, concatenate_videoclips
)
from duckduckgo_search import DDGS

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
W, H = 1080, 1920
TARGET_SECONDS = 45
MIN_IMGS, MAX_IMGS = 3, 4

# ---------- 1) WYBÓR PRODUKTU ----------
def pick_aliexpress_url() -> str:
    # Stabilne przykładowe listingi (możesz dopisać kolejne)
    candidates = [
        "https://www.aliexpress.com/item/1005005136453309.html",
        "https://www.aliexpress.com/item/1005006227833009.html",
        "https://www.aliexpress.com/item/1005005902550895.html",
        "https://www.aliexpress.com/item/1005006069462704.html",
        "https://www.aliexpress.com/item/1005006434825098.html",
        "https://www.aliexpress.com/item/1005005145894174.html",
    ]
    return random.choice(candidates)

def get(url: str) -> str:
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=25)
    r.raise_for_status()
    return r.text

# ---------- 2) PARSOWANIE: TYTUŁ, CENA, ZDJĘCIA Z STRONY ----------
def parse_from_page(html: str, url: str):
    soup = BeautifulSoup(html, "lxml")

    # Tytuł
    title = None
    m = soup.find("meta", property="og:title")
    if m and m.get("content"):
        title = m["content"].strip()
    if not title:
        t = soup.find("title")
        if t: title = t.get_text().strip()
    if not title:
        title = "AliExpress Gadget"

    # Cena (best-effort)
    price = None
    md = soup.find("meta", property="og:description")
    if md and md.get("content"):
        m = re.search(r'(\$\s?\d+[\.,]?\d*|\d+[\.,]?\d*\s*(USD|PLN|EUR|€|zł))', md["content"])
        if m: price = m.group(0)
    if not price:
        txt = soup.get_text(" ", strip=True)
        m = re.search(r'(\$\s?\d+[\.,]?\d*|\d+[\.,]?\d*\s*(USD|PLN|EUR|€|zł))', txt)
        if m: price = m.group(0)
    if not price:
        price = "budget price"

    # Obrazy z alicdn/aliexpress w HTML/JS
    imgs = set()
    patt = re.compile(r'https://[a-z0-9\.-]*alicdn\.com/[^\s"\'\\]+?\.(?:jpg|jpeg|png)', re.I)
    for s in soup.find_all(["script", "img"]):
        if s.name == "img":
            src = s.get("src") or ""
            if src.startswith("http") and ("alicdn" in src or "aliexpress" in src):
                imgs.add(src)
        else:
            txt = s.get_text(" ", strip=False)
            for u in patt.findall(txt):
                imgs.add(u)

    return {"title": title, "price": price, "url": url, "images": list(imgs)}

# ---------- 3) UZUPEŁNIENIE ZDJĘĆ: DDG Images DLA KONKRETNEGO PRODUKTU ----------
def ddg_images(title: str, want: int) -> list[str]:
    out = []
    q = f'{title} site:alicdn.com OR site:aliexpress.com "img"'
    try:
        with DDGS() as ddg:
            for r in ddg.images(q, max_results=8, safesearch="Off"):
                u = r.get("image")
                if u and u.startswith("http") and ("alicdn" in u or "aliexpress" in u):
                    out.append(u)
                    if len(out) >= want:
                        break
    except Exception:
        pass
    return out

# ---------- 4) POBIERANIE I PRZYGOTOWANIE KADRÓW ----------
def pil_from_url(url: str):
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=25)
        r.raise_for_status()
        return Image.open(io.BytesIO(r.content)).convert("RGB")
    except Exception:
        return None

def fit_9x16(img: Image.Image) -> Image.Image:
    return ImageOps.fit(img, (W, H), method=Image.LANCZOS, centering=(0.5, 0.5))

def prepare_images(urls: list[str]) -> list[Image.Image]:
    frames = []
    for u in urls:
        im = pil_from_url(u)
        if im:
            frames.append(fit_9x16(im))
        if len(frames) >= MAX_IMGS:
            break
    return frames

# ---------- 5) NAPISY: TOP (tytuł), DÓŁ (captions) ----------
def wrap(draw, text, max_width, font):
    lines, line = [], ""
    for w in text.split():
        test = (line + " " + w).strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if (bbox[2] - bbox[0]) <= max_width:
            line = test
        else:
            if line: lines.append(line)
            line = w
    if line: lines.append(line)
    return lines

def overlay(img: Image.Image, title: str, price: str, caption: str) -> Image.Image:
    o = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(o)
    # pasy
    d.rectangle([0, 0, W, 210], fill=(0, 0, 0, 135))
    d.rectangle([0, H - 220, W, H], fill=(0, 0, 0, 155))
    try:
        f_big = ImageFont.truetype("DejaVuSans-Bold.ttf", 56)
        f_mid = ImageFont.truetype("DejaVuSans.ttf", 46)
    except:
        f_big = ImageFont.load_default(); f_mid = ImageFont.load_default()

    # górny tytuł
    y = 34
    for ln in wrap(d, title[:100], W - 120, f_big)[:2]:
        d.text((60, y), ln, fill=(255, 255, 255, 255), font=f_big); y += 64
    d.text((60, y + 6), f"Price: {price}", fill=(255, 255, 255, 255), font=f_mid)

    # dolne napisy (captions)
    cap_lines = wrap(d, caption, W - 120, f_mid)
    yb = H - 180 - (len(cap_lines) * 48)
    yb = max(yb, H - 200)  # bezpiecznie nad krawędzią
    for ln in cap_lines[:4]:
        d.text((60, yb), ln, fill=(255, 255, 255, 255), font=f_mid); yb += 48

    out = img.convert("RGBA")
    return Image.alpha_composite(out, o).convert("RGB")

# ---------- 6) TEKST NARRACJI + KAPITELKI (N CZĘŚCI) ----------
def script(title: str, price: str) -> str:
    return (
        f"{title}. Price {price}. "
        "Here is a quick look. "
        "Reason one: it is cheap and handy. "
        "Reason two: daily use, decent quality for the price. "
        "Reason three: nice small gift idea. "
        "Always read reviews and check real photos. "
        "Link in description."
    )

def split_into_chunks(text: str, n: int) -> list[str]:
    words = text.split()
    n = max(1, n)
    chunk_size = max(1, len(words) // n)
    chunks = []
    for i in range(0, len(words), chunk_size):
        chunks.append(" ".join(words[i:i + chunk_size]))
        if len(chunks) == n:  # dokładnie n części
            break
    # jeśli za mało, dopchnij ostatnią częścią
    while len(chunks) < n:
        chunks.append("")
    return chunks

# ---------- 7) TTS – męski, płynny (espeak-ng) ----------
def tts_male_to_mp3(text: str, mp3_path="voice.mp3") -> float:
    try:
        subprocess.run(["espeak-ng", "--version"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        wav = "voice.wav"
        # en-us+m7 – męski, szybkość 165, pitch 52 (naturalniej niż standard)
        subprocess.run(
            ["espeak-ng", "-v", "en-us+m7", "-s", "165", "-p", "52", "-w", wav, text],
            check=True
        )
        subprocess.run(
            ["ffmpeg", "-y", "-i", wav, "-ar", "44100", "-ac", "2", mp3_path],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        try: os.remove(wav)
        except: pass
    except Exception:
        # Fallback do gTTS
        from gtts import gTTS
        gTTS(text=text, lang="en").save(mp3_path)

    # czas trwania audio
    aud = AudioFileClip(mp3_path)
    dur = float(aud.duration)
    aud.close()
    return dur

# ---------- 8) BUDOWA WIDEO ----------
def build_video(frames: list[Image.Image], title: str, price: str, script_txt: str, voice_mp3: str, out_path="short.mp4"):
    # Load audio i dobierz długość klipów tak, by wideo = audio (lub TARGET_SECONDS, co większe)
    audio = AudioFileClip(voice_mp3)
    target = max(TARGET_SECONDS, audio.duration)
    n = max(MIN_IMGS, min(MAX_IMGS, len(frames))) or MIN_IMGS
    frames = frames[:n]
    chunks = split_into_chunks(script_txt, n)

    # czas na jeden kadr
    per = target / n
    per = max(4.5, per)  # min ~4.5 s na kadr

    # złożenie
    clips = []
    for i in range(n):
        frame = overlay(frames[i], title, price, chunks[i])
        arr = np.array(frame)
        clip = ImageClip(arr).set_duration(per).set_position("center")
        clips.append(clip)

    seq = concatenate_videoclips(clips, method="compose").set_fps(30)
    # dopasuj dokładnie do długości audio
    if seq.duration < audio.duration:
        # przedłuż ostatni kadr o różnicę
        delta = audio.duration - seq.duration
        last = clips[-1].set_duration(clips[-1].duration + delta)
        clips[-1] = last
        seq = concatenate_videoclips(clips, method="compose").set_fps(30)

    seq = seq.set_audio(audio)
    seq.write_videofile(out_path, codec="libx264", audio_codec="aac", fps=30)
    audio.close()
    return out_path

# ---------- 9) GŁÓWNY PRZEPŁYW ----------
def main():
    url = pick_aliexpress_url()
    html = get(url)
    meta = parse_from_page(html, url)

    imgs = meta["images"][:8]  # najpierw z samej strony
    if len(imgs) < MIN_IMGS:
        need = MIN_IMGS - len(imgs)
        imgs += ddg_images(meta["title"], want=need + 2)

    frames = prepare_images(imgs)
    if len(frames) < MIN_IMGS:
        # ostateczny awaryjny filler
        r = requests.get("https://picsum.photos/1080/1920", timeout=20)
        frames += [Image.open(io.BytesIO(r.content)).convert("RGB")]
        frames = [frames[0]] * MAX_IMGS

    narr = script(meta["title"], meta["price"])
    voice_len = tts_male_to_mp3(narr, "voice.mp3")
    build_video(frames, meta["title"], meta["price"], narr, "voice.mp3", out_path="short.mp4")

if __name__ == "__main__":
    main()
