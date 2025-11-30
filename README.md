# FreeFans Telegram Bot

A Telegram bot that acts as a platform for discovering and accessing creator content with advanced filtering capabilities.

## Features

### 🔍 Content Discovery
- Search for content by creator name
- Structured content directory with organized results
- Placeholder implementation ready for real search integration

### 🏷️ Advanced Filtering
- **Content Type**: Photos, Videos, or All content
- **Date Range**: Recent (24h), This Week, This Month, or All Time
- **Quality**: HD, Standard, or Any quality
- Real-time filter application

### 📱 User-Friendly Interface
- Intuitive inline keyboard navigation
- Pagination for large content lists
- Detailed content information and previews
- Session-based user preferences

### 🔗 Content Access
- Secure download link generation (placeholder)
- Content preview functionality (placeholder)
- Single-use, time-limited download URLs
- Download tracking and analytics

## Setup Instructions

### 1. Prerequisites
- Python 3.8 or higher
- Telegram account
- Telegram Bot Token (from @BotFather)

### 2. Installation

1. Clone or download this project
2. Navigate to the project directory:
   ```bash
   cd FreeFans
   ```

3. Create and activate a virtual environment:
   ```bash
   python3 -m venv env
   source env/bin/activate  # On Windows: env\Scripts\activate
   ```

4. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### 3. Configuration

1. Create a Telegram bot:
   - Open Telegram and search for @BotFather
   - Send `/newbot` and follow the instructions
   - Copy the bot token you receive

2. Update the `.env` file:
   ```
   TELEGRAM_BOT_TOKEN=your_bot_token_here
   ```

### 4. Running the Bot

1. Make sure your virtual environment is activated:
   ```bash
   source env/bin/activate  # On Windows: env\Scripts\activate
   ```

2. Start the bot:
   ```bash
   python bot.py
   ```

3. The bot will start and show: "🤖 FreeFans Bot is starting..."

4. Go to Telegram and start a conversation with your bot using `/start`

## Usage

### Basic Commands
- `/start` - Initialize the bot and show welcome message
- `/help` - Display help information
- Send any creator name to search for content

### Navigation
- Use inline buttons to navigate through content
- Apply filters before searching
- Browse paginated results
- View detailed content information
- Generate download links

## Project Structure

```
FreeFans/
├── bot.py              # Main bot application
├── content_manager.py  # Handles content search and management
├── user_session.py     # User session and preferences management
├── requirements.txt    # Python dependencies
├── .env               # Environment variables (add your bot token)
├── .env.example       # Example environment configuration
└── README.md          # This file
```

## Key Components

### Bot Features
- **Multi-user support**: Each user has their own session and preferences
- **Filter persistence**: User filter preferences are maintained across searches
- **Pagination**: Large content lists are split into manageable pages
- **Error handling**: Graceful error handling with user-friendly messages

### Content Management
- **Structured results**: Content organized with metadata (title, type, size, date, quality)
- **Filter application**: Real-time filtering based on user preferences
- **Mock content**: Placeholder content for demonstration (replace with real API calls)

### Session Management
- **User state tracking**: Maintains current search, page, and preferences
- **Activity logging**: Tracks user searches and downloads
- **Session cleanup**: Automatic cleanup of inactive sessions

## Development Notes

### Placeholder Implementations

The following features are implemented as placeholders and need real implementations:

1. **Content Search** (`content_manager.py`):
   - `search_creator_content()` currently returns mock data
   - Replace with actual API calls to content providers

2. **Download Links** (`content_manager.py`):
   - `get_content_download_link()` returns placeholder URLs
   - Implement secure link generation with your content delivery system

3. **Preview Generation** (`content_manager.py`):
   - `get_content_preview()` returns mock preview URLs
   - Integrate with actual preview generation service

### Adding Real Search Functionality

To integrate real search:

1. Implement search provider classes in `content_manager.py`
2. Add API credentials to `.env` file
3. Replace mock content generation with actual API calls
4. Implement error handling for external API failures

### Security Considerations

- Keep your bot token secure and never commit it to version control
- Implement rate limiting for API calls
- Add user authentication if required
- Validate user inputs to prevent abuse

## Customization

### Adding New Filters
1. Add new filter options to `UserSession` class in `user_session.py`
2. Update filter UI in `bot.py` (`show_filters_menu()` method)
3. Implement filter logic in `content_manager.py`

### Modifying Content Display
- Update `create_content_keyboard()` in `bot.py` for different layouts
- Modify content item display format in `display_content_directory()`
- Customize pagination settings in configuration

## Troubleshooting

### Common Issues

1. **"Import could not be resolved" errors**:
   - Make sure virtual environment is activated
   - Install dependencies: `pip install -r requirements.txt`

2. **"Bot token not found" error**:
   - Check `.env` file contains `TELEGRAM_BOT_TOKEN=your_token`
   - Ensure no spaces around the equals sign

3. **Bot doesn't respond**:
   - Verify bot token is correct
   - Check internet connection
   - Look for error messages in console

4. **No content found for searches**:
   - This is expected behavior with placeholder implementation
   - Mock content is generated for demonstration

## Contributing

To contribute to this project:

1. Fork the repository
2. Create a feature branch
3. Implement your changes
4. Test thoroughly
5. Submit a pull request

## License

This project is available for educational and development purposes. Please ensure compliance with Telegram's Bot API terms of service and respect content creators' rights.

## Support

For support or questions:
- Check the troubleshooting section above
- Review the code comments for implementation details
- Test with the placeholder content first before implementing real search

---

**Note**: This bot includes placeholder implementations for content search and download functionality. You'll need to integrate with actual content providers and implement real search mechanisms for production use.