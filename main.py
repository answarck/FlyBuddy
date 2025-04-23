from fastapi import FastAPI, Request
from contextlib import asynccontextmanager
import httpx
import os
import sqlite3
from dotenv import load_dotenv
import json

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
WEBHOOK_URL = os.getenv("WEBHOOK_URL") + "/webhook"
client = httpx.AsyncClient()

help_message = """
✈️ *FlyBuddy* - Your Personal Flight Assistant

Welcome! I can help you find and book flights with ease.
Use the buttons below to get started!
"""

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Set webhook when application starts
    await client.get(f"{BASE_URL}/setWebhook", params={"url": WEBHOOK_URL})
    yield

app = FastAPI(lifespan=lifespan)

# Store user booking states
booking_state = {}

def get_main_menu_keyboard():
    return {
        "inline_keyboard": [
            [
                {"text": "🛫 Book Ticket", "callback_data": "book_ticket"},
                {"text": "❓ Help", "callback_data": "help"}
            ],
        ]
    }

def get_back_keyboard():
    return {
        "inline_keyboard": [
            [
                {"text": "◀️ Back to Main Menu", "callback_data": "main_menu"}
            ]
        ]
    }

@app.post("/webhook")
async def webhook(req: Request):
    data = await req.json()
    
    # Handle callback queries (button presses)
    if "callback_query" in data:
        return await handle_callback_query(data["callback_query"])
    
    # Handle regular messages
    elif "message" in data:
        message = data["message"]
        
        if "text" not in message:
            return {"ok": True}
            
        chat_id = message["chat"]["id"]
        text = message["text"]
        
        if text == "/start":
            await welcome_user(chat_id)
        elif chat_id in booking_state:
            await handle_booking_step(chat_id, text)
        else:
            # For any other message, show the main menu
            await client.post(f"{BASE_URL}/sendMessage", json={
                "chat_id": chat_id,
                "text": "What would you like to do?",
                "reply_markup": get_main_menu_keyboard(),
                "parse_mode": "Markdown"
            })
    
    return {"ok": True}

async def welcome_user(chat_id):
    await client.post(f"{BASE_URL}/sendMessage", json={
        "chat_id": chat_id,
        "text": f"✈️ *Welcome to FlyBuddy!*\n\nI'm your personal flight booking assistant. How can I help you today?",
        "reply_markup": get_main_menu_keyboard(),
        "parse_mode": "Markdown"
    })

async def handle_callback_query(callback_query):
    chat_id = callback_query["message"]["chat"]["id"]
    message_id = callback_query["message"]["message_id"]
    callback_data = callback_query["data"]
    
    # First, acknowledge the button press
    await client.post(f"{BASE_URL}/answerCallbackQuery", json={
        "callback_query_id": callback_query["id"]
    })
    
    if callback_data == "book_ticket":
        booking_state[chat_id] = {"step": "arrival"}
        await client.post(f"{BASE_URL}/editMessageText", json={
            "chat_id": chat_id,
            "message_id": message_id,
            "text": "🌍 *Flight Booking Started*\n\nPlease enter the *arrival airport code* (e.g., JFK, LAX):",
            "reply_markup": get_back_keyboard(),
            "parse_mode": "Markdown"
        })
    
    elif callback_data == "help":
        await client.post(f"{BASE_URL}/editMessageText", json={
            "chat_id": chat_id,
            "message_id": message_id,
            "text": """
✈️ *FlyBuddy Help*

*How to book a flight:*
1. Click on '🛫 Book Ticket'
2. Enter the arrival airport code
3. Enter the departure airport code
4. Select from available flights

*Airport codes examples:*
• JFK - New York
• LAX - Los Angeles
• LHR - London
• SIN - Singapore
• DXB - Dubai
""",
            "reply_markup": get_back_keyboard(),
            "parse_mode": "Markdown"
        })
    elif callback_data == "main_menu":
        booking_state.pop(chat_id, None)  # Clear any booking state
        await client.post(f"{BASE_URL}/editMessageText", json={
            "chat_id": chat_id,
            "message_id": message_id,
            "text": "What would you like to do?",
            "reply_markup": get_main_menu_keyboard(),
            "parse_mode": "Markdown"
        })
    
    elif callback_data.startswith("select_flight_"):
        flight_no = callback_data.replace("select_flight_", "")
        await client.post(f"{BASE_URL}/editMessageText", json={
            "chat_id": chat_id,
            "message_id": message_id,
            "text": f"✅ *Booking Confirmed!*\n\nYour flight *{flight_no}* has been booked successfully.\n\nThank you for using FlyBuddy!",
            "reply_markup": get_main_menu_keyboard(),
            "parse_mode": "Markdown"
        })
    
    return {"ok": True}

async def handle_booking_step(chat_id, text):
    step = booking_state[chat_id]["step"]
    
    if step == "arrival":
        booking_state[chat_id]["arrival"] = text.upper()
        booking_state[chat_id]["step"] = "departure"
        await client.post(f"{BASE_URL}/sendMessage", json={
            "chat_id": chat_id,
            "text": "✅ Arrival: *" + text.upper() + "*\n\nNow enter the *departure airport code* (e.g., JFK, LAX):",
            "reply_markup": get_back_keyboard(),
            "parse_mode": "Markdown"
        })
    
    elif step == "departure":
        booking_state[chat_id]["departure"] = text.upper()
        arrival = booking_state[chat_id]["arrival"]
        departure = text.upper()
        
        # Search for flights
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
            flight_buttons = []
            for flight_no, d_time, a_time in rows:
                flight_buttons.append([{
                    "text": f"✈️ {flight_no} | {departure} {d_time} → {arrival} {a_time}",
                    "callback_data": f"select_flight_{flight_no}"
                }])
            
            # Add back button at the bottom
            flight_buttons.append([{"text": "◀️ Back to Main Menu", "callback_data": "main_menu"}])
            
            await client.post(f"{BASE_URL}/sendMessage", json={
                "chat_id": chat_id,
                "text": f"🔍 *Available Flights*\n\nFrom *{departure}* to *{arrival}*\nPlease select a flight:",
                "reply_markup": {"inline_keyboard": flight_buttons},
                "parse_mode": "Markdown"
            })
        else:
            await client.post(f"{BASE_URL}/sendMessage", json={
                "chat_id": chat_id,
                "text": f"😔 *No flights found* from *{departure}* to *{arrival}*.\n\nPlease try different airports.",
                "reply_markup": get_main_menu_keyboard(),
                "parse_mode": "Markdown"
            })
        
        # Clear the booking state
        booking_state.pop(chat_id)
