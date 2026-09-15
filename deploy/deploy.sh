#!/bin/bash
set -e

FUNCTION_NAME="resy-bot-snipe"
EC2_INSTANCE_ID="${EC2_INSTANCE_ID:?Set EC2_INSTANCE_ID env var}"
APP_DIR="/opt/resy-bot"

echo "=== Deploying Lambda trigger ==="
BUILD_DIR=$(mktemp -d)

pip3 install boto3 -t "$BUILD_DIR" --quiet \
  --platform manylinux2014_x86_64 --only-binary=:all: --python-version 3.12

cp backend/lambda_handler.py "$BUILD_DIR/"

cd "$BUILD_DIR"
zip -r9 /tmp/resy-bot-lambda.zip . --quiet
cd -

aws lambda update-function-code \
  --function-name "$FUNCTION_NAME" \
  --zip-file fileb:///tmp/resy-bot-lambda.zip

aws lambda update-function-configuration \
  --function-name "$FUNCTION_NAME" \
  --timeout 30 \
  --environment "Variables={EC2_INSTANCE_ID=$EC2_INSTANCE_ID}"

rm -rf "$BUILD_DIR" /tmp/resy-bot-lambda.zip
echo "Lambda trigger deployed."

echo ""
echo "=== Syncing code to EC2 ==="
# Copy app files to EC2 via SSM (no SSH needed)
for file in resy.py snipe.py snipe_runner.py database.py config.py; do
  echo "Uploading $file..."
  aws ssm send-command \
    --instance-id "$EC2_INSTANCE_ID" \
    --document-name "AWS-RunShellScript" \
    --parameters "commands=[\"cat > $APP_DIR/$file << 'FILEEOF'\n$(cat backend/$file)\nFILEEOF\"]" \
    --output text --query "Command.CommandId" > /dev/null
done

echo "Deploy complete."
