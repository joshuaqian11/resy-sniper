# IAM Setup for Resy Bot (Lambda Architecture)

---

## Step 1: Create DynamoDB Tables

In AWS Console → DynamoDB → Create table:

1. **resy-bot-targets**
   - Partition key: `id` (String)
   - Capacity: On-demand
   
2. **resy-bot-config**
   - Partition key: `key` (String)
   - Capacity: On-demand

---

## Step 2: Create Lambda IAM Role

1. IAM → Roles → Create Role
2. Trusted entity: **Lambda** (`lambda.amazonaws.com`)
3. Name: `ResyBotLambdaRole`
4. Add inline policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:Scan"],
      "Resource": [
        "arn:aws:dynamodb:us-east-1:*:table/resy-bot-targets",
        "arn:aws:dynamodb:us-east-1:*:table/resy-bot-config"
      ]
    },
    {
      "Effect": "Allow",
      "Action": ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
      "Resource": "arn:aws:logs:*:*:*"
    }
  ]
}
```

---

## Step 3: Create Lambda Function

1. Lambda → Create function
2. Name: `resy-bot-snipe`
3. Runtime: Python 3.12
4. Architecture: x86_64
5. Execution role: `ResyBotLambdaRole`
6. Memory: 256 MB
7. Timeout: 5 minutes

After creation, deploy code:
```bash
./deploy/deploy.sh
```

---

## Step 4: Add EventBridge Permission to Lambda

Allow EventBridge to invoke the Lambda function:

```bash
aws lambda add-permission \
  --function-name resy-bot-snipe \
  --statement-id eventbridge-invoke \
  --action lambda:InvokeFunction \
  --principal events.amazonaws.com
```

---

## Step 5: Create Local IAM User

1. IAM → Users → Create user
2. Name: `ResyBotLocal`
3. Attach inline policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem",
        "dynamodb:DeleteItem", "dynamodb:Scan"
      ],
      "Resource": [
        "arn:aws:dynamodb:us-east-1:*:table/resy-bot-targets",
        "arn:aws:dynamodb:us-east-1:*:table/resy-bot-config"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "events:PutRule", "events:PutTargets",
        "events:DeleteRule", "events:RemoveTargets"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": ["lambda:GetFunction"],
      "Resource": "arn:aws:lambda:us-east-1:*:function:resy-bot-snipe"
    }
  ]
}
```

4. Create access key for this user
5. Run `aws configure` on your laptop with the access key

---

## Step 6: Configure Local Environment

Create `backend/.env`:
```
DASHBOARD_API_KEY=<pick-a-strong-key>
LAMBDA_ARN=arn:aws:lambda:us-east-1:<account-id>:function:resy-bot-snipe
AWS_DEFAULT_REGION=us-east-1
CORS_ORIGINS=http://localhost:5173
```

Create `frontend/.env.local`:
```
VITE_API_KEY=<same-key-as-above>
VITE_API_BASE=http://localhost:8000
```

---

## Summary of Resources

| Resource | Purpose |
|---|---|
| DynamoDB `resy-bot-targets` | Stores snipe targets |
| DynamoDB `resy-bot-config` | Stores Resy credentials |
| Lambda `resy-bot-snipe` | Executes snipes |
| IAM role `ResyBotLambdaRole` | Lambda execution permissions |
| IAM user `ResyBotLocal` | Local dashboard AWS access |
| EventBridge rules | One per target, triggers Lambda |
