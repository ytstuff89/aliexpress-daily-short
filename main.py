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
        "trending gadget aliexpress 2025",
        "viral aliexpress gadget",
        "useful cheap gadget aliexpress"
    ]

    for q in search_terms:
        url = f"https://duckduckgo.com/html/?q={q}+site:aliexpress.com+item"
        r = requests.get(url, headers={"User-Agent": USER_AGENT})
        soup = BeautifulSoup(r.text, "lxml")

        for a in soup.select("a.result__a"):
            link = a.get("href")
            if link and "aliexpress.com/item" in link:
                return link

    return "https://www.aliexpress.com/item/1005005145894174.html"

def scrape(url):
    r = requests.get(url, headers={"User-Agent": USER_AGENT})
    soup = BeautifulSoup(r.text, "lxml")

    title_tag = soup.find("title")
    if title_tag:
        title = title_tag.get_text().strip()[:60]
    else:
        title = "AliExpress Gadget"

    imgs = []
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if src and src.startswith("http") and ("jpg" in src or "png" in src):
            imgs.append(src)
            if len(imgs) >= 3:
                break

    if not imgs:
        imgs = ["https://i.imgur.com/ZK8Qp5O.jpeg"]

    price_match = re.search(r"\d+\.\d+|\d+", soup.text)
    price = price_match.group(0) if price_match else "Unknown"

    return title, price, imgs

def make_video(title, price, imgs):
    voice = gTTS(text=f"{title}. Price {price} dollars.", lang="en", tld="com")
    voice.save("voice.mp3")
    audio = AudioFileClip("voice.mp3")

    clips = []
    for img in imgs:
        data = requests.get(img, headers={"User-Agent": USER_AGENT}).content
        with open("img.jpg", "wb") as f:
            f.write(data)

        pic = ImageClip("img.jpg").set_duration(2).fx(resize, height=1920).on_color(size=(1080,1920))
        txt = TextClip(title, fontsize=60, font="Arial-Bold", color="white") \
                .set_position(("center","bottom")).set_duration(2)

        clips.append(CompositeVideoClip([pic, txt]))

    final = concatenate_videoclips(clips).set_audio(audio)
    final.write_videofile("short.mp4", fps=30)

url = find_product()
title, price, imgs = scrape(url)
make_video(title, price, imgs)
print("DONE")
