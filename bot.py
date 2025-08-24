#!/usr/bin/env python3

import os
import asyncio
import logging
from datetime import datetime
from typing import Optional, Set
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from appointment_checker import AppointmentChecker
from telegram_notifier import TelegramNotifier

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class EinburgerungstestBot:
    def __init__(self):
        load_dotenv()
        
        self.bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        if not self.bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN not found in environment variables")
        
        self.check_interval = int(os.getenv('CHECK_INTERVAL_MINUTES', '5'))
        
        # Initialize components
        self.appointment_checker = AppointmentChecker()
        self.telegram_notifier = TelegramNotifier(self.bot_token)
        self.scheduler = AsyncIOScheduler()
        
        # Track previously seen appointments to avoid duplicate notifications
        self.seen_locations_with_slots = set()
        self.last_check_result = None
        self.location_last_checked = {}
        
        # Add default chat ID if provided
        default_chat_id = os.getenv('TELEGRAM_CHAT_ID')
        if default_chat_id:
            self.telegram_notifier.add_subscriber(int(default_chat_id))
            logger.info(f"Added default chat ID: {default_chat_id}")
    
    async def check_and_notify(self):
        try:
            logger.info("Checking for appointments...")
            result = self.appointment_checker.check_appointments()
            
            if result.get('error'):
                logger.error(f"Error checking appointments: {result['error']}")
                # Only notify subscribers of persistent errors
                if self.last_check_result and self.last_check_result.get('error'):
                    await self.telegram_notifier.send_status_update(
                        "Bot is experiencing issues checking appointments",
                        result['error']
                    )
            else:
                appointments = result.get('appointments', [])
                
                # Update location check times
                if result.get('location_check_times'):
                    self.location_last_checked = result['location_check_times']
                
                if appointments:
                    # Group appointments by location
                    locations_with_slots = set()
                    for apt in appointments:
                        locations_with_slots.add(apt.get('location_name'))
                    
                    # Find new locations with slots
                    new_locations = locations_with_slots - self.seen_locations_with_slots
                    
                    if new_locations:
                        logger.info(f"Found appointments at {len(new_locations)} new location(s)!")
                        # Filter appointments to only those from new locations
                        new_appointments = [apt for apt in appointments if apt.get('location_name') in new_locations]
                        await self.telegram_notifier.send_appointment_notification(new_appointments)
                        # Update seen locations
                        self.seen_locations_with_slots = locations_with_slots
                    else:
                        logger.info(f"Appointments still available at {len(locations_with_slots)} location(s), already notified")
                else:
                    logger.info("No appointments available at any location")
                    # Clear seen locations if none are available
                    if self.seen_locations_with_slots:
                        self.seen_locations_with_slots.clear()
                        logger.info("Cleared seen locations cache")
            
            self.last_check_result = result
            
        except Exception as e:
            logger.error(f"Unexpected error in check_and_notify: {e}", exc_info=True)
    
    async def manual_check(self, update, context):
        """Handle manual check command from Telegram"""
        await update.message.reply_text("🔍 Checking all VHS locations for appointments...")
        
        result = self.appointment_checker.check_appointments()
        
        if result.get('errors'):
            error_msg = "\n".join(result['errors'][:3])
            await update.message.reply_text(
                f"⚠️ Some locations could not be checked:\n{error_msg}"
            )
        
        appointments = result.get('appointments', [])
        if appointments:
            # Group by location
            by_location = {}
            for apt in appointments:
                location = apt.get('location_name', 'Unknown')
                if location not in by_location:
                    by_location[location] = []
                by_location[location].append(apt)
            
            message = f"✅ Found {len(appointments)} appointment(s) at {len(by_location)} location(s):\n\n"
            
            for location, location_apts in list(by_location.items())[:3]:
                message += f"📍 {location}:\n"
                for apt in location_apts[:2]:
                    message += f"  📅 {apt.get('date', 'Unknown date')}\n"
                if len(location_apts) > 2:
                    message += f"  ... +{len(location_apts) - 2} more\n"
            
            if len(by_location) > 3:
                message += f"\n... and {len(by_location) - 3} more locations"
            
            message += "\n\n📝 Visit https://service.berlin.de/dienstleistung/351180/ to book"
        else:
            message = "❌ No appointments currently available at any VHS location"
        
        await update.message.reply_text(message)
    
    async def start(self):
        logger.info("Starting Einbürgerungstest Bot...")
        
        # Setup Telegram bot handlers
        application = await self.telegram_notifier.setup_handlers()
        
        # Pass bot instance to application for status command
        application.bot_data['bot_instance'] = self
        
        # Override the check command with our implementation
        from telegram.ext import CommandHandler
        application.add_handler(CommandHandler("check", self.manual_check), group=1)
        
        # Schedule periodic checks
        self.scheduler.add_job(
            self.check_and_notify,
            IntervalTrigger(minutes=self.check_interval),
            id='appointment_check',
            name='Check for appointments',
            replace_existing=True
        )
        
        # Start scheduler
        self.scheduler.start()
        logger.info(f"Scheduler started - checking every {self.check_interval} minutes")
        
        # Run initial check
        await self.check_and_notify()
        
        # Start Telegram bot
        logger.info("Starting Telegram bot...")
        await application.initialize()
        await application.start()
        await application.updater.start_polling()
        
        logger.info("Bot is running! Press Ctrl+C to stop.")
        
        try:
            # Keep the bot running
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("Shutting down bot...")
        finally:
            # Cleanup
            self.scheduler.shutdown()
            self.appointment_checker.close()
            await application.updater.stop()
            await application.stop()
            await application.shutdown()
            logger.info("Bot shutdown complete")

async def main():
    bot = EinburgerungstestBot()
    await bot.start()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)