from telethon import TelegramClient, events
import os
import requests
from PIL import Image
from threading import Timer
import asyncio
import uuid

# === Telegram авторизація
api_id = 28067897
api_hash = '58562f6b38ee6197d65fc16de649b238'
client = TelegramClient('user_session', api_id, api_hash)

# === Make Webhook
MAKE_WEBHOOK_URL = 'https://hook.eu2.make.com/iaqn7i7659ktujenbzyh2oa75f4yxycu'

# === ImgBB API
IMGBB_API_KEY = '9296c54b2fa1ec1b305118958765026b'

# === Telegram канали
channels_to_monitor = ['lady_shopi', 'bottelethon']

# === Кеш для постів
media_groups = {}
pending_posts = {}
timers = {}
SAVE_DELAY = 30  # секунди

# === Завантаження JPG на ImgBB
def upload_to_imgbb(image_path):
    with open(image_path, "rb") as f:
        response = requests.post(
            "https://api.imgbb.com/1/upload",
            params={"key": IMGBB_API_KEY},
            files={"image": f}
        )
    if response.status_code == 200:
        return response.json()['data']['url']
    else:
        print("❌ ImgBB upload failed:", response.text)
        return None

# === Збереження картинки у JPG
def save_as_jpg(file, output_path):
    image = Image.open(file)
    rgb_image = image.convert('RGB')
    rgb_image.save(output_path, "JPEG")

# === Відправка в Make
def send_to_make(post_data):
    try:
        response = requests.post(MAKE_WEBHOOK_URL, json=post_data)
        print(f"📤 Відправлено: {response.status_code} {response.text}")
    except Exception as e:
        print("❌ Помилка при надсиланні в Make:", e)

# === Обробка готового посту
async def finalize_post(group_id):
    post = pending_posts.pop(group_id, {})
    timers.pop(group_id, None)

    if not post.get("photos") and not post.get("caption"):
        return  # пустий пост

    media_urls = []
    for photo_path in post.get("photos", []):
        url = upload_to_imgbb(photo_path)
        if url:
            media_urls.append(url)

    payload = {
        "chat_id": post.get("chat_id"),
        "caption": post.get("caption", ""),
        "source": post.get("source", ""),
        "media": media_urls
    }

    send_to_make(payload)

# === Запуск таймера очікування
def start_timer(group_id):
    if group_id in timers:
        timers[group_id].cancel()
    timers[group_id] = Timer(SAVE_DELAY, lambda: asyncio.run(finalize_post(group_id)))
    timers[group_id].start()

# === Обробка повідомлення
@client.on(events.NewMessage(chats=channels_to_monitor))
async def handler(event):
    msg = event.message
    group_id = msg.grouped_id or str(uuid.uuid4())

    if group_id not in pending_posts:
        pending_posts[group_id] = {
            "photos": [],
            "caption": "",
            "source": f"https://t.me/{event.chat.username}" if event.chat else "",
            "chat_id": event.chat_id
        }

    # === Якщо це фото
    if msg.photo:
        file_path = f"temp_{uuid.uuid4().hex}.jpg"
        await msg.download_media(file_path)
        save_as_jpg(file_path, file_path)
        pending_posts[group_id]["photos"].append(file_path)

    # === Якщо це текст
    if msg.text and not msg.media:
        pending_posts[group_id]["caption"] = msg.text

    # === Якщо фото і текст в одному — відправляємо відразу
    if msg.photo and msg.text:
        await finalize_post(group_id)
    else:
        start_timer(group_id)

# === Старт клієнта
print("🤖 Бот запущено. Слухає:", channels_to_monitor)
client.start()
client.run_until_disconnected()
