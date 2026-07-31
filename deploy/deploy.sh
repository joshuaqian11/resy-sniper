#!/bin/bash
set -e

FUNCTION_NAME="resy-bot-snipe"
BUILD_DIR=$(mktemp -d)

echo "Installing dependencies..."
pip install httpx boto3 -t "$BUILD_DIR" --quiet

echo "Copying source files..."
cp backend/lambda_handler.py "$BUILD_DIR/"
cp backend/resy.py "$BUILD_DIR/"
cp backend/snipe.py "$BUILD_DIR/"
cp backend/database.py "$BUILD_DIR/"
cp backend/config.py "$BUILD_DIR/"

echo "Creating zip..."
cd "$BUILD_DIR"
zip -r9 /tmp/resy-bot-lambda.zip . --quiet

echo "Uploading to Lambda..."
aws lambda update-function-code \
  --function-name "$FUNCTION_NAME" \
  --zip-file fileb:///tmp/resy-bot-lambda.zip

echo "Cleaning up..."
rm -rf "$BUILD_DIR" /tmp/resy-bot-lambda.zip

echo "Deploy complete."
