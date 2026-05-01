#!/bin/bash
set -e

# Define paths (following Linux XDG Base Directory standards)
INSTALL_DIR="$HOME/.local/share/py-cpu-z"
BIN_DIR="$HOME/.local/bin"

echo "🚀 Starting Py-CPU-Z Installation..."

# 1. Check for Python3
if ! command -v python3 &> /dev/null; then
    echo "❌ ERROR: Python3 is not installed."
    echo "Please install it using your package manager (e.g., sudo pacman -S python)"
    exit 1
fi

# 2. Prepare the installation directory
mkdir -p "$INSTALL_DIR"
mkdir -p "$BIN_DIR"

# 3. Create a Virtual Environment (Bypasses the "externally-managed-environment" block)
echo "📦 Creating isolated Python environment..."
python3 -m venv "$INSTALL_DIR/venv"

# 4. Install dependencies into the isolated environment
echo "⬇️ Installing dependencies (psutil, rich)..."
"$INSTALL_DIR/venv/bin/pip" install -r requirements.txt -q

# 5. Copy the main application file
echo "📄 Copying application files..."
cp py_cpu_z.py "$INSTALL_DIR/"

# 6. Create the executable launcher command
echo "⚙️ Creating 'pycpuz' command..."
cat << EOF > "$BIN_DIR/pycpuz"
#!/bin/bash
# This script forces the app to use its own isolated Python libraries
exec "$INSTALL_DIR/venv/bin/python" "$INSTALL_DIR/py_cpu_z.py" "\$@"
EOF

# Make the launcher executable
chmod +x "$BIN_DIR/pycpuz"

echo "====================================="
echo "✅ Installation Complete!"
echo "You can now run the tool from anywhere by typing:"
echo -e "\n    \033[1;32mpycpuz\033[0m\n"
echo "Note: If it says 'command not found', you need to add ~/.local/bin to your PATH or restart your terminal."
echo "====================================="
