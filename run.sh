#!/bin/bash
echo "🔧 Встановлюємо віртуальне середовище..."
python3 -m venv venv
source venv/bin/activate
echo "⬇️ Встановлюємо залежності..."
pip install --upgrade pip
pip install -r requirements.txt
echo "🚀 Запускаємо бота..."
python album04.py
