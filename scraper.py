#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import re
import shutil
import traceback
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
import cv2
import boto3
from botocore.config import Config

# ==== 环境变量 ====
R2_ACCOUNT_ID = os.environ.get("R2_ACCOUNT_ID")
R2_ACCESS_KEY_ID = os.environ.get("R2_ACCESS_KEY_ID")
R2_SECRET_ACCESS_KEY = os.environ.get("R2_SECRET_ACCESS_KEY")
R2_BUCKET_NAME = os.environ.get("R2_BUCKET_NAME")

# ==== 配置 ====
BRIGHTNESS_THRESHOLD = 130
BATCH_SIZE = 100
TEMP_DIR = "temp_images"
GALLERIES_FILE = "galleries.json"
PROGRESS_FILE = "progress.json"
IMAGES_JSON_FILE = "images.json"  # 仓库根目录

# ==== 请求头 ====
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://img.hyun.cc/",
}


def load_json(filepath: str, default=None):
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    return default if default is not None else []


def save_json(filepath: str, data):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_r2_client():
    return boto3.client(
        "s3",
        endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=R2_ACCESS_KEY_ID,
        aws_secret_access_key=R2_SECRET_ACCESS_KEY,
        config=Config(signature_version="s3v4"),
        region_name="auto"
    )


def upload_to_r2(local_path: str, r2_key: str, client) -> bool:
    try:
        ext = os.path.splitext(local_path)[1].lower()
        content_types = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
            ".gif": "image/gif",
        }
        content_type = content_types.get(ext, "application/octet-stream")
        
        client.upload_file(
            local_path,
            R2_BUCKET_NAME,
            r2_key,
            ExtraArgs={"ContentType": content_type}
        )
        print(f"☁️ 已上传: {r2_key}")
        return True
    except Exception as e:
        print(f"❌ 上传失败 {r2_key}: {e}")
        return False


def get_next_gallery():
    galleries = load_json(GALLERIES_FILE, [])
    progress = load_json(PROGRESS_FILE, {"completed": []})
    completed = set(progress.get("completed", []))
    
    for gallery in galleries:
        if gallery["url"] not in completed:
            return gallery
    return None


def mark_completed(url: str):
    progress = load_json(PROGRESS_FILE, {"completed": []})
    if url not in progress["completed"]:
        progress["completed"].append(url)
    save_json(PROGRESS_FILE, progress)


def scrape_images(url: str) -> list[dict]:
    print(f"🌐 正在爬取: {url}")
    
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        resp.encoding = 'utf-8'
    except Exception as e:
        print(f"❌ 请求页面失败: {e}")
        return []
    
    soup = BeautifulSoup(resp.text, "lxml")
    images = []
    links = soup.find_all("a", {"data-fancybox": True})
    
    for idx, link in enumerate(links, 1):
        href = link.get("href", "")
        if href and href.startswith("http"):
            img_tag = link.find("img")
            data_src = img_tag.get("data-src", href) if img_tag else href
            ext_match = re.search(r'\.(jpg|jpeg|png|webp|gif)$', data_src, re.I)
            ext = ext_match.group(1).lower() if ext_match else "jpg"
            
            images.append({"url": href, "index": idx, "ext": ext})
    
    print(f"✅ 找到 {len(images)} 张图片")
    return images


def download_image(url: str, save_path: str) -> bool:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=60, stream=True)
        resp.raise_for_status()
        with open(save_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except Exception as e:
        print(f"❌ 下载失败 {url}: {e}")
        return False


def get_image_theme(path: str, threshold=BRIGHTNESS_THRESHOLD) -> str | None:
    try:
        img = cv2.imread(path)
        if img is None:
            return None
        if img.shape[1] < 10 or img.shape[0] < 10:
            return None
        
        img = cv2.resize(img, (100, 100))
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        avg_l = lab[:, :, 0].mean()
        
        theme = "dark" if avg_l < threshold else "light"
        print(f"🖼️ {os.path.basename(path)} → L={avg_l:.1f} → {theme}")
        return theme
    except Exception as e:
        print(f"❌ 分析失败: {e}")
        return None


def process_gallery(gallery: dict):
    url = gallery["url"]
    folder_name = gallery["folder"]
    
    print(f"\n{'='*50}")
    print(f"📂 处理: {folder_name}")
    print(f"{'='*50}\n")
    
    temp_folder = os.path.join(TEMP_DIR, folder_name)
    os.makedirs(temp_folder, exist_ok=True)
    
    images = scrape_images(url)
    if not images:
        return False
    
    r2_client = get_r2_client()
    
    # 读取本地 images.json
    all_images = load_json(IMAGES_JSON_FILE, [])
    print(f"📋 现有记录: {len(all_images)} 条")
    
    new_count = 0
    for img_info in images[:BATCH_SIZE]:
        idx = img_info["index"]
        ext = img_info["ext"]
        filename = f"{idx:02d}.{ext}"
        local_path = os.path.join(temp_folder, filename)
        
        print(f"\n📥 下载 {idx}/{len(images)}...")
        
        if not download_image(img_info["url"], local_path):
            continue
        
        theme = get_image_theme(local_path) or "light"
        r2_key = f"{folder_name}/{filename}"
        
        # 追加记录
        all_images.append({"name": r2_key, "theme": theme})
        new_count += 1
        
        # 上传到 R2
        upload_to_r2(local_path, r2_key, r2_client)
    
    # 保存 images.json 到仓库
    save_json(IMAGES_JSON_FILE, all_images)
    
    print(f"\n✅ 完成: {folder_name}")
    print(f"📊 新增 {new_count} 张，总计 {len(all_images)} 条")
    
    shutil.rmtree(temp_folder, ignore_errors=True)
    return True


def main():
    print("🚀 开始运行")
    os.makedirs(TEMP_DIR, exist_ok=True)
    
    gallery = get_next_gallery()
    if gallery is None:
        print("\n🎉 所有图仓已处理完成!")
        return
    
    if process_gallery(gallery):
        mark_completed(gallery["url"])
    
    shutil.rmtree(TEMP_DIR, ignore_errors=True)
    print("\n🏁 结束")


if __name__ == "__main__":
    main()
