#!/bin/bash
# Quick rebuild script

echo "Cleaning old build..."
rm -rf build dist

echo "Building executable..."
pyinstaller staminabuyer.spec

echo ""
echo "Build complete!"
echo "Executable location: dist/staminabuyer"
echo ""
echo "Test it:"
echo "  ./dist/staminabuyer          # Opens GUI"
echo "  ./dist/staminabuyer gui      # Opens GUI"
echo "  ./dist/staminabuyer --help   # Shows help"

