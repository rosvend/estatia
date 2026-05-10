from estatia.models import Budget, Location, PropertyPreferences, PropertyType, UserRequest
from estatia.services import SeedListingService, SeedNewsService


def test_listing_service_filters_by_city_budget_and_type():
    request = UserRequest(
        raw_text="rent in bogota",
        search_summary="Bogota apartment under budget",
        location=Location(city="Bogota"),
        budget=Budget(max=3000000),
        property=PropertyPreferences(type=PropertyType.APARTMENT),
    )

    results = SeedListingService().search(request)

    assert results
    assert all(item.location.city == "Bogota" for item in results)
    assert all(item.price <= 3000000 for item in results)
    assert all(item.property.type == PropertyType.APARTMENT for item in results)


def test_news_service_uses_listing_neighborhoods_when_request_is_broad():
    request = UserRequest(raw_text="need options", search_summary="broad request")
    listings = SeedListingService().search(
        UserRequest(
            raw_text="Medellin apartment",
            search_summary="Medellin apartment",
            location=Location(city="Medellin"),
        )
    )

    news = SeedNewsService().search(request, listings)

    assert news
