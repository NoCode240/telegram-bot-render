from telethon import TelegramClient, events
from PIL import Image
import os
import uuid
import requests
import asyncio
from threading import Timer

# === Telegram авторизація
api_id = 28067897
api_hash = '58562f6b38ee6197d65fc16de649b238'

# === Make Webhook і ImgBB API
MAKE_WEBHOOK_URL = 'https://hook.eu2.make.com/iaqn7i7659ktujenbzyh2oa75f4yxycu'
IMGBB_API_KEY = '9296c54b2fa1ec1b305118958765026b'

# === Тимчасова папка
IMG_DIR = "img_to_web"
os.makedirs(IMG_DIR, exist_ok=True)

channels_to_monitor = ['lady_shopi', 'bottelethon']
pending_messages = {}
pending_timers = {}
media_groups = {}
media_group_chat_map = {}

BUFFER_DELAY = 30  # секунд
ALBUM_DELAY = 3  # секунд

client = TelegramClient('user_session', api_id, api_hash)
client.start()
main_loop = asyncio.get_event_loop()


def convert_to_jpg(photo_path):
    unique_name = f"{uuid.uuid4().hex}.jpg"
    output_path = os.path.join(IMG_DIR, unique_name)
    Image.open(photo_path).convert("RGB").save(output_path, "JPEG")
    os.remove(photo_path)
    return output_path


def upload_to_imgbb(jpg_path):
    if jpg_path.startswith("http"):
        return jpg_path
    with open(jpg_path, 'rb') as file:
        response = requests.post(
            "https://api.imgbb.com/1/upload",
            params={"key": IMGBB_API_KEY},
            files={"image": file}
        )
    os.remove(jpg_path)
    if response.status_code == 200:
        return response.json()['data']['url']
    else:
        print("❌ ImgBB upload failed")
        return None


def send_to_make(caption, image_links, source, chat_id):
    data = {
        'caption': caption or '',
        'source': source or '',
        'chat_id': str(chat_id),
    }
    for i, url in enumerate(image_links):
        data[f'media[{i}]'] = url
    response = requests.post(MAKE_WEBHOOK_URL, data=data)
    print(f"📤 Відправлено {len(image_links)} JPG → {response.status_code}")


def flush_buffer(chat_id):
    messages = pending_messages.pop(chat_id, [])
    pending_timers.pop(chat_id, None)

    captions = []
    image_links = []
    source = None

    for mtype, content in messages:
        if mtype == 'text':
            captions.append(content['text'])
            source = content['source']
        elif mtype == 'photo':
            link = upload_to_imgbb(content['path'])
            if link:
                image_links.append(link)
                source = content['source']

    full_caption = "\n".join(captions).strip()
    send_to_make(full_caption, image_links, source, chat_id)


async def flush_album_async(grouped_id):
    messages = media_groups.pop(grouped_id, [])
    chat_id = media_group_chat_map.pop(grouped_id)
    captions = []
    image_links = []
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
            link = upload_to_imgbb(jpg)
            if link:
                image_links.append(link)

    full_caption = "\n".join(captions).strip()

    if full_caption:
        send_to_make(full_caption, image_links, source, chat_id)
    else:
        pending_messages.setdefault(chat_id, [])
        for link in image_links:
            pending_messages[chat_id].append(('photo', {'path': link, 'source': source, 'chat_id': chat_id}))

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

    pending_messages.setdefault(chat_id, [])

    if msg.photo:
        path = await msg.download_media()
        jpg = convert_to_jpg(path)
        pending_messages[chat_id].append(('photo', {'path': jpg, 'source': source, 'chat_id': chat_id}))
    elif msg.message:
        pending_messages[chat_id].append(('text', {'text': msg.message, 'source': source, 'chat_id': chat_id}))

    if chat_id in pending_timers:
        pending_timers[chat_id].cancel()
    pending_timers[chat_id] = Timer(BUFFER_DELAY, flush_buffer, [chat_id])
    pending_timers[chat_id].start()


print("🤖 Бот запущено. Слухає:", channels_to_monitor)
client.run_until_disconnected()
