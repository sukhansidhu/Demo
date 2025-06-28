import os
import logging
import zipfile
import rarfile
import pyzipper
import subprocess
from uuid import uuid4
from config import Config
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)

# Initialize logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# User state management
user_states = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📁 Send me files to archive. Click 'Done' when finished!",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❓ Help", callback_data="help")]
        ])
    )

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    file = await update.message.effective_attachment.get_file()
    
    # Initialize user state
    if user_id not in user_states:
        user_states[user_id] = {
            'files': [],
            'temp_files': [],
            'current_file': None
        }
    
    # Download file
    file_ext = os.path.splitext(update.message.effective_attachment.file_name)[1]
    temp_file = os.path.join(Config.TMP_DIR, f"temp_{uuid4()}{file_ext}")
    await file.download_to_drive(temp_file)
    
    # Store file info
    user_states[user_id]['files'].append({
        'file_name': update.message.effective_attachment.file_name,
        'local_path': temp_file,
        'size': os.path.getsize(temp_file)
    })
    user_states[user_id]['temp_files'].append(temp_file)
    
    # Calculate total size
    total_size = sum(f['size'] for f in user_states[user_id]['files']) / (1024 * 1024)
    
    # Show action buttons
    keyboard = [
        [InlineKeyboardButton("📦 Make Archive", callback_data="make_archive")],
        [InlineKeyboardButton("✅ Done", callback_data="done")]
    ]
    await update.message.reply_text(
        f"✅ Received: {update.message.effective_attachment.file_name}\n"
        f"📦 Total files: {len(user_states[user_id]['files'])}\n"
        f"📊 Total size: {total_size:.2f} MB",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data
    
    if user_id not in user_states:
        user_states[user_id] = {'files': [], 'temp_files': []}
    
    # Archive workflow
    if data == "make_archive":
        if not user_states[user_id]['files']:
            await query.edit_message_text("❌ No files to archive!")
            return
            
        keyboard = [
            [InlineKeyboardButton("ZIP", callback_data="zip")],
            [InlineKeyboardButton("RAR", callback_data="rar")],
            [InlineKeyboardButton("7Z", callback_data="sevenz")]
        ]
        await query.edit_message_text(
            "Select archive type:",
            reply_markup=InlineKeyboardMarkup(keyboard)
    
    elif data in ["zip", "rar", "sevenz"]:
        user_states[user_id]['archive_type'] = data
        keyboard = [
            [InlineKeyboardButton("🔑 Set Password", callback_data="set_password")],
            [InlineKeyboardButton("⏩ Skip Password", callback_data="skip_password")]
        ]
        await query.edit_message_text(
            "Add password protection?",
            reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif data == "set_password":
        await query.edit_message_text("🔐 Enter password for archive:")
        user_states[user_id]['awaiting_password'] = True
    
    elif data == "skip_password":
        user_states[user_id]['password'] = None
        await create_archive(user_id, query.message)
    
    elif data == "done":
        if not user_states[user_id]['files']:
            await query.answer("No files received yet!")
            return
            
        keyboard = [
            [InlineKeyboardButton("📦 Make Archive", callback_data="make_archive")]
        ]
        total_size = sum(f['size'] for f in user_states[user_id]['files']) / (1024 * 1024)
        await query.edit_message_text(
            f"✅ Ready to archive {len(user_states[user_id]['files'])} files\n"
            f"📊 Total size: {total_size:.2f} MB",
            reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif data == "help":
        await query.edit_message_text(
            "🤖 Archive Bot Help:\n\n"
            "1. Send files one by one\n"
            "2. Click 'Done' when finished\n"
            "3. Choose archive format (ZIP/RAR/7Z)\n"
            "4. Add password if needed\n"
            "5. Receive your archive!\n\n"
            "Max files per archive: 20\n"
            "Max total size: 2GB"
        )

async def handle_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    password = update.message.text
    
    if user_id in user_states and 'awaiting_password' in user_states[user_id]:
        user_states[user_id]['password'] = password
        del user_states[user_id]['awaiting_password']
        await create_archive(user_id, update.message)

async def create_archive(user_id, message):
    state = user_states[user_id]
    archive_name = os.path.join(Config.TMP_DIR, f"archive_{uuid4()}.{state['archive_type']}")
    
    try:
        total_size = sum(f['size'] for f in state['files'])
        
        # Show progress message
        progress_msg = await message.reply_text("⏳ Creating archive... 0%")
        
        # Create archive based on type
        if state['archive_type'] == "zip":
            with pyzipper.AESZipFile(
                archive_name,
                'w',
                compression=pyzipper.ZIP_DEFLATED,
                encryption=pyzipper.WZ_AES
            ) as zipf:
                if state.get('password'):
                    zipf.setpassword(state['password'].encode())
                
                for i, file in enumerate(state['files']):
                    zipf.write(file['local_path'], arcname=file['file_name'])
                    # Update progress
                    progress = int((i + 1) / len(state['files']) * 100)
                    await progress_msg.edit_text(f"⏳ Creating archive... {progress}%")
        
        elif state['archive_type'] == "rar":
            # RAR creation using rar command
            cmd = ['rar', 'a', '-hp' + state['password'] if state.get('password') else '-ep', archive_name]
            cmd.extend([f['local_path'] for f in state['files']])
            subprocess.run(cmd, check=True)
        
        elif state['archive_type'] == "sevenz":
            # 7Z creation using 7z command
            cmd = ['7z', 'a', '-p' + state['password'] if state.get('password') else '', archive_name]
            cmd.extend([f['local_path'] for f in state['files']])
            subprocess.run(cmd, check=True)
        
        # Send archive to user
        with open(archive_name, 'rb') as archive_file:
            await message.reply_document(
                document=archive_file,
                caption=f"📦 {len(state['files'])} files archived" +
                        (f"\n🔐 Password: {state['password']}" if state.get('password') else "")
            )
        
        # Cleanup
        os.remove(archive_name)
        for file in state['temp_files']:
            if os.path.exists(file):
                os.remove(file)
        del user_states[user_id]
        await progress_msg.delete()
        
    except Exception as e:
        logger.error(f"Archive creation error: {str(e)}")
        await message.reply_text(f"❌ Error creating archive: {str(e)}")
        if os.path.exists(archive_name):
            os.remove(archive_name)

def main():
    # Create bot application
    application = Application.builder().token(Config.BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_file))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_password))
    
    # Start the bot
    if Config.ENVIRONMENT == "production":
        application.run_webhook(
            listen="0.0.0.0",
            port=Config.PORT,
            url_path=Config.BOT_TOKEN,
            webhook_url=f"{Config.WEBHOOK_URL}/{Config.BOT_TOKEN}"
        )
    else:
        application.run_polling()

if __name__ == "__main__":
    main()
