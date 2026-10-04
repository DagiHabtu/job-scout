"""Gazetteer for reading a posting's LOCATION field — data only, no logic (spec S2).

All entries are lower-case and matched on word boundaries against one location segment at a time
(never against description prose). The user's own country/city are excluded at match time by the
classifier, so this data is profile-independent.
"""

from __future__ import annotations

import re

COUNTRIES: frozenset[str] = frozenset({
    # UN member and observer states, common English names
    "afghanistan", "albania", "algeria", "andorra", "angola", "antigua and barbuda", "argentina",
    "armenia", "australia", "austria", "azerbaijan", "bahamas", "bahrain", "bangladesh", "barbados",
    "belarus", "belgium", "belize", "benin", "bhutan", "bolivia", "bosnia and herzegovina", "botswana",
    "brazil", "brunei", "bulgaria", "burkina faso", "burundi", "cabo verde", "cape verde", "cambodia",
    "cameroon", "canada", "central african republic", "chad", "chile", "china", "colombia", "comoros",
    "congo", "democratic republic of the congo", "drc", "costa rica", "cote d'ivoire", "côte d'ivoire",
    "ivory coast", "croatia", "cuba", "cyprus", "czechia", "czech republic", "denmark", "djibouti",
    "dominica", "dominican republic", "ecuador", "egypt", "el salvador", "equatorial guinea", "eritrea",
    "estonia", "eswatini", "swaziland", "ethiopia", "fiji", "finland", "france", "gabon", "gambia",
    "georgia", "germany", "ghana", "greece", "grenada", "guatemala", "guinea", "guinea-bissau", "guyana",
    "haiti", "honduras", "hungary", "iceland", "india", "indonesia", "iran", "iraq", "ireland", "israel",
    "italy", "jamaica", "japan", "jordan", "kazakhstan", "kenya", "kiribati", "kosovo", "kuwait",
    "kyrgyzstan", "laos", "latvia", "lebanon", "lesotho", "liberia", "libya", "liechtenstein",
    "lithuania", "luxembourg", "madagascar", "malawi", "malaysia", "maldives", "mali", "malta",
    "marshall islands", "mauritania", "mauritius", "mexico", "micronesia", "moldova", "monaco",
    "mongolia", "montenegro", "morocco", "mozambique", "myanmar", "burma", "namibia", "nauru", "nepal",
    "netherlands", "the netherlands", "holland", "new zealand", "nicaragua", "niger", "nigeria",
    "north korea", "north macedonia", "macedonia", "norway", "oman", "pakistan", "palau", "palestine",
    "panama", "papua new guinea", "paraguay", "peru", "philippines", "poland", "portugal", "qatar",
    "romania", "russia", "russian federation", "rwanda", "saint kitts and nevis", "saint lucia",
    "saint vincent and the grenadines", "samoa", "san marino", "sao tome and principe", "saudi arabia",
    "ksa", "senegal", "serbia", "seychelles", "sierra leone", "singapore", "slovakia", "slovenia",
    "solomon islands", "somalia", "south africa", "south korea", "korea", "republic of korea",
    "south sudan", "spain", "sri lanka", "sudan", "suriname", "sweden", "switzerland", "syria",
    "taiwan", "tajikistan", "tanzania", "thailand", "timor-leste", "east timor", "togo", "tonga",
    "trinidad and tobago", "tunisia", "turkey", "türkiye", "turkiye", "turkmenistan", "tuvalu",
    "uganda", "ukraine", "united arab emirates", "uae", "united kingdom", "uk", "u.k.", "great britain",
    "britain", "england", "scotland", "wales", "northern ireland", "united states",
    "united states of america", "usa", "u.s.a.", "u.s.", "us", "uruguay", "uzbekistan", "vanuatu",
    "vatican city", "venezuela", "vietnam", "viet nam", "yemen", "zambia", "zimbabwe",
    # territories that appear as job locations
    "hong kong", "macau", "puerto rico", "greenland",
})

# Named regions that do NOT include Ethiopia.
REGIONS_EXCLUDING_AFRICA: frozenset[str] = frozenset({
    "americas", "amer", "north america", "latam", "latin america", "south america", "central america",
    "apac", "asia pacific", "asia", "oceania", "europe", "eu", "european union", "eea", "dach",
    "nordics", "benelux", "anz", "middle east",
    # African sub-regions that do not contain Ethiopia (they contain the word "africa")
    "north africa", "northern africa", "west africa", "western africa", "southern africa", "central africa",
})

# Named regions that DO include Ethiopia.
REGIONS_INCLUDING_AFRICA: frozenset[str] = frozenset({
    "africa", "emea", "mea", "middle east and africa", "east africa", "eastern africa", "horn of africa",
    "sub-saharan africa",
})

US_STATES: frozenset[str] = frozenset({
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado", "connecticut", "delaware",
    "florida", "hawaii", "idaho", "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana",
    "maine", "maryland", "massachusetts", "michigan", "minnesota", "mississippi", "missouri", "montana",
    "nebraska", "nevada", "new hampshire", "new jersey", "new mexico", "north carolina", "north dakota",
    "ohio", "oklahoma", "oregon", "pennsylvania", "rhode island", "south carolina", "south dakota",
    "tennessee", "texas", "utah", "vermont", "virginia", "washington", "west virginia", "wisconsin",
    "wyoming",
})

WORLDWIDE_TOKENS: frozenset[str] = frozenset({"worldwide", "global", "anywhere", "international"})

# Cities seen in practice → country. Extend from the funnel's rejected samples.
CITIES: dict[str, str] = {
    "bangalore": "india", "bengaluru": "india", "hyderabad": "india", "pune": "india",
    "mumbai": "india", "delhi": "india", "new delhi": "india", "gurgaon": "india", "gurugram": "india",
    "noida": "india", "chennai": "india",
    "london": "united kingdom", "manchester": "united kingdom", "edinburgh": "united kingdom",
    "dublin": "ireland", "berlin": "germany", "munich": "germany", "hamburg": "germany",
    "paris": "france", "amsterdam": "netherlands", "madrid": "spain", "barcelona": "spain",
    "lisbon": "portugal", "warsaw": "poland", "krakow": "poland", "kraków": "poland",
    "prague": "czechia", "vienna": "austria", "zurich": "switzerland", "zürich": "switzerland",
    "stockholm": "sweden", "copenhagen": "denmark", "oslo": "norway", "helsinki": "finland",
    "tel aviv": "israel", "dubai": "united arab emirates", "abu dhabi": "united arab emirates",
    "riyadh": "saudi arabia", "istanbul": "turkey",
    "new york": "united states", "nyc": "united states", "san francisco": "united states",
    "seattle": "united states", "austin": "united states", "boston": "united states",
    "chicago": "united states", "los angeles": "united states", "denver": "united states",
    "toronto": "canada", "vancouver": "canada", "montreal": "canada",
    "mexico city": "mexico", "sao paulo": "brazil", "são paulo": "brazil", "buenos aires": "argentina",
    "bogota": "colombia", "bogotá": "colombia",
    "tokyo": "japan", "seoul": "south korea", "manila": "philippines", "jakarta": "indonesia",
    "sydney": "australia", "melbourne": "australia", "auckland": "new zealand",
    "lagos": "nigeria", "nairobi": "kenya", "cape town": "south africa", "johannesburg": "south africa",
    "cairo": "egypt", "kigali": "rwanda", "accra": "ghana",
}

# "San Francisco, CA" — a trailing two-letter upper-case code (applied to the RAW segment).
US_STATE = re.compile(r",\s*[A-Z]{2}$")
