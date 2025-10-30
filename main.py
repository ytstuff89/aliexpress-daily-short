import os, re, random, time, smtplib, ssl, textwrap, requests
from datetime import datetime
from email.message import EmailMessage
from bs4 import BeautifulSoup
from gtts import gTTS
from moviepy.editor import ImageClip, AudioFileClip, CompositeVideoClip, concatenate_videoclips, TextClip
from moviepy.video.fx import resize

USER_AGENT = "Mozilla/5.0"

def find_product():
    search_terms = [
        "cool gadget from aliexpress",
        "trending gadget 2025 aliexpress",
        "new tech gadget cheap"
    ]

    q = random.choice(search_terms)
    url = f"https://duckduckgo.com/html/?q={q}+site:aliexpress.com+item"

    r = requests.get(url, headers={"User-Agent": USER_AGENT})
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")

    for a in soup.select("a.result__a"):
        link = a.get("href")
        if "aliexpress.com/item" in link:
            return link
    return None

def scrape(url):
    r = requests.get(url, headers={"User-Agent": USER_AGENT})
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")

    title = soup.find("title").get_text().strip()[:60]

    imgs = []
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if "jpg" in src or "png" in src:
            if "http" not in src:
                continue
            imgs.append(src)
            if len(imgs) >= 3:
                break

    price = "Unknown"
    match = re.search(r"\d+\.\d+|\d+", soup.text)
    if match:
        price = match.group(0)

    return title, price, imgs

def make_video(title, price, imgs):
    clips = []

    voice = gTTS(
        text=f"{title}. Price {price} dollars. Check the link in description.",
        lang="en",
        tld="com"
    )
    voice.save("voice.mp3")
    audio = AudioFileClip("voice.mp3")

    for img in imgs:
        data = requests.get(img, headers={"User-Agent": USER_AGENT}).content
        fn = "img.jpg"
        with open(fn, "wb") as f:
            f.write(data)

        pic = ImageClip(fn).set_duration(2).fx(resize, height=1920).on_color(size=(1080,1920))
        txt = TextClip(
            title, fontsize=60, font="Arial-Bold", color="white"
        ).set_position(("center","bottom")).set_duration(2)

        clips.append(CompositeVideoClip([pic, txt]))

    final = concatenate_videoclips(clips).set_audio(audio)
    final.write_videofile("short.mp4", fps=30)

prod = find_product()
title, price, imgs = scrape(prod)
make_video(title, price, imgs)

print("DONE")
