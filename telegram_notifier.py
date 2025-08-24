import logging
from typing import List, Dict, Optional, Set
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.error import TelegramError
import asyncio
import json
import os

logger = logging.getLogger(__name__)

class TelegramNotifier:
    def __init__(self, bot_token: str, subscribers_file: str = "subscribers.json"):
        self.bot_token = bot_token
        self.bot = Bot(token=bot_token)
        self.subscribers_file = subscribers_file
        self.subscribers = self._load_subscribers()
        self.application = None
    
    def _load_subscribers(self) -> Set[int]:
        """Load subscribers from JSON file"""
        if os.path.exists(self.subscribers_file):
            try:
                with open(self.subscribers_file, 'r') as f:
                    data = json.load(f)
                    subscribers = set(data.get('subscribers', []))
                    logger.info(f"Loaded {len(subscribers)} subscriber(s) from {self.subscribers_file}")
                    return subscribers
            except Exception as e:
                logger.error(f"Error loading subscribers: {e}")
        return set()
    
    def _save_subscribers(self):
        """Save subscribers to JSON file"""
        try:
            with open(self.subscribers_file, 'w') as f:
                json.dump({'subscribers': list(self.subscribers)}, f, indent=2)
            logger.debug(f"Saved {len(self.subscribers)} subscriber(s) to {self.subscribers_file}")
        except Exception as e:
            logger.error(f"Error saving subscribers: {e}")
        
    async def setup_handlers(self):
        self.application = Application.builder().token(self.bot_token).build()
        
        # Add command handlers
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("subscribe", self.subscribe_command))
        self.application.add_handler(CommandHandler("unsubscribe", self.unsubscribe_command))
        self.application.add_handler(CommandHandler("status", self.status_command))
        self.application.add_handler(CommandHandler("check", self.check_command))
        
        return self.application
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        welcome_message = (
            "🤖 Welcome to Einbürgerungstest Appointment Bot!\n\n"
            "I will notify you when new appointments become available.\n\n"
            "Commands:\n"
            "/subscribe - Subscribe to notifications\n"
            "/unsubscribe - Unsubscribe from notifications\n"
            "/status - Check subscription status\n"
            "/check - Manually check for appointments\n"
            "/help - Show detailed help information"
        )
        await update.message.reply_text(welcome_message)
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_message = (
            "📚 *Einbürgerungstest Bot Help*\n\n"
            "*What this bot does:*\n"
            "• Checks all 12 VHS locations in Berlin every minute\n"
            "• Notifies you when appointments become available\n"
            "• Shows which VHS locations have slots\n\n"
            
            "*Commands:*\n"
            "`/subscribe` - Start receiving notifications\n"
            "`/unsubscribe` - Stop receiving notifications\n"
            "`/status` - Shows if you're subscribed and when each location was last checked\n"
            "`/check` - Manually check all locations right now\n"
            "`/help` - Show this help message\n\n"
            
            "*How to book when notified:*\n"
            "1. Go to the booking page\n"
            "2. Find the VHS location from the notification\n"
            "3. Click 'An diesem Standort einen Termin buchen'\n"
            "4. Select your appointment\n\n"
            
            "*Locations monitored:*\n"
            "• Treptow-Köpenick\n"
            "• City West\n"
            "• Friedrichshain-Kreuzberg\n"
            "• Lichtenberg\n"
            "• Marzahn-Hellersdorf\n"
            "• Mitte - Antonstraße\n"
            "• Neukölln\n"
            "• Reinickendorf\n"
            "• Spandau\n"
            "• Steglitz-Zehlendorf\n"
            "• Tempelhof-Schöneberg\n\n"
            
            "⚡ *Tip:* Appointments go fast! Book immediately when notified."
        )
        await update.message.reply_text(help_message, parse_mode='Markdown')
    
    async def subscribe_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        if chat_id not in self.subscribers:
            self.subscribers.add(chat_id)
            self._save_subscribers()  # Save after adding
            await update.message.reply_text(
                "✅ You've been subscribed to appointment notifications!\n"
                "I'll notify you as soon as new appointments become available."
            )
            logger.info(f"New subscriber: {chat_id}")
        else:
            await update.message.reply_text("You're already subscribed!")
    
    async def unsubscribe_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        if chat_id in self.subscribers:
            self.subscribers.discard(chat_id)
            self._save_subscribers()  # Save after removing
            await update.message.reply_text("You've been unsubscribed from notifications.")
            logger.info(f"Unsubscribed: {chat_id}")
        else:
            await update.message.reply_text("You're not subscribed.")
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        
        # Get bot instance to access location check times
        bot_instance = context.bot_data.get('bot_instance')
        
        if chat_id in self.subscribers:
            status_msg = (
                "📊 *Status*\n"
                f"✅ Subscribed to notifications\n"
                f"👥 Total subscribers: {len(self.subscribers)}\n"
                f"🔄 Checking every minute\n\n"
            )
            
            # Add location check times if available
            if bot_instance and hasattr(bot_instance, 'location_last_checked') and bot_instance.location_last_checked:
                status_msg += "*Last checked:*\n"
                from datetime import datetime
                now = datetime.now()
                
                for location, check_time in sorted(bot_instance.location_last_checked.items()):
                    try:
                        check_dt = datetime.fromisoformat(check_time)
                        seconds_ago = (now - check_dt).total_seconds()
                        
                        if seconds_ago < 60:
                            time_str = f"{int(seconds_ago)}s ago"
                        elif seconds_ago < 3600:
                            time_str = f"{int(seconds_ago/60)}m ago"
                        else:
                            time_str = f"{int(seconds_ago/3600)}h ago"
                        
                        # Truncate long location names
                        location_short = location[:30] + "..." if len(location) > 30 else location
                        status_msg += f"• {location_short}: {time_str}\n"
                    except:
                        pass
            else:
                status_msg += "\n_No checks completed yet_"
        else:
            status_msg = (
                "📊 *Status*\n"
                "❌ Not subscribed to notifications\n"
                "Use /subscribe to start receiving notifications"
            )
        
        await update.message.reply_text(status_msg, parse_mode='Markdown')
    
    async def check_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        # This will be connected to the appointment checker
        await update.message.reply_text(
            "🔍 Checking for appointments...\n"
            "This feature will be activated when the bot starts monitoring."
        )
    
    async def send_appointment_notification(self, appointments: List[Dict]):
        if not appointments:
            return
        
        message = "🎉 *Neue Termine verfügbar! / New Appointments Available!*\n\n"
        
        # Get unique locations
        locations = set()
        for apt in appointments:
            locations.add(apt.get('location_name', 'Unknown'))
        
        message += f"Appointments available at {len(locations)} location(s):\n\n"
        
        # List locations with slots
        for location in sorted(locations):
            message += f"✅ *{location}*\n"
        
        message += "\n📝 *How to book:*\n"
        message += "1. Go to: https://service.berlin.de/dienstleistung/351180/\n"
        message += "2. Find the Volkshochschule location mentioned above\n"
        message += "3. Click 'An diesem Standort einen Termin buchen'\n"
        message += "4. Select your appointment date\n\n"
        message += "⏰ *Book quickly before they're gone!*"
        
        # Send to all subscribers
        for chat_id in self.subscribers.copy():
            try:
                await self.bot.send_message(
                    chat_id=chat_id,
                    text=message,
                    parse_mode='Markdown',
                    disable_web_page_preview=True
                )
                logger.info(f"Notification sent to {chat_id}")
            except TelegramError as e:
                logger.error(f"Failed to send to {chat_id}: {e}")
                # Remove invalid chat IDs
                if "chat not found" in str(e).lower():
                    self.subscribers.discard(chat_id)
    
    async def send_status_update(self, status: str, error: Optional[str] = None):
        if error:
            message = f"⚠️ Bot Status Update:\n{status}\nError: {error}"
        else:
            message = f"ℹ️ Bot Status Update:\n{status}"
        
        for chat_id in self.subscribers.copy():
            try:
                await self.bot.send_message(chat_id=chat_id, text=message)
            except TelegramError as e:
                logger.error(f"Failed to send status to {chat_id}: {e}")
    
    def get_subscribers_count(self) -> int:
        return len(self.subscribers)
    
    def add_subscriber(self, chat_id: int):
        self.subscribers.add(chat_id)
        self._save_subscribers()  # Save after adding
        logger.info(f"Added subscriber via admin: {chat_id}")