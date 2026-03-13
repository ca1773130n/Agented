from app.models.trigger import CreateTriggerRequest, UpdateTriggerRequest, Trigger


class TestTriggerModelDispatchFields:
    def test_create_request_defaults_to_bot(self):
        req = CreateTriggerRequest(name="test", prompt_template="do stuff")
        assert req.dispatch_type == "bot"
        assert req.super_agent_id is None

    def test_create_request_with_super_agent(self):
        req = CreateTriggerRequest(
            name="test",
            prompt_template="do stuff",
            dispatch_type="super_agent",
            super_agent_id="sa-abc123",
        )
        assert req.dispatch_type == "super_agent"
        assert req.super_agent_id == "sa-abc123"

    def test_update_request_accepts_dispatch_fields(self):
        req = UpdateTriggerRequest(dispatch_type="super_agent", super_agent_id="sa-abc123")
        assert req.dispatch_type == "super_agent"
        assert req.super_agent_id == "sa-abc123"

    def test_trigger_response_includes_dispatch_fields(self):
        t = Trigger(
            id="trig-123abc",
            name="test",
            prompt_template="do stuff",
            backend_type="claude",
            trigger_source="webhook",
            dispatch_type="super_agent",
            super_agent_id="sa-abc123",
        )
        assert t.dispatch_type == "super_agent"
        assert t.super_agent_id == "sa-abc123"

    def test_trigger_response_defaults(self):
        t = Trigger(
            id="trig-123abc",
            name="test",
            prompt_template="do stuff",
            backend_type="claude",
            trigger_source="webhook",
        )
        assert t.dispatch_type == "bot"
        assert t.super_agent_id is None
