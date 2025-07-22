from telethon import TelegramClient, events
from PIL import Image
import os
import uuid
import requests
import asyncio
import subprocess
from threading import Timer

# === Telegram авторизація
api_id = 28067897
api_hash = '58562f6b38ee6197d65fc16de649b238'

# === Make Webhook
MAKE_WEBHOOK_URL = 'https://hook.eu2.make.com/iaqn7i7659ktujenbzyh2oa75f4yxycu'

# === Шляхи
IMG_DIR = "C:/Users/volko/OneDrive/Desktop/NoCode/img_to_web_2"
GITHUB_RAW_BASE = "https://raw.githubusercontent.com/NoCode240/telegram-bot-render/main/img_to_web/"


os.makedirs(IMG_DIR, exist_ok=True)

channels_to_monitor = ['lady_shopi', 'bottelethon']

pending_messages = {}
pending_timers = {}
media_groups = {}
media_group_chat_map = {}
BUFFER_DELAY = 30
ALBUM_DELAY = 3

client = TelegramClient('user_session', api_id, api_hash)
client.start()
main_loop = asyncio.get_event_loop()


def convert_to_jpg(photo_path):
    unique_name = f"{uuid.uuid4().hex}.jpg"
    output_path = os.path.join(IMG_DIR, unique_name)
    Image.open(photo_path).convert("RGB").save(output_path, "JPEG")
    os.remove(photo_path)
    return unique_name


def git_push():
    try:
        subprocess.run(["git", "add", "."], cwd=IMG_DIR, check=True)
        commit_result = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=IMG_DIR)
        if commit_result.returncode != 0:
            subprocess.run(["git", "commit", "-m", "upload new jpg"], cwd=IMG_DIR, check=True)
            subprocess.run(["git", "push", "origin", "main"], cwd=IMG_DIR, check=True)
            print("✅ Нові JPG запушено на GitHub")
        else:
            print("ℹ️ Немає нових змін для commit/push")
    except subprocess.CalledProcessError as e:
        print(f"❌ Git push failed: {e}")


def cleanup_local_jpgs():
    try:
        count = 0
        for f in os.listdir(IMG_DIR):
            if f.endswith(".jpg"):
                os.remove(os.path.join(IMG_DIR, f))
                count += 1
        print(f"🧹 Очищено {count} JPG з диску")
    except Exception as e:
        print(f"❌ Помилка при очищенні JPG: {e}")


def send_to_make(caption, filenames, source, chat_id):
    media_links = [GITHUB_RAW_BASE + f for f in filenames]
    data = {
        'caption': caption or '',
        'source': source or '',
        'chat_id': str(chat_id),
        'media[]': media_links
    }
    response = requests.post(MAKE_WEBHOOK_URL, data=data)
    print(f"📤 Відправлено {len(media_links)} JPG → {response.status_code}")
    git_push()
    cleanup_local_jpgs()  # Очищення JPG після пушу


def flush_buffer(chat_id):
    messages = pending_messages.pop(chat_id, [])
    pending_timers.pop(chat_id, None)

    captions = []
    filenames = []
    source = None

    for mtype, content in messages:
        if mtype == 'text':
            captions.append(content['text'])
            source = content['source']
        elif mtype == 'photo':
            filenames.append(content['filename'])
            source = content['source']

    full_caption = "\n".join(captions).strip()
    send_to_make(full_caption, filenames, source, chat_id)


async def flush_album_async(grouped_id):
    messages = media_groups.pop(grouped_id, [])
    chat_id = media_group_chat_map.pop(grouped_id)
    captions = []
    filenames = []
    source = None

    for msg in messages:
        if not source:
            chat = await msg.get_chat()
            source = f"https://t.me/{chat.username}" if chat and chat.username else None
        if msg.message:
            captions.append(msg.message)
        if msg.photo:
            path = await msg.download_media()
            jpg = convert_to_jpg(path)
            filenames.append(jpg)

    full_caption = "\n".join(captions).strip()

    if full_caption:
        send_to_make(full_caption, filenames, source, chat_id)
    else:
        pending_messages.setdefault(chat_id, [])
        for fn in filenames:
            pending_messages[chat_id].append(('photo', {'filename': fn, 'source': source, 'chat_id': chat_id}))

        if chat_id in pending_timers:
            pending_timers[chat_id].cancel()
        pending_timers[chat_id] = Timer(BUFFER_DELAY, flush_buffer, [chat_id])
        pending_timers[chat_id].start()


def flush_album(grouped_id):
    asyncio.run_coroutine_threadsafe(flush_album_async(grouped_id), main_loop)


@client.on(events.NewMessage(chats=channels_to_monitor))
async def handle_message(event):
    msg = event.message
    chat = await event.get_chat()
    chat_id = msg.chat_id
    source = f"https://t.me/{chat.username}" if chat and chat.username else None

    if msg.grouped_id:
        gid = msg.grouped_id
        media_groups.setdefault(gid, []).append(msg)
        media_group_chat_map[gid] = chat_id
        if gid in pending_timers:
            pending_timers[gid].cancel()
        pending_timers[gid] = Timer(ALBUM_DELAY, flush_album, [gid])
        pending_timers[gid].start()
        return

    if msg.photo and msg.message:
        path = await msg.download_media()
        jpg = convert_to_jpg(path)
        send_to_make(msg.message, [jpg], source, chat_id)
        return

    pending_messages.setdefault(chat_id, [])

    if msg.photo:
        path = await msg.download_media()
        jpg = convert_to_jpg(path)
        pending_messages[chat_id].append(('photo', {'filename': jpg, 'source': source, 'chat_id': chat_id}))
    elif msg.message:
        pending_messages[chat_id].append(('text', {'text': msg.message, 'source': source, 'chat_id': chat_id}))

    if chat_id in pending_timers:
        pending_timers[chat_id].cancel()
    pending_timers[chat_id] = Timer(BUFFER_DELAY, flush_buffer, [chat_id])
    pending_timers[chat_id].start()


print("🤖 Бот запущено. Слухає:", channels_to_monitor)
client.run_until_disconnected()
