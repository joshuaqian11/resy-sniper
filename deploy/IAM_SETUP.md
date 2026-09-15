# AWS Setup for Resy Bot (EC2 + Lambda Architecture)

---

## Architecture

```
EventBridge (cron) → Lambda (thin trigger) → EC2 (Playwright snipe) → self-stop
                          ↓                       ↑
                    SSM Parameter Store ───────────┘
```

- **EventBridge** fires 2 min before opening time
- **Lambda** writes the target ID to SSM and starts the EC2 instance
- **EC2** boots, systemd runs `snipe_runner.py`, which reads SSM, loads target from DynamoDB, runs the snipe with Playwright, then stops the instance
- **DynamoDB** stores targets and config
- **Dashboard** (FastAPI + React) runs locally, manages targets and EventBridge rules

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
      "Action": ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
      "Resource": "arn:aws:logs:*:*:*"
    },
    {
      "Effect": "Allow",
      "Action": "ec2:StartInstances",
      "Resource": "*",
      "Condition": {
        "StringEquals": { "ec2:ResourceTag/Name": "resy-bot-snipe" }
      }
    },
    {
      "Effect": "Allow",
      "Action": "ssm:PutParameter",
      "Resource": "arn:aws:ssm:us-east-1:*:parameter/resy-bot/pending-target-id"
    }
  ]
}
```

---

## Step 3: Create EC2 IAM Role

1. IAM → Roles → Create Role
2. Trusted entity: **EC2** (`ec2.amazonaws.com`)
3. Name: `ResyBotEC2Role`
4. Attach managed policy: **AmazonSSMManagedInstanceCore**
5. Add inline policy:

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
      "Action": "ssm:GetParameter",
      "Resource": "arn:aws:ssm:us-east-1:*:parameter/resy-bot/pending-target-id"
    },
    {
      "Effect": "Allow",
      "Action": "ec2:StopInstances",
      "Resource": "*",
      "Condition": {
        "StringEquals": { "ec2:ResourceTag/Name": "resy-bot-snipe" }
      }
    }
  ]
}
```

---

## Step 4: Create EC2 Instance

```bash
aws ec2 run-instances \
  --image-id <latest-al2023-ami> \
  --instance-type t3.micro \
  --iam-instance-profile Name=ResyBotEC2Role \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=resy-bot-snipe}]' \
  --metadata-options "HttpTokens=required,HttpEndpoint=enabled" \
  --query 'Instances[0].InstanceId' --output text
```

Then run the setup script on it:
```bash
# Via SSM Session Manager or SSH
bash deploy/ec2-setup.sh
```

Stop the instance after setup — it only runs during snipes:
```bash
aws ec2 stop-instances --instance-ids <instance-id>
```

---

## Step 5: Create Lambda Function

1. Lambda → Create function
2. Name: `resy-bot-snipe`
3. Runtime: Python 3.12
4. Architecture: x86_64
5. Execution role: `ResyBotLambdaRole`
6. Memory: 128 MB
7. Timeout: 30 seconds

After creation, deploy code:
```bash
EC2_INSTANCE_ID=<instance-id> bash deploy/deploy.sh
```

---

## Step 6: Add EventBridge Permission to Lambda

```bash
aws lambda add-permission \
  --function-name resy-bot-snipe \
  --statement-id eventbridge-invoke \
  --action lambda:InvokeFunction \
  --principal events.amazonaws.com
```

---

## Step 7: Create Local IAM User

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
      "Action": [
        "lambda:GetFunction", "lambda:UpdateFunctionCode",
        "lambda:UpdateFunctionConfiguration", "lambda:GetFunctionConfiguration",
        "lambda:InvokeFunction"
      ],
      "Resource": "arn:aws:lambda:us-east-1:*:function:resy-bot-snipe"
    },
    {
      "Effect": "Allow",
      "Action": [
        "ec2:RunInstances", "ec2:DescribeInstances", "ec2:StartInstances",
        "ec2:StopInstances", "ec2:CreateTags", "ec2:DescribeKeyPairs",
        "ec2:DescribeImages", "ec2:DescribeSecurityGroups", "ec2:DescribeSubnets"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "ssm:PutParameter", "ssm:GetParameter",
        "ssm:SendCommand", "ssm:GetCommandInvocation"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": "iam:PassRole",
      "Resource": "arn:aws:iam::*:role/ResyBotEC2Role"
    }
  ]
}
```

4. Create access key for this user
5. Run `aws configure` on your laptop with the access key

---

## Step 8: Configure Local Environment

Create `backend/.env`:
```
DASHBOARD_API_KEY=<pick-a-strong-key>
LAMBDA_ARN=arn:aws:lambda:us-east-1:<account-id>:function:resy-bot-snipe
EC2_INSTANCE_ID=<instance-id>
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
| Lambda `resy-bot-snipe` | Thin trigger: writes SSM param, starts EC2 |
| EC2 `resy-bot-snipe` (t3.micro) | Runs Playwright snipe, self-stops |
| SSM `/resy-bot/pending-target-id` | Passes target ID from Lambda to EC2 |
| IAM role `ResyBotLambdaRole` | Lambda execution permissions |
| IAM role `ResyBotEC2Role` | EC2 execution permissions |
| IAM user `ResyBotLocal` | Local dashboard AWS access |
| EventBridge rules | One per target, triggers Lambda on schedule |
