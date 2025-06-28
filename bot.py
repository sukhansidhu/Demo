import os
import logging
import tempfile
import uuid
import ffmpeg
from PIL import Image
import json
import requests
import zipfile
import rarfile
import py7zr
import eyed3
from eyed3.id3.frames import ImageFrame
import subprocess
import shutil
from typing import Dict, Optional, List, Tuple
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputFile,
    InputMediaPhoto,
    InputMediaVideo,
    InputMediaAudio,
)
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    Filters,
    CallbackContext,
    CallbackQueryHandler,
    ConversationHandler,
)
from telegram.error import TelegramError

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot token from BotFather
TOKEN = "YOUR_BOT_TOKEN_HERE"

# Conversation states
SETTINGS, RENAME, UPLOAD_MODE, AUDIO_QUALITY, VIDEO_QUALITY = range(5)
PROCESSING_VIDEO, PROCESSING_AUDIO, PROCESSING_DOC, PROCESSING_URL = range(4, 8)

# User settings storage (in production, use a database)
user_settings = {}

class MediaProcessor:
    @staticmethod
    def get_temp_path(extension: str = "") -> str:
        """Generate a temporary file path."""
        return os.path.join(tempfile.gettempdir(), f"bot_{uuid.uuid4().hex}{extension}")

    @staticmethod
    def download_file(file_id: str, context: CallbackContext) -> Optional[str]:
        """Download file from Telegram and return local path."""
        try:
            file = context.bot.get_file(file_id)
            temp_path = MediaProcessor.get_temp_path()
            file.download(custom_path=temp_path)
            return temp_path
        except Exception as e:
            logger.error(f"Error downloading file: {e}")
            return None

    @staticmethod
    def cleanup_files(*paths: str) -> None:
        """Clean up temporary files."""
        for path in paths:
            try:
                if path and os.path.exists(path):
                    os.unlink(path)
            except Exception as e:
                logger.error(f"Error cleaning up file {path}: {e}")

    # Video Processing Functions
    @staticmethod
    def remove_audio_video(input_path: str) -> Tuple[str, str]:
        """Remove audio from video."""
        output_path = MediaProcessor.get_temp_path(".mp4")
        (
            ffmpeg.input(input_path)
            .output(output_path, vcodec="copy", an=None)
            .run(overwrite_output=True)
        )
        return output_path, "Audio removed from video"

    @staticmethod
    def extract_audio_video(input_path: str, format: str = "mp3") -> Tuple[str, str]:
        """Extract audio from video."""
        output_path = MediaProcessor.get_temp_path(f".{format}")
        (
            ffmpeg.input(input_path)
            .output(output_path, acodec="libmp3lame" if format == "mp3" else None)
            .run(overwrite_output=True)
        )
        return output_path, f"Audio extracted as {format}"

    @staticmethod
    def trim_video(input_path: str, start: str, end: str) -> Tuple[str, str]:
        """Trim video between start and end times."""
        output_path = MediaProcessor.get_temp_path(".mp4")
        (
            ffmpeg.input(input_path, ss=start, to=end)
            .output(output_path, c="copy")
            .run(overwrite_output=True)
        )
        return output_path, f"Video trimmed from {start} to {end}"

    @staticmethod
    def merge_videos(input_paths: List[str]) -> Tuple[str, str]:
        """Merge multiple videos."""
        output_path = MediaProcessor.get_temp_path(".mp4")
        input_files = [ffmpeg.input(path) for path in input_paths]
        (
            ffmpeg.concat(*input_files, v=1, a=1)
            .output(output_path)
            .run(overwrite_output=True)
        )
        return output_path, "Videos merged successfully"

    @staticmethod
    def video_to_gif(input_path: str, start: int = 0, duration: int = 5) -> Tuple[str, str]:
        """Convert video segment to GIF."""
        output_path = MediaProcessor.get_temp_path(".gif")
        (
            ffmpeg.input(input_path, ss=start, t=duration)
            .filter("fps", fps=10)
            .filter("scale", w=-1, h=240)
            .output(output_path)
            .run(overwrite_output=True)
        )
        return output_path, f"GIF created from {start}s to {start+duration}s"

    @staticmethod
    def generate_screenshots(input_path: str, count: int = 3) -> List[Tuple[str, str]]:
        """Generate screenshots from video."""
        result = []
        probe = ffmpeg.probe(input_path)
        duration = float(probe["format"]["duration"])
        
        for i in range(count):
            output_path = MediaProcessor.get_temp_path(f"_{i}.jpg")
            time = duration * (i + 1) / (count + 1)
            (
                ffmpeg.input(input_path, ss=time)
                .output(output_path, vframes=1, qscale:v=2)
                .run(overwrite_output=True)
            )
            result.append((output_path, f"Screenshot at {time:.1f}s"))
        
        return result

    # Audio Processing Functions
    @staticmethod
    def slow_reverb_audio(input_path: str) -> Tuple[str, str]:
        """Apply slow and reverb effect to audio."""
        output_path = MediaProcessor.get_temp_path(".mp3")
        # Complex filter chain for slow + reverb effect
        (
            ffmpeg.input(input_path)
            .filter("atempo", 0.8)
            .filter("aecho", 0.8, 0.9, 1000, 0.3)
            .output(output_path)
            .run(overwrite_output=True)
        )
        return output_path, "Slow + reverb effect applied"

    @staticmethod
    def convert_audio_format(input_path: str, format: str) -> Tuple[str, str]:
        """Convert audio to different format."""
        output_path = MediaProcessor.get_temp_path(f".{format}")
        (
            ffmpeg.input(input_path)
            .output(output_path, acodec="libmp3lame" if format == "mp3" else None)
            .run(overwrite_output=True)
        )
        return output_path, f"Audio converted to {format}"

    @staticmethod
    def audio_8d_effect(input_path: str) -> Tuple[str, str]:
        """Apply 8D audio effect."""
        output_path = MediaProcessor.get_temp_path(".mp3")
        # Simple 8D effect using pan filter
        (
            ffmpeg.input(input_path)
            .filter("pan", "stereo|FL=0.5*FC+0.707*FL+0.707*BL|FR=0.5*FC+0.707*FR+0.707*BR")
            .output(output_path)
            .run(overwrite_output=True)
        )
        return output_path, "8D audio effect applied"

    @staticmethod
    def adjust_audio_speed(input_path: str, speed: float) -> Tuple[str, str]:
        """Change audio speed."""
        output_path = MediaProcessor.get_temp_path(".mp3")
        (
            ffmpeg.input(input_path)
            .filter("atempo", speed)
            .output(output_path)
            .run(overwrite_output=True)
        )
        return output_path, f"Audio speed changed to {speed}x"

    # Document Processing Functions
    @staticmethod
    def create_archive(input_paths: List[str], archive_type: str = "zip") -> Tuple[str, str]:
        """Create archive from files."""
        output_path = MediaProcessor.get_temp_path(f".{archive_type}")
        
        if archive_type == "zip":
            with zipfile.ZipFile(output_path, "w") as zipf:
                for path in input_paths:
                    zipf.write(path, os.path.basename(path))
        elif archive_type == "rar":
            # Requires rar command line tool
            subprocess.run(["rar", "a", output_path] + input_paths)
        elif archive_type == "7z":
            with py7zr.SevenZipFile(output_path, "w") as archive:
                for path in input_paths:
                    archive.write(path, os.path.basename(path))
        
        return output_path, f"{archive_type.upper()} archive created"

    @staticmethod
    def extract_archive(input_path: str) -> List[Tuple[str, str]]:
        """Extract archive and return list of extracted files."""
        extracted_files = []
        output_dir = MediaProcessor.get_temp_path("_extracted")
        os.makedirs(output_dir, exist_ok=True)
        
        if input_path.endswith(".zip"):
            with zipfile.ZipFile(input_path, "r") as zipf:
                zipf.extractall(output_dir)
        elif input_path.endswith(".rar"):
            # Requires unrar command line tool
            subprocess.run(["unrar", "x", input_path, output_dir])
        elif input_path.endswith(".7z"):
            with py7zr.SevenZipFile(input_path, "r") as archive:
                archive.extractall(output_dir)
        
        for root, _, files in os.walk(output_dir):
            for file in files:
                file_path = os.path.join(root, file)
                extracted_files.append((file_path, f"Extracted: {file}"))
        
        return extracted_files

    # URL Processing Functions
    @staticmethod
    def download_from_url(url: str) -> Tuple[str, str]:
        """Download file from URL."""
        try:
            response = requests.get(url, stream=True)
            if response.status_code == 200:
                file_name = os.path.basename(url.split("?")[0]) or "downloaded_file"
                ext = os.path.splitext(file_name)[1]
                output_path = MediaProcessor.get_temp_path(ext)
                
                with open(output_path, "wb") as f:
                    for chunk in response.iter_content(1024):
                        f.write(chunk)
                
                return output_path, f"Downloaded: {file_name}"
        except Exception as e:
            logger.error(f"Error downloading from URL: {e}")
            return None, f"Error downloading: {str(e)}"

# Bot Command Handlers
def start(update: Update, context: CallbackContext) -> None:
    """Send welcome message."""
    user = update.effective_user
    update.message.reply_markdown_v2(
        fr"Hi {user.mention_markdown_v2()}\! Welcome to the All\-in\-One Media Bot\. "
        "Send me a video, audio, document, or URL to get started\. "
        "Use /settings to customize options\."
    )

def settings(update: Update, context: CallbackContext) -> int:
    """Show settings menu."""
    keyboard = [
        [InlineKeyboardButton("Rename File", callback_data="settings_rename")],
        [InlineKeyboardButton("Upload Mode", callback_data="settings_upload_mode")],
        [InlineKeyboardButton("Audio Quality", callback_data="settings_audio_quality")],
        [InlineKeyboardButton("Video Quality", callback_data="settings_video_quality")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("Settings Menu:", reply_markup=reply_markup)
    return SETTINGS

def handle_video(update: Update, context: CallbackContext) -> int:
    """Handle incoming video files."""
    keyboard = [
        [InlineKeyboardButton("Audio Remover", callback_data="video_remove_audio")],
        [InlineKeyboardButton("Audio Extractor", callback_data="video_extract_audio")],
        [InlineKeyboardButton("Video Trimmer", callback_data="video_trim")],
        [InlineKeyboardButton("Video Merger", callback_data="video_merge")],
        [InlineKeyboardButton("Video to GIF", callback_data="video_to_gif")],
        [InlineKeyboardButton("Screenshots", callback_data="video_screenshots")],
        [InlineKeyboardButton("Video Converter", callback_data="video_convert")],
        [InlineKeyboardButton("Media Info", callback_data="video_info")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("Select a video processing option:", reply_markup=reply_markup)
    
    # Store file info in context
    if update.message.video:
        context.user_data["file_id"] = update.message.video.file_id
        context.user_data["file_type"] = "video"
    elif update.message.document:
        context.user_data["file_id"] = update.message.document.file_id
        context.user_data["file_type"] = "document"
    
    return PROCESSING_VIDEO

def handle_audio(update: Update, context: CallbackContext) -> int:
    """Handle incoming audio files."""
    keyboard = [
        [InlineKeyboardButton("Slow + Reverb", callback_data="audio_slow_reverb")],
        [InlineKeyboardButton("Audio Converter", callback_data="audio_convert")],
        [InlineKeyboardButton("8D Effect", callback_data="audio_8d")],
        [InlineKeyboardButton("Speed Change", callback_data="audio_speed")],
        [InlineKeyboardButton("Volume Adjust", callback_data="audio_volume")],
        [InlineKeyboardButton("Tag Editor", callback_data="audio_tags")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("Select an audio processing option:", reply_markup=reply_markup)
    
    if update.message.audio:
        context.user_data["file_id"] = update.message.audio.file_id
        context.user_data["file_type"] = "audio"
    elif update.message.document:
        context.user_data["file_id"] = update.message.document.file_id
        context.user_data["file_type"] = "document"
    
    return PROCESSING_AUDIO

def handle_document(update: Update, context: CallbackContext) -> int:
    """Handle incoming documents."""
    keyboard = [
        [InlineKeyboardButton("Create Archive", callback_data="doc_archive")],
        [InlineKeyboardButton("Extract Archive", callback_data="doc_extract")],
        [InlineKeyboardButton("Rename File", callback_data="doc_rename")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("Select a document processing option:", reply_markup=reply_markup)
    
    context.user_data["file_id"] = update.message.document.file_id
    context.user_data["file_type"] = "document"
    
    return PROCESSING_DOC

def handle_url(update: Update, context: CallbackContext) -> int:
    """Handle incoming URLs."""
    keyboard = [
        [InlineKeyboardButton("Download File", callback_data="url_download")],
        [InlineKeyboardButton("Extract Archive", callback_data="url_extract")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("Select a URL processing option:", reply_markup=reply_markup)
    
    context.user_data["url"] = update.message.text
    return PROCESSING_URL

def handle_bulk_mode(update: Update, context: CallbackContext) -> None:
    """Handle bulk processing mode."""
    keyboard = [
        [InlineKeyboardButton("Archive Files", callback_data="bulk_archive")],
        [InlineKeyboardButton("Convert Videos", callback_data="bulk_convert")],
        [InlineKeyboardButton("Extract Archives", callback_data="bulk_extract")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("Select a bulk processing option:", reply_markup=reply_markup)
    
    # Initialize bulk processing context
    context.user_data["bulk_files"] = []
    context.user_data["bulk_operation"] = None

def help_command(update: Update, context: CallbackContext) -> None:
    """Show help message."""
    update.message.reply_text("""
Available commands:
/start - Start the bot
/settings - Configure bot settings
/help - Show this help message
/bulk - Enter bulk processing mode

Send me a video, audio, document, or URL to process it.
""")

# Callback Handlers
def video_callback_handler(update: Update, context: CallbackContext) -> int:
    """Handle video processing callbacks."""
    query = update.callback_query
    query.answer()
    
    file_id = context.user_data.get("file_id")
    if not file_id:
        query.edit_message_text("Error: File not found. Please send the file again.")
        return ConversationHandler.END
    
    input_path = MediaProcessor.download_file(file_id, context)
    if not input_path:
        query.edit_message_text("Error downloading file. Please try again.")
        return ConversationHandler.END
    
    try:
        if query.data == "video_remove_audio":
            output_path, caption = MediaProcessor.remove_audio_video(input_path)
            with open(output_path, "rb") as f:
                context.bot.send_video(chat_id=query.message.chat_id, video=f, caption=caption)
        
        elif query.data == "video_extract_audio":
            output_path, caption = MediaProcessor.extract_audio_video(input_path)
            with open(output_path, "rb") as f:
                context.bot.send_audio(chat_id=query.message.chat_id, audio=f, caption=caption)
        
        elif query.data == "video_trim":
            # In a full implementation, you would ask for start/end times
            output_path, caption = MediaProcessor.trim_video(input_path, "00:00:10", "00:00:20")
            with open(output_path, "rb") as f:
                context.bot.send_video(chat_id=query.message.chat_id, video=f, caption=caption)
        
        elif query.data == "video_to_gif":
            output_path, caption = MediaProcessor.video_to_gif(input_path)
            with open(output_path, "rb") as f:
                context.bot.send_animation(chat_id=query.message.chat_id, animation=f, caption=caption)
        
        elif query.data == "video_screenshots":
            screenshots = MediaProcessor.generate_screenshots(input_path)
            media_group = []
            for i, (screenshot_path, caption) in enumerate(screenshots):
                if i < 10:  # Telegram allows max 10 media in a group
                    with open(screenshot_path, "rb") as f:
                        media_group.append(InputMediaPhoto(media=f, caption=caption if i == 0 else ""))
            
            context.bot.send_media_group(chat_id=query.message.chat_id, media=media_group)
        
        query.edit_message_text("Processing complete!")
    
    except Exception as e:
        logger.error(f"Error processing video: {e}")
        query.edit_message_text(f"Error processing video: {str(e)}")
    
    finally:
        MediaProcessor.cleanup_files(input_path)
        if "output_path" in locals():
            MediaProcessor.cleanup_files(output_path)
        if "screenshots" in locals():
            for path, _ in screenshots:
                MediaProcessor.cleanup_files(path)
    
    return ConversationHandler.END

def audio_callback_handler(update: Update, context: CallbackContext) -> int:
    """Handle audio processing callbacks."""
    query = update.callback_query
    query.answer()
    
    file_id = context.user_data.get("file_id")
    if not file_id:
        query.edit_message_text("Error: File not found. Please send the file again.")
        return ConversationHandler.END
    
    input_path = MediaProcessor.download_file(file_id, context)
    if not input_path:
        query.edit_message_text("Error downloading file. Please try again.")
        return ConversationHandler.END
    
    try:
        if query.data == "audio_slow_reverb":
            output_path, caption = MediaProcessor.slow_reverb_audio(input_path)
            with open(output_path, "rb") as f:
                context.bot.send_audio(chat_id=query.message.chat_id, audio=f, caption=caption)
        
        elif query.data == "audio_convert":
            output_path, caption = MediaProcessor.convert_audio_format(input_path, "wav")
            with open(output_path, "rb") as f:
                context.bot.send_audio(chat_id=query.message.chat_id, audio=f, caption=c
        elif query.data == "audio_8d":
            output_path, caption = MediaProcessor.audio_8d_effect(input_path)
            with open(output_path, "rb") as f:
                context.bot.send_audio(chat_id=query.message.chat_id, audio=f, caption=caption)
        
        elif query.data == "audio_speed":
            output_path, caption = MediaProcessor.adjust_audio_speed(input_path, 1.5)
            with open(output_path, "rb") as f:
                context.bot.send_audio(chat_id=query.message.chat_id, audio=f, caption=caption)
        
        query.edit_message_text("Processing complete!")
    
    except Exception as e:
        logger.error(f"Error processing audio: {e}")
        query.edit_message_text(f"Error processing audio: {str(e)}")
    
    finally:
        MediaProcessor.cleanup_files(input_path)
        if "output_path" in locals():
            MediaProcessor.cleanup_files(output_path)
    
    return ConversationHandler.END

def doc_callback_handler(update: Update, context: CallbackContext) -> int:
    """Handle document processing callbacks."""
    query = update.callback_query
    query.answer()
    
    file_id = context.user_data.get("file_id")
    if not file_id:
        query.edit_message_text("Error: File not found. Please send the file again.")
        return ConversationHandler.END
    
    input_path = MediaProcessor.download_file(file_id, context)
    if not input_path:
        query.edit_message_text("Error downloading file. Please try again.")
        return ConversationHandler.END
    
    try:
        if query.data == "doc_archive":
            # In a full implementation, you would collect multiple files
            output_path, caption = MediaProcessor.create_archive([input_path])
            with open(output_path, "rb") as f:
                context.bot.send_document(chat_id=query.message.chat_id, document=f, caption=caption)
        
        elif query.data == "doc_extract":
            extracted_files = MediaProcessor.extract_archive(input_path)
            for file_path, caption in extracted_files:
                with open(file_path, "rb") as f:
                    context.bot.send_document(chat_id=query.message.chat_id, document=f, caption=caption)
        
        query.edit_message_text("Processing complete!")
    
    except Exception as e:
        logger.error(f"Error processing document: {e}")
        query.edit_message_text(f"Error processing document: {str(e)}")
    
    finally:
        MediaProcessor.cleanup_files(input_path)
        if "output_path" in locals():
            MediaProcessor.cleanup_files(output_path)
        if "extracted_files" in locals():
            for path, _ in extracted_files:
                MediaProcessor.cleanup_files(path)
    
    return ConversationHandler.END

def url_callback_handler(update: Update, context: CallbackContext) -> int:
    """Handle URL processing callbacks."""
    query = update.callback_query
    query.answer()
    
    url = context.user_data.get("url")
    if not url:
        query.edit_message_text("Error: URL not found. Please send the URL again.")
        return ConversationHandler.END
    
    try:
        if query.data == "url_download":
            output_path, caption = MediaProcessor.download_from_url(url)
            if output_path:
                with open(output_path, "rb") as f:
                    context.bot.send_document(chat_id=query.message.chat_id, document=f, caption=caption)
            else:
                query.edit_message_text(caption)
        
        elif query.data == "url_extract":
            output_path, _ = MediaProcessor.download_from_url(url)
            if output_path:
                extracted_files = MediaProcessor.extract_archive(output_path)
                for file_path, caption in extracted_files:
                    with open(file_path, "rb") as f:
                        context.bot.send_document(chat_id=query.message.chat_id, document=f, caption=caption)
                MediaProcessor.cleanup_files(output_path)
            else:
                query.edit_message_text("Error downloading file from URL")
        
        query.edit_message_text("Processing complete!")
    
    except Exception as e:
        logger.error(f"Error processing URL: {e}")
        query.edit_message_text(f"Error processing URL: {str(e)}")
    
    finally:
        if "output_path" in locals():
            MediaProcessor.cleanup_files(output_path)
        if "extracted_files" in locals():
            for path, _ in extracted_files:
                MediaProcessor.cleanup_files(path)
    
    return ConversationHandler.END

def bulk_callback_handler(update: Update, context: CallbackContext) -> None:
    """Handle bulk processing callbacks."""
    query = update.callback_query
    query.answer()
    
    context.user_data["bulk_operation"] = query.data
    query.edit_message_text(f"Bulk operation '{query.data}' selected. Please send files one by one.")

def cancel(update: Update, context: CallbackContext) -> int:
    """Cancel the current operation."""
    update.message.reply_text("Operation cancelled.")
    return ConversationHandler.END

def error_handler(update: Update, context: CallbackContext) -> None:
    """Log errors caused by updates."""
    logger.error(msg="Exception while handling an update:", exc_info=context.error)
    if update.effective_message:
        update.effective_message.reply_text("An error occurred. Please try again.")

def main() -> None:
    """Start the bot."""
    # Create the Updater and pass it your bot's token.
    updater = Updater(TOKEN)

    # Get the dispatcher to register handlers
    dispatcher = updater.dispatcher

    # Add conversation handler with the states
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CommandHandler("settings", settings),
            MessageHandler(Filters.video | Filters.document.mime_type("video/*"), handle_video),
            MessageHandler(Filters.audio | Filters.document.mime_type("audio/*"), handle_audio),
            MessageHandler(Filters.document, handle_document),
            MessageHandler(Filters.entity("url") | Filters.text & ~Filters.command, handle_url),
            CommandHandler("bulk", handle_bulk_mode),
        ],
        states={
            SETTINGS: [
                CallbackQueryHandler(settings, pattern="^settings_"),
            ],
            PROCESSING_VIDEO: [
CallbackQueryHandler(video_callback_handler, pattern="^video_"),
            ],
            PROCESSING_AUDIO: [
                CallbackQueryHandler(audio_callback_handler, pattern="^audio_"),
            ],
            PROCESSING_DOC: [
                CallbackQueryHandler(doc_callback_handler, pattern="^doc_"),
            ],
            PROCESSING_URL: [
                CallbackQueryHandler(url_callback_handler, pattern="^url_"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    dispatcher.add_handler(conv_handler)
    dispatcher.add_handler(CommandHandler("help", help_command))
    dispatcher.add_handler(CallbackQueryHandler(bulk_callback_handler, pattern="^bulk_"))
    
    # Register error handler
    dispatcher.add_error_handler(error_handler)

    # Start the Bot
    updater.start_polling()

    # Run the bot until you press Ctrl-C
    updater.idle()

if __name__ == "__main__":
    main()
```
