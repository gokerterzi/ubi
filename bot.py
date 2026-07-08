import os
import logging
import asyncio
import subprocess
import shutil
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters, CallbackQueryHandler

# --- Setup Logging ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Environment Variables ---
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
if not TOKEN:
    logger.error("❌ TELEGRAM_BOT_TOKEN is not set!")
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable is required!")

# --- Supported Formats ---
SUPPORTED_FORMATS = {
    'image': ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'tiff', 'ico'],
    'video': ['mp4', 'avi', 'mkv', 'mov', 'wmv', 'flv', 'webm', 'm4v'],
    'audio': ['mp3', 'wav', 'aac', 'flac', 'ogg', 'm4a', 'wma'],
    'document': ['pdf', 'docx', 'txt', 'csv', 'xlsx', 'pptx', 'odt', 'html', 'xml'],
    'ebook': ['epub', 'mobi', 'azw3', 'pdf', 'txt']
}

# --- Convert Function ---
def convert_file(input_path, output_format):
    """Convert file to specified format using ffmpeg or other tools."""
    base_name = os.path.splitext(input_path)[0]
    output_path = f"{base_name}.{output_format}"
    
    # Check if output format is image
    if output_format in SUPPORTED_FORMATS['image']:
        # Use ffmpeg for image conversion
        cmd = ['ffmpeg', '-i', input_path, '-y', output_path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0 and os.path.exists(output_path):
            return output_path
        else:
            logger.error(f"Conversion failed: {result.stderr}")
            return None
    
    # Check if output format is audio/video
    elif output_format in SUPPORTED_FORMATS['audio'] or output_format in SUPPORTED_FORMATS['video']:
        cmd = ['ffmpeg', '-i', input_path, '-y', output_path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0 and os.path.exists(output_path):
            return output_path
        else:
            logger.error(f"Conversion failed: {result.stderr}")
            return None
    
    # Document conversion (using LibreOffice for advanced formats)
    elif output_format in SUPPORTED_FORMATS['document']:
        cmd = ['libreoffice', '--headless', '--convert-to', output_format, '--outdir', os.path.dirname(input_path), input_path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        converted_file = f"{base_name}.{output_format}"
        if result.returncode == 0 and os.path.exists(converted_file):
            return converted_file
        else:
            logger.error(f"Document conversion failed: {result.stderr}")
            return None
    
    else:
        logger.error(f"Unsupported output format: {output_format}")
        return None

def get_file_type(filename):
    """Detect file type based on extension."""
    ext = filename.split('.')[-1].lower() if '.' in filename else ''
    
    for file_type, formats in SUPPORTED_FORMATS.items():
        if ext in formats:
            return file_type, ext
    
    return 'unknown', ext

# --- Bot Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send welcome message with instructions."""
    keyboard = [
        [InlineKeyboardButton("📸 Image Formats", callback_data='show_image')],
        [InlineKeyboardButton("🎬 Video Formats", callback_data='show_video')],
        [InlineKeyboardButton("🎵 Audio Formats", callback_data='show_audio')],
        [InlineKeyboardButton("📄 Document Formats", callback_data='show_document')],
        [InlineKeyboardButton("📚 Ebook Formats", callback_data='show_ebook')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🎯 *OnlineConvertBot*\n\n"
        "Send me any file (image, video, audio, document, or ebook), "
        "and I'll convert it to your desired format!\n\n"
        "*How to use:*\n"
        "1️⃣ Send a file\n"
        "2️⃣ Choose the output format\n"
        "3️⃣ I'll convert and send it back\n\n"
        "*Supported formats:* Click a button below to see all formats.",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

async def show_formats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show supported formats when button is clicked."""
    query = update.callback_query
    await query.answer()
    
    format_type = query.data.replace('show_', '')
    
    if format_type in SUPPORTED_FORMATS:
        formats = SUPPORTED_FORMATS[format_type]
        emoji_map = {
            'image': '📸',
            'video': '🎬',
            'audio': '🎵',
            'document': '📄',
            'ebook': '📚'
        }
        emoji = emoji_map.get(format_type, '📁')
        
        format_list = ', '.join(f'`{f}`' for f in formats)
        await query.edit_message_text(
            f"{emoji} *{format_type.title()} Formats*\n\n"
            f"{format_list}\n\n"
            f"*How to convert:*\n"
            f"1. Send a {format_type} file\n"
            f"2. When I ask, reply with the format you want (e.g., `{formats[0]}`)",
            parse_mode='Markdown'
        )

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming files."""
    file = update.message.document or update.message.photo or update.message.video or update.message.audio
    
    if not file:
        await update.message.reply_text("Please send a valid file.")
        return
    
    # Get file info
    file_name = getattr(file, 'file_name', None)
    if not file_name:
        if update.message.photo:
            file_name = f"photo_{file.file_id}.jpg"
        elif update.message.video:
            file_name = f"video_{file.file_id}.mp4"
        elif update.message.audio:
            file_name = f"audio_{file.file_id}.mp3"
        else:
            file_name = f"file_{file.file_id}.bin"
    
    file_type, ext = get_file_type(file_name)
    
    if file_type == 'unknown':
        await update.message.reply_text(
            f"⚠️ Unsupported file format: `{ext}`\n\n"
            f"Please send one of these formats:\n"
            f"{', '.join([f'`{f}`' for f in sum(SUPPORTED_FORMATS.values(), [])][:20])}",
            parse_mode='Markdown'
        )
        return
    
    # Download the file
    await update.message.reply_text(f"📥 Downloading your {file_type}...")
    
    file_obj = await file.get_file()
    input_path = f"downloads/{file.file_id}_{file_name}"
    os.makedirs('downloads', exist_ok=True)
    await file_obj.download_to_drive(input_path)
    
    # Store file info in context for later
    context.user_data['input_path'] = input_path
    context.user_data['file_type'] = file_type
    context.user_data['original_ext'] = ext
    
    # Ask for output format
    emoji_map = {
        'image': '📸',
        'video': '🎬',
        'audio': '🎵',
        'document': '📄',
        'ebook': '📚'
    }
    emoji = emoji_map.get(file_type, '📁')
    
    formats = SUPPORTED_FORMATS[file_type]
    format_buttons = []
    row = []
    for i, fmt in enumerate(formats):
        row.append(InlineKeyboardButton(fmt, callback_data=f'convert_{fmt}'))
        if len(row) == 3:
            format_buttons.append(row)
            row = []
    if row:
        format_buttons.append(row)
    
    reply_markup = InlineKeyboardMarkup(format_buttons)
    
    await update.message.reply_text(
        f"{emoji} *{file_type.title()} Detected!*\n\n"
        f"Original format: `{ext}`\n\n"
        f"*Choose an output format:*\n"
        f"(Click a button below or type the format name)",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

async def handle_format_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle format selection from buttons."""
    query = update.callback_query
    await query.answer()
    
    output_format = query.data.replace('convert_', '')
    input_path = context.user_data.get('input_path')
    
    if not input_path or not os.path.exists(input_path):
        await query.edit_message_text(
            "❌ File not found. Please send the file again."
        )
        return
    
    file_type = context.user_data.get('file_type', 'unknown')
    
    # Check if output format is valid for this file type
    if output_format not in SUPPORTED_FORMATS.get(file_type, []):
        await query.edit_message_text(
            f"❌ `{output_format}` is not a valid format for {file_type} files.\n"
            f"Please choose from: {', '.join(SUPPORTED_FORMATS.get(file_type, []))}",
            parse_mode='Markdown'
        )
        return
    
    await query.edit_message_text(f"🔄 Converting to `{output_format}`... This may take a moment.", parse_mode='Markdown')
    
    # Convert the file
    output_path = convert_file(input_path, output_format)
    
    if output_path and os.path.exists(output_path):
        try:
            # Send the converted file back
            with open(output_path, 'rb') as f:
                await update._bot.send_document(
                    chat_id=update.effective_chat.id,
                    document=f,
                    caption=f"✅ Converted to `{output_format}` successfully!",
                    parse_mode='Markdown'
                )
            await query.edit_message_text(f"✅ Conversion complete! Check the file above.")
            
            # Clean up
            os.remove(output_path)
        except Exception as e:
            logger.error(f"Error sending file: {e}")
            await query.edit_message_text(f"❌ Error sending converted file: {str(e)[:100]}")
    else:
        await query.edit_message_text(
            f"❌ Conversion failed. Please try again with a different format.\n\n"
            f"Try one of these: {', '.join(SUPPORTED_FORMATS.get(file_type, [])[:5])}"
        )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text input for format selection."""
    text = update.message.text.strip().lower()
    
    # Check if user is trying to select a format
    input_path = context.user_data.get('input_path')
    if not input_path:
        await update.message.reply_text(
            "Please send a file first, then choose a format.\n"
            "Send /start for help."
        )
        return
    
    file_type = context.user_data.get('file_type', 'unknown')
    
    if text in SUPPORTED_FORMATS.get(file_type, []):
        # Process the conversion
        output_format = text
        await update.message.reply_text(f"🔄 Converting to `{output_format}`...", parse_mode='Markdown')
        
        output_path = convert_file(input_path, output_format)
        
        if output_path and os.path.exists(output_path):
            try:
                with open(output_path, 'rb') as f:
                    await update.message.reply_document(
                        document=f,
                        caption=f"✅ Converted to `{output_format}` successfully!",
                        parse_mode='Markdown'
                    )
                os.remove(output_path)
            except Exception as e:
                await update.message.reply_text(f"❌ Error sending file: {str(e)[:100]}")
        else:
            await update.message.reply_text(
                f"❌ Conversion failed. Try one of these: {', '.join(SUPPORTED_FORMATS.get(file_type, [])[:5])}"
            )
    else:
        await update.message.reply_text(
            f"❌ `{text}` is not a valid format for {file_type} files.\n\n"
            f"Available formats: {', '.join(SUPPORTED_FORMATS.get(file_type, []))}",
            parse_mode='Markdown'
        )

# --- Main Function ---
def main():
    app = ApplicationBuilder().token(TOKEN).build()
    
    # Handlers
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CallbackQueryHandler(show_formats, pattern='^show_'))
    app.add_handler(CallbackQueryHandler(handle_format_selection, pattern='^convert_'))
    app.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO | filters.VIDEO | filters.AUDIO, handle_file))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    logger.info("🤖 OnlineConvertBot is starting with long polling...")
    app.run_polling()

if __name__ == '__main__':
    main()
