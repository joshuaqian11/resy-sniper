import pytest
from unittest.mock import MagicMock, patch
from sms import SMSClient

@pytest.fixture
def client():
    return SMSClient(
        account_sid="AC123",
        auth_token="twil-tok",
        from_number="+15550001111",
        to_number="+15559998888",
    )

def test_send_calls_twilio(client):
    mock_twilio = MagicMock()
    mock_twilio.messages.create.return_value = MagicMock(sid="SM123")
    with patch("sms.Client", return_value=mock_twilio):
        client = SMSClient("AC123", "tok", "+15550001111", "+15559998888")
        client.send("Test message")
    mock_twilio.messages.create.assert_called_once_with(
        body="Test message",
        from_="+15550001111",
        to="+15559998888",
    )

def test_send_does_not_raise_on_twilio_error(client):
    mock_twilio = MagicMock()
    mock_twilio.messages.create.side_effect = Exception("Twilio error")
    with patch("sms.Client", return_value=mock_twilio):
        c = SMSClient("AC123", "tok", "+15550001111", "+15559998888")
        c.send("Test")  # Should not raise

def test_send_skipped_when_no_credentials():
    c = SMSClient("", "", "", "")
    c.send("This should be a no-op")  # Should not raise
