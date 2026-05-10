from estatia.models import Listing, ListingLocation, ListingProperty, NewsInsight, PropertyType


SAMPLE_LISTINGS = [
    Listing(
        id="bog-apt-001",
        source="seed",
        url="https://example.com/listings/bog-apt-001",
        title="Modern apartment near Parque 93",
        price=4200000,
        location=ListingLocation(
            city="Bogota",
            neighborhood="Chico Norte",
            address="Calle 94 #13-20",
        ),
        property=ListingProperty(type=PropertyType.APARTMENT, bedrooms=2, bathrooms=2, area_m2=78),
        highlights=["Walkable area", "Coworking lounge", "Natural light"],
        images=["https://example.com/images/bog-apt-001.jpg"],
    ),
    Listing(
        id="bog-apt-002",
        source="seed",
        url="https://example.com/listings/bog-apt-002",
        title="Budget apartment in Teusaquillo",
        price=2600000,
        location=ListingLocation(
            city="Bogota",
            neighborhood="Teusaquillo",
            address="Carrera 21 #45-12",
        ),
        property=ListingProperty(type=PropertyType.APARTMENT, bedrooms=2, bathrooms=1, area_m2=63),
        highlights=["Good transit", "Quiet street", "Renovated kitchen"],
        images=["https://example.com/images/bog-apt-002.jpg"],
    ),
    Listing(
        id="bog-house-003",
        source="seed",
        url="https://example.com/listings/bog-house-003",
        title="Family house in Cedritos",
        price=6800000,
        location=ListingLocation(
            city="Bogota",
            neighborhood="Cedritos",
            address="Calle 146 #12-44",
        ),
        property=ListingProperty(type=PropertyType.HOUSE, bedrooms=3, bathrooms=3, area_m2=142),
        highlights=["Garage", "Near schools", "Private patio"],
        images=["https://example.com/images/bog-house-003.jpg"],
    ),
    Listing(
        id="med-apt-004",
        source="seed",
        url="https://example.com/listings/med-apt-004",
        title="Remote-work apartment in Laureles",
        price=3500000,
        location=ListingLocation(
            city="Medellin",
            neighborhood="Laureles",
            address="Circular 3 #70-50",
        ),
        property=ListingProperty(type=PropertyType.APARTMENT, bedrooms=1, bathrooms=2, area_m2=74),
        highlights=["Fast internet", "Cafe district", "Balcony"],
        images=["https://example.com/images/med-apt-004.jpg"],
    ),
    Listing(
        id="med-apt-005",
        source="seed",
        url="https://example.com/listings/med-apt-005",
        title="High-rise apartment in El Poblado",
        price=5900000,
        location=ListingLocation(
            city="Medellin",
            neighborhood="El Poblado",
            address="Carrera 43A #11-55",
        ),
        property=ListingProperty(type=PropertyType.APARTMENT, bedrooms=2, bathrooms=2, area_m2=88),
        highlights=["Amenities tower", "Close to offices", "Strong resale demand"],
        images=["https://example.com/images/med-apt-005.jpg"],
    ),
]


SAMPLE_NEWS = [
    NewsInsight(
        neighborhood="Teusaquillo",
        title="Transit upgrades continue around Teusaquillo",
        summary="Infrastructure work is improving public transport access and commute reliability.",
        source="Local Mobility Bulletin",
        url="https://example.com/news/teusaquillo-transit",
    ),
    NewsInsight(
        neighborhood="Laureles",
        title="Laureles demand remains strong for long-stay renters",
        summary="Rental demand is stable due to walkability and mixed residential-commercial use.",
        source="Metro Property Watch",
        url="https://example.com/news/laureles-demand",
    ),
    NewsInsight(
        neighborhood="Cedritos",
        title="Family-oriented developments keep Cedritos competitive",
        summary="Schools, parks, and larger homes continue to support the area for family buyers.",
        source="Capital Housing Report",
        url="https://example.com/news/cedritos-family",
    ),
]
