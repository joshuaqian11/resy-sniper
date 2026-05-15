# IAM Setup for Resy Bot

This document covers the manual AWS Console steps required to configure IAM roles for the bot's EC2 instance and EventBridge scheduler.

---

## Step 1: Create EC2 IAM Role

1. Open the AWS Console and navigate to **IAM → Roles → Create Role**.
2. Under **Trusted entity type**, select **AWS service**, then choose **EC2**.
3. Click **Next** through the permissions screen (you will add an inline policy manually).
4. Name the role `ResyBotEC2Role` and click **Create role**.
5. Open the newly created role, go to the **Permissions** tab, and click **Add permissions → Create inline policy**.
6. Switch to the **JSON** editor and paste the following policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "events:PutRule",
        "events:PutTargets",
        "events:DeleteRule",
        "events:RemoveTargets",
        "events:ListRules"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": ["ec2:StopInstances"],
      "Resource": "*"
    }
  ]
}
```

7. Click **Next**, give the inline policy a name (e.g., `ResyBotEC2InlinePolicy`), and click **Create policy**.

---

## Step 2: Create EventBridge IAM Role

1. Open the AWS Console and navigate to **IAM → Roles → Create Role**.
2. Under **Trusted entity type**, select **AWS service**, then choose **EventBridge** (or search for `events.amazonaws.com` under custom trust policy if EventBridge is not listed directly).
3. If prompted for a use case, select **EventBridge**.
4. Click **Next** through the permissions screen.
5. Name the role `ResyBotEventBridgeRole` and click **Create role**.
6. Open the newly created role, go to the **Permissions** tab, and click **Add permissions → Create inline policy**.
7. Switch to the **JSON** editor and paste the following policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "ssm:StartAutomationExecution",
      "Resource": "arn:aws:ssm:*::automation-definition/AWS-StartEC2Instance"
    }
  ]
}
```

8. Click **Next**, give the inline policy a name (e.g., `ResyBotEventBridgeInlinePolicy`), and click **Create policy**.

---

## Step 3: Attach the EC2 Role to the Instance

1. Open the AWS Console and navigate to **EC2 → Instances**.
2. Select the Resy bot instance.
3. Click **Actions → Security → Modify IAM Role**.
4. In the **IAM role** dropdown, select `ResyBotEC2Role`.
5. Click **Update IAM role**.

---

## Step 4: Add the EventBridge Role ARN to `.env`

After the roles are created, the EventBridge role ARN must be added to the bot's environment file on the instance.

1. In the AWS Console, navigate to **IAM → Roles → ResyBotEventBridgeRole**.
2. Copy the **ARN** shown at the top of the role summary page (format: `arn:aws:iam::<account-id>:role/ResyBotEventBridgeRole`).
3. SSH into the EC2 instance and append the ARN to `/opt/resy-bot/.env`:

```bash
# Replace the ARN below with the actual ARN copied from the IAM Console
echo "EVENTBRIDGE_ROLE_ARN=arn:aws:iam::123456789:role/ResyBotEventBridgeRole" >> /opt/resy-bot/.env
```

4. Verify the value was written correctly:

```bash
grep EVENTBRIDGE_ROLE_ARN /opt/resy-bot/.env
```

---

## Summary of Roles

| Role Name                | Trusted Entity              | Purpose                                                      |
|--------------------------|-----------------------------|--------------------------------------------------------------|
| `ResyBotEC2Role`         | EC2 (`ec2.amazonaws.com`)   | Allows the bot process to manage EventBridge rules and stop the instance after a snipe completes. |
| `ResyBotEventBridgeRole` | EventBridge (`events.amazonaws.com`) | Allows EventBridge to trigger SSM Automation to start the EC2 instance on a schedule. |
