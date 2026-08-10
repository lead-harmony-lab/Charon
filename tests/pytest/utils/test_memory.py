import pytest
from charon.utils.memory import ConversationBuffer


class TestConversationBuffer:
    """Test suite targeting 100% statement and branch coverage for ConversationBuffer."""

    def test_init_defaults_and_custom(self):
        """Verifies default and custom max_turns initialization."""
        default_buf = ConversationBuffer()
        assert default_buf.max_turns == 5
        assert default_buf.history == []

        custom_buf = ConversationBuffer(max_turns=3)
        assert custom_buf.max_turns == 3
        assert custom_buf.history == []

    def test_add_user_message(self):
        """Verifies convenience method for adding user messages."""
        buf = ConversationBuffer()
        buf.add_user_message("Hello Charon")
        assert buf.history == [{"role": "user", "content": "Hello Charon"}]

    def test_add_system_message(self):
        """Verifies convenience method for adding assistant messages."""
        buf = ConversationBuffer()
        buf.add_system_message("Standing by.")
        assert buf.history == [{"role": "assistant", "content": "Standing by."}]

    def test_history_truncation_on_overflow(self):
        """Verifies history rolling behavior when exceeding max_turns * 2 limit."""
        buf = ConversationBuffer(max_turns=1)  # Limit = 2 messages

        buf.add_turn("user", "Message 1")
        buf.add_turn("assistant", "Message 2")
        assert len(buf.history) == 2

        # Adding a 3rd message must drop Message 1
        buf.add_turn("user", "Message 3")
        assert len(buf.history) == 2
        assert buf.history == [
            {"role": "assistant", "content": "Message 2"},
            {"role": "user", "content": "Message 3"},
        ]

    def test_get_context_string_empty(self):
        """Verifies output formatting when buffer is empty."""
        buf = ConversationBuffer()
        assert buf.get_context_string() == "No prior conversational context."

    def test_get_context_string_role_mapping(self):
        """Verifies speaker string mapping for user/human vs assistant/other roles."""
        buf = ConversationBuffer()
        buf.add_turn("USER", "Prompt 1")
        buf.add_turn("human", "Prompt 2")
        buf.add_turn("assistant", "Response 1")
        buf.add_turn("system", "System note")

        expected_context = (
            "User: Prompt 1\n"
            "User: Prompt 2\n"
            "Charon: Response 1\n"
            "Charon: System note"
        )
        assert buf.get_context_string() == expected_context

    def test_clear_buffer_and_logging(self, caplog):
        """Verifies buffer flushing and log output emission."""
        buf = ConversationBuffer()
        buf.add_user_message("Temporary memory")
        assert len(buf.history) == 1

        with caplog.at_level("INFO"):
            buf.clear()

        assert len(buf.history) == 0
        assert "Conversation memory buffer cleared." in caplog.text
