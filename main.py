from fastapi import FastAPI, Request
from contextlib import asynccontextmanager
import httpx
import os
import sqlite3
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
WEBHOOK_URL = os.getenv("WEBHOOK_URL") + "/webhook"
client = httpx.AsyncClient()

help_message = """
✈️ FlyBuddy Help Menu
Welcome to FlyBuddy — your personal flight booking assistant!
Here's what you can do:

🛫 Book Ticket
Tap "Book Ticket" to start the flight booking process. I'll guide you step-by-step to collect your travel details.

❓ Help
Need help at any point? Just tap "Help" or type /help.

ℹ️ Commands
    /start – Restart the bot
    /book  - To Start booking
    /help  – Show this help message
"""

@asynccontextmanager
async def lifespan(app: FastAPI):
    await client.get(f"{BASE_URL}/setWebhook", params={"url": WEBHOOK_URL})
    yield

app = FastAPI(lifespan=lifespan)
booking_state = {}

@app.post("/webhook")
async def webhook(req: Request):
    data = await req.json()
    chat_id = data['message']['chat']['id']
    text = data['message']['text']
    
    if text == "/start" or text == "/help":
        await client.post(f"{BASE_URL}/sendMessage", json={
            "chat_id": chat_id,
            "text": help_message,
        })
        booking_state.pop(chat_id, None)
    elif text == "/book":
        booking_state[chat_id] = {"step": "arrival"}
        await client.post(f"{BASE_URL}/sendMessage", json={
            "chat_id": chat_id,
            "text": "Please enter the arrival airport code.",
        })
    elif chat_id in booking_state:
        step = booking_state[chat_id]["step"]
        if step == "arrival":
            booking_state[chat_id]["arrival"] = text.upper()
            booking_state[chat_id]["step"] = "departure"
            await client.post(f"{BASE_URL}/sendMessage", json={
                "chat_id": chat_id,
                "text": "Got it! Now enter the departure airport code.",
            })
        elif step == "departure":  # Fixed the indentation here
            booking_state[chat_id]["departure"] = text.upper()
            arrival = booking_state[chat_id]["arrival"]
            departure = booking_state[chat_id]["departure"]
            conn = sqlite3.connect("bo.db")
            cursor = conn.cursor()
            cursor.execute("""
                SELECT flight_no, departure_time, arrival_time
                FROM flights
                WHERE arrival = ? AND departure = ?
            """, (arrival, departure))
            rows = cursor.fetchall()
            conn.close()
            if rows:
                flights = "\n".join(
                f"✈️ {flight_no} | Dep: {d_time} | Arr: {a_time}"
                    for flight_no, d_time, a_time in rows
                )
                response = f"Flights from {departure} to {arrival}:\n\n{flights}"
            else:
                response = f"No flights found from {departure} to {arrival}."
            await client.post(f"{BASE_URL}/sendMessage", json={
                "chat_id": chat_id,
                "text": response,
            })
            booking_state.pop(chat_id)
    else:
        await client.post(f"{BASE_URL}/sendMessage", json={
            "chat_id": chat_id,
            "text": "I didn't understand that. Use /book to start booking or /help for assistance.",
        })
