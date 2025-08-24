#!/bin/bash

# Deployment script for Einbürgerungstest Bot

SERVER="ben@dmm-01"
REMOTE_PATH="/home/ben/einburgerungstest"

echo "📦 Deploying Einbürgerungstest Bot to $SERVER..."

# Create remote directory if it doesn't exist
echo "Creating remote directory..."
ssh $SERVER "mkdir -p $REMOTE_PATH"

# Copy necessary files
echo "Copying files to server..."
scp -r \
    bot.py \
    appointment_checker.py \
    telegram_notifier.py \
    pyproject.toml \
    .env \
    $SERVER:$REMOTE_PATH/

echo "✅ Files copied successfully!"

# Create setup script for the server
cat > setup_server.sh << 'EOF'
#!/bin/bash
cd /home/ben/einburgerungstest

echo "📦 Installing uv if needed..."
if ! command -v uv &> /dev/null; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
    source $HOME/.cargo/env
fi

echo "📦 Installing Python dependencies..."
uv sync

echo "🚀 Starting bot in tmux session..."
tmux new-session -d -s einburgerungstest
tmux send-keys -t einburgerungstest "cd /home/ben/einburgerungstest" C-m
tmux send-keys -t einburgerungstest "uv run python bot.py" C-m

echo "✅ Bot is running in tmux session 'einburgerungstest'"
echo "Use 'tmux attach -t einburgerungstest' to view the bot"
EOF

# Copy and run setup script
echo "Setting up on server..."
scp setup_server.sh $SERVER:/tmp/
ssh $SERVER "bash /tmp/setup_server.sh"

# Clean up
rm setup_server.sh

echo "🎉 Deployment complete!"
echo ""
echo "To view the bot on the server:"
echo "  ssh $SERVER"
echo "  tmux attach -t einburgerungstest"
echo ""
echo "To detach from tmux: Press Ctrl+B, then D"