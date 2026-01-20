#!/bin/bash
# Setup script for JMeter Telegram Bot Stress Testing

echo "=========================================="
echo "JMeter Telegram Bot Stress Test Setup"
echo "=========================================="
echo ""

# Check if .env file exists
if [ -f "telegram_bot/.env" ]; then
    echo "✅ Found .env file"
    # Try to extract BOT_TOKEN
    BOT_TOKEN=$(grep "^BOT_TOKEN=" telegram_bot/.env | cut -d '=' -f2 | tr -d '"' | tr -d "'")
    if [ -n "$BOT_TOKEN" ]; then
        echo "✅ Bot Token found: ${BOT_TOKEN:0:10}..."
    else
        echo "⚠️  Bot Token not found in .env"
        echo "Please enter your Bot Token:"
        read BOT_TOKEN
    fi
else
    echo "⚠️  .env file not found"
    echo "Please enter your Bot Token:"
    read BOT_TOKEN
fi

echo ""
echo "=========================================="
echo "Getting Your Chat ID"
echo "=========================================="
echo ""
echo "To get your Chat ID:"
echo "1. Send a message to your bot (e.g., /start)"
echo "2. Visit this URL in your browser:"
echo ""
echo "   https://api.telegram.org/bot${BOT_TOKEN}/getUpdates"
echo ""
echo "3. Look for 'from':{'id': 123456789} - that's your Chat ID"
echo ""
echo "Please enter your Chat ID:"
read CHAT_ID

# Validate inputs
if [ -z "$BOT_TOKEN" ] || [ -z "$CHAT_ID" ]; then
    echo "❌ Error: Bot Token or Chat ID is empty"
    exit 1
fi

echo ""
echo "=========================================="
echo "Configuring JMeter Test Plan"
echo "=========================================="
echo ""

# Update the JMeter test plan
if [ -f "telegram_bot_stress_test.jmx" ]; then
    # Create backup
    cp telegram_bot_stress_test.jmx telegram_bot_stress_test.jmx.bak
    echo "✅ Created backup: telegram_bot_stress_test.jmx.bak"
    
    # Replace placeholders
    sed -i "s/YOUR_BOT_TOKEN_HERE/${BOT_TOKEN}/g" telegram_bot_stress_test.jmx
    sed -i "s/YOUR_CHAT_ID_HERE/${CHAT_ID}/g" telegram_bot_stress_test.jmx
    
    echo "✅ Updated JMeter test plan with your credentials"
else
    echo "❌ Error: telegram_bot_stress_test.jmx not found"
    exit 1
fi


echo ""
echo "=========================================="
echo "Setup Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo ""
echo "1. Make sure your bot is running:"
echo "   cd telegram_bot"
echo "   python coordinator_bot.py"
echo ""
echo "2. Open JMeter:"
echo "   jmeter"
echo ""
echo "3. Load the test plan:"
echo "   File → Open → telegram_bot_stress_test.jmx"
echo ""
echo "4. Run the test:"
echo "   Click the green 'Start' button (or Ctrl+R)"
echo ""
echo "5. View results in the listeners (Summary Report, Graph Results, etc.)"
echo ""
echo "📊 For CLI execution (recommended for heavy tests):"
echo "   jmeter -n -t telegram_bot_stress_test.jmx -l results.jtl -e -o ./jmeter_results"
echo ""
echo "⚠️  Remember: Start with light load (10 users) and increase gradually!"
echo ""
