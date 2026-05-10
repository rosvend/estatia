from estatia.models import Budget, Intent, PropertyType, UserRequest


def test_budget_currency_normalizes_to_uppercase():
    budget = Budget(currency="cop", max=3000000)
    assert budget.currency == "COP"


def test_user_request_defaults_are_stable():
    request = UserRequest(raw_text="rent me something", search_summary="short summary")
    assert request.intent == Intent.RENT
    assert request.property.type == PropertyType.ANY
    assert request.constraints.must_have == []
