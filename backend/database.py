import json
import uuid
import boto3
from datetime import datetime, timezone
from typing import Optional


class Database:
    def __init__(self, region: str = "us-east-1"):
        self._dynamodb = boto3.resource("dynamodb", region_name=region)
        self._targets = self._dynamodb.Table("resy-bot-targets")
        self._config = self._dynamodb.Table("resy-bot-config")

    def insert_target(self, t: dict) -> str:
        target_id = str(uuid.uuid4())
        item = {
            "id": target_id,
            "venue_id": t["venue_id"],
            "venue_name": t["venue_name"],
            "date": t["date"],
            "party_size": t["party_size"],
            "opening_time": t["opening_time"],
            "status": "pending",
        }
        for key in ("preferred_time", "window_start", "window_end"):
            if t.get(key):
                item[key] = t[key]
        self._targets.put_item(Item=item)
        return target_id

    def get_all_targets(self) -> list[dict]:
        response = self._targets.scan()
        items = response.get("Items", [])
        for item in items:
            if "party_size" in item:
                item["party_size"] = int(item["party_size"])
        return sorted(items, key=lambda x: x.get("opening_time", ""))

    def get_target(self, target_id: str) -> Optional[dict]:
        response = self._targets.get_item(Key={"id": target_id})
        item = response.get("Item")
        if item and "party_size" in item:
            item["party_size"] = int(item["party_size"])
        return item

    def update_target_status(self, target_id: str, status: str):
        self._targets.update_item(
            Key={"id": target_id},
            UpdateExpression="SET #s = :status",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":status": status},
        )

    def update_target_booked(self, target_id: str, reservation_details: dict):
        now = datetime.now(timezone.utc).isoformat()
        self._targets.update_item(
            Key={"id": target_id},
            UpdateExpression="SET #s = :status, booked_at = :booked_at, reservation_details = :details",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":status": "booked",
                ":booked_at": now,
                ":details": json.dumps(reservation_details),
            },
        )

    def delete_target_if_pending(self, target_id: str) -> bool:
        try:
            self._targets.delete_item(
                Key={"id": target_id},
                ConditionExpression="#s = :pending",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={":pending": "pending"},
            )
            return True
        except self._dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
            return False

    def complete_past_targets(self):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        response = self._targets.scan(
            FilterExpression="#s IN (:booked, :failed) AND #d < :today",
            ExpressionAttributeNames={"#s": "status", "#d": "date"},
            ExpressionAttributeValues={
                ":booked": "booked",
                ":failed": "failed",
                ":today": today,
            },
        )
        for item in response.get("Items", []):
            self.update_target_status(item["id"], "completed")

    def set_config(self, key: str, value: str):
        self._config.put_item(Item={"key": key, "value": value})

    def get_config(self, key: str) -> Optional[str]:
        response = self._config.get_item(Key={"key": key})
        item = response.get("Item")
        return item["value"] if item else None

    def get_all_config(self) -> dict[str, str]:
        response = self._config.scan()
        return {item["key"]: item["value"] for item in response.get("Items", [])}
