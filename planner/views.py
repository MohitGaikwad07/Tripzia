from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from .models import Trip, Booking, RouteHistory
import requests
from django.conf import settings
import json
from copy import deepcopy

GEOCODE_CACHE = {}
PLACE_CANDIDATES_CACHE = {}
ACTIVITY_METADATA = {
    "nature": {
        "label": "nature",
        "keywords": ["nature", "garden", "park", "lake", "hill", "forest", "trail", "viewpoint", "green"],
    },
    "adventure": {
        "label": "adventure",
        "keywords": ["adventure", "trek", "rafting", "climb", "camp", "zipline", "outdoor", "sports"],
    },
    "food": {
        "label": "food",
        "keywords": ["food", "restaurant", "cafe", "dining", "culinary", "street food", "meal"],
    },
    "shopping": {
        "label": "shopping",
        "keywords": ["shopping", "market", "bazaar", "mall", "souvenir", "retail"],
    },
    "history": {
        "label": "history",
        "keywords": ["history", "heritage", "museum", "fort", "palace", "monument", "temple", "old city"],
    },
}


def selected_activity_labels(activities):
    if not activities:
        return ["general sightseeing"]
    return [ACTIVITY_METADATA.get(activity, {}).get("label", activity) for activity in activities]


def infer_activity_focus(item, selected_activities):
    explicit_focus = (item.get("activity_focus") or "").strip().lower()
    if explicit_focus in ACTIVITY_METADATA:
        return explicit_focus

    haystack = " ".join(
        str(item.get(key, "")) for key in ("name", "title", "description", "meal")
    ).lower()

    for activity in selected_activities:
        keywords = ACTIVITY_METADATA.get(activity, {}).get("keywords", [])
        if any(keyword in haystack for keyword in keywords):
            return activity

    return selected_activities[0] if selected_activities else "general"


def option_covers_selected_activities(option, selected_activities):
    if not selected_activities:
        return True

    covered = set()
    trip = option.get("trip", {}) if isinstance(option, dict) else {}

    for day in trip.get("days", []) if isinstance(trip.get("days", []), list) else []:
        for item in day.get("plan", []) if isinstance(day.get("plan", []), list) else []:
            if not isinstance(item, dict):
                continue
            focus = infer_activity_focus(item, selected_activities)
            if focus in selected_activities:
                covered.add(focus)

    return all(activity in covered for activity in selected_activities)


def all_options_cover_selected_activities(trip_options, selected_activities):
    return all(option_covers_selected_activities(option, selected_activities) for option in trip_options)


def geocode_location(query):
    if not query:
        return None

    normalized_query = query.strip().lower()
    if normalized_query in GEOCODE_CACHE:
        return GEOCODE_CACHE[normalized_query]

    try:
        response = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={
                "q": query,
                "format": "json",
                "limit": 1,
            },
            headers={
                "User-Agent": "travel-planner-app/1.0"
            },
            timeout=8,
        )
        response.raise_for_status()
        results = response.json()
    except requests.RequestException:
        GEOCODE_CACHE[normalized_query] = None
        return None

    if not results:
        GEOCODE_CACHE[normalized_query] = None
        return None

    first_result = results[0]
    resolved = {
        "lat": float(first_result["lat"]),
        "lng": float(first_result["lon"]),
        "label": first_result.get("display_name", query),
    }
    GEOCODE_CACHE[normalized_query] = resolved
    return resolved


def coerce_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def is_valid_coordinate(lat, lng):
    return lat is not None and lng is not None and -90 <= lat <= 90 and -180 <= lng <= 180


def find_place_coordinates(name, destination):
    search_queries = []
    if name and destination:
        search_queries.append(f"{name}, {destination}")
    if name:
        search_queries.append(name)
    if destination:
        search_queries.append(destination)

    for query in search_queries:
        point = geocode_location(query)
        if point:
            return point

    return None


def build_place_photo_url(photo_reference):
    if not photo_reference or not getattr(settings, "GOOGLE_API_KEY", None):
        return None

    return (
        "https://maps.googleapis.com/maps/api/place/photo"
        f"?maxwidth=800&photo_reference={photo_reference}&key={settings.GOOGLE_API_KEY}"
    )


def lookup_place_details(query):
    candidates = lookup_place_candidates(query, limit=1)
    return candidates[0] if candidates else None


def lookup_place_candidates(query, limit=5):
    if not query or not getattr(settings, "GOOGLE_API_KEY", None):
        return []

    cache_key = (query.strip().lower(), limit)
    if cache_key in PLACE_CANDIDATES_CACHE:
        return deepcopy(PLACE_CANDIDATES_CACHE[cache_key])

    try:
        response = requests.get(
            "https://maps.googleapis.com/maps/api/place/textsearch/json",
            params={
                "query": query,
                "key": settings.GOOGLE_API_KEY,
            },
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException:
        PLACE_CANDIDATES_CACHE[cache_key] = []
        return []

    candidates = []
    for place in (data.get("results") or [])[:limit]:
        location = place.get("geometry", {}).get("location", {})
        photos = place.get("photos") or []
        photo_reference = photos[0].get("photo_reference") if photos else None
        candidates.append({
            "name": place.get("name"),
            "address": place.get("formatted_address"),
            "rating": place.get("rating"),
            "price_level": place.get("price_level"),
            "lat": location.get("lat"),
            "lng": location.get("lng"),
            "photo_url": build_place_photo_url(photo_reference),
        })

    PLACE_CANDIDATES_CACHE[cache_key] = deepcopy(candidates)
    return candidates


def enrich_item_with_real_place(item, destination, minimum_rating):
    if not isinstance(item, dict):
        return item

    item_type = item.get("type")
    if item_type not in {"place", "restaurant", "hotel"}:
        return item

    base_query = item.get("name") or item.get("title")
    place_details = lookup_place_details(f"{base_query}, {destination}") or lookup_place_details(base_query)
    if not place_details:
        return item

    try:
        resolved_rating = float(place_details.get("rating") or minimum_rating)
    except (TypeError, ValueError):
        resolved_rating = minimum_rating

    if resolved_rating < minimum_rating:
        return item

    item["name"] = place_details.get("name") or item.get("name") or item.get("title")
    item["title"] = item.get("title") or item["name"]
    item["lat"] = place_details.get("lat") or item.get("lat")
    item["lng"] = place_details.get("lng") or item.get("lng")
    item["image_url"] = place_details.get("photo_url")
    item["address"] = place_details.get("address")
    item["rating"] = max(resolved_rating, minimum_rating)
    item["price_level"] = place_details.get("price_level")

    if item_type == "restaurant" and not item.get("description"):
        item["description"] = f"A dining stop at {item['name']}."
    if item_type == "hotel" and not item.get("description"):
        item["description"] = f"A stay option at {item['name']}."

    return item


def diversify_options_with_real_places(trip_options, destination, minimum_rating):
    used_names = {"place": set(), "restaurant": set(), "hotel": set()}
    query_hint = {
        "place": destination,
        "restaurant": f"best restaurant in {destination}",
        "hotel": f"best hotel in {destination}",
    }

    for option in trip_options:
        trip = option.get("trip", {}) if isinstance(option, dict) else {}
        for day in trip.get("days", []) if isinstance(trip.get("days", []), list) else []:
            for item in day.get("plan", []) if isinstance(day.get("plan", []), list) else []:
                if not isinstance(item, dict):
                    continue

                item_type = item.get("type")
                if item_type not in used_names:
                    continue

                base_name = item.get("name") or item.get("title") or query_hint[item_type]
                queries = [f"{base_name}, {destination}", query_hint[item_type], destination]
                chosen_candidate = None

                for query in queries:
                    candidates = lookup_place_candidates(query)
                    for candidate in candidates:
                        candidate_name = (candidate.get("name") or "").strip().lower()
                        if not candidate_name or candidate_name in used_names[item_type]:
                            continue
                        try:
                            candidate_rating = float(candidate.get("rating") or minimum_rating)
                        except (TypeError, ValueError):
                            candidate_rating = minimum_rating
                        if candidate_rating < minimum_rating:
                            continue
                        chosen_candidate = candidate
                        break
                    if chosen_candidate:
                        break

                if chosen_candidate:
                    item["name"] = chosen_candidate.get("name") or item.get("name") or item.get("title")
                    item["title"] = item.get("title") or item["name"]
                    item["lat"] = chosen_candidate.get("lat") or item.get("lat")
                    item["lng"] = chosen_candidate.get("lng") or item.get("lng")
                    item["image_url"] = chosen_candidate.get("photo_url")
                    item["address"] = chosen_candidate.get("address")
                    item["price_level"] = chosen_candidate.get("price_level")
                    if chosen_candidate.get("rating"):
                        item["rating"] = max(float(chosen_candidate["rating"]), minimum_rating)
                    used_names[item_type].add((item["name"] or "").strip().lower())
                else:
                    normalized_name = (item.get("name") or item.get("title") or "").strip().lower()
                    if normalized_name:
                        used_names[item_type].add(normalized_name)

    return trip_options


def option_signature(option):
    trip = option.get("trip", {}) if isinstance(option, dict) else {}
    grouped_names = {"place": [], "restaurant": [], "hotel": []}
    for day in trip.get("days", []) if isinstance(trip.get("days", []), list) else []:
        for item in day.get("plan", []) if isinstance(day.get("plan", []), list) else []:
            if not isinstance(item, dict):
                continue
            item_type = item.get("type")
            if item_type in grouped_names:
                grouped_names[item_type].append((item.get("name") or item.get("title") or "").strip().lower())
    return (
        tuple(grouped_names["place"]),
        tuple(grouped_names["restaurant"]),
        tuple(grouped_names["hotel"]),
    )


def options_have_conflicts(trip_options):
    seen_by_type = {"place": set(), "restaurant": set(), "hotel": set()}

    for option in trip_options:
        trip = option.get("trip", {}) if isinstance(option, dict) else {}
        option_names = {"place": set(), "restaurant": set(), "hotel": set()}

        for day in trip.get("days", []) if isinstance(trip.get("days", []), list) else []:
            for item in day.get("plan", []) if isinstance(day.get("plan", []), list) else []:
                if not isinstance(item, dict):
                    continue
                item_type = item.get("type")
                normalized_name = (item.get("name") or item.get("title") or "").strip().lower()
                if item_type in option_names and normalized_name:
                    option_names[item_type].add(normalized_name)

        for item_type, names in option_names.items():
            if names & seen_by_type[item_type]:
                return True
            seen_by_type[item_type].update(names)

    return False


def ensure_distinct_options(trip_options):
    distinct = []
    seen = set()

    for option in trip_options:
        signature = option_signature(option)
        if signature in seen:
            continue
        seen.add(signature)
        distinct.append(option)

    return distinct


def estimate_item_cost(item, budget):
    item_type = (item.get("type") or "place").lower()
    try:
        rating = float(item.get("rating", 4.0))
    except (TypeError, ValueError):
        rating = 4.0
    try:
        price_level = int(item.get("price_level", 0) or 0)
    except (TypeError, ValueError):
        price_level = 0

    base_costs = {
        "low": {"travel": 900, "place": 500, "restaurant": 450, "hotel": 1800},
        "medium": {"travel": 1600, "place": 900, "restaurant": 850, "hotel": 3200},
        "high": {"travel": 3000, "place": 1600, "restaurant": 1500, "hotel": 6500},
    }
    selected_costs = base_costs.get(budget, base_costs["medium"])
    base_amount = selected_costs.get(item_type, 700)
    rating_multiplier = 1 + max(rating - 4.0, 0) * 0.22
    name_seed = (item.get("name") or item.get("title") or item_type).strip().lower()
    address_seed = (item.get("address") or "").strip().lower()
    duration_seed = (item.get("duration") or item.get("time_to_spend") or "").strip().lower()
    combined_seed = f"{name_seed}|{address_seed}|{duration_seed}|{item_type}"
    seed_value = sum(ord(ch) for ch in combined_seed)

    variability_band = 0.85 + ((seed_value % 31) / 100)

    keyword_multiplier = 1.0
    if item_type == "hotel":
        luxury_keywords = ["palace", "grand", "taj", "oberoi", "resort", "suite", "luxury", "premium", "marriott", "hyatt"]
        budget_keywords = ["inn", "hostel", "lodge", "guest house", "budget"]
        if any(keyword in name_seed for keyword in luxury_keywords):
            keyword_multiplier = 1.35
        elif any(keyword in name_seed for keyword in budget_keywords):
            keyword_multiplier = 0.85
    elif item_type == "restaurant":
        premium_dining_keywords = ["grill", "kitchen", "fine", "bistro", "club", "bar", "signature"]
        if any(keyword in name_seed for keyword in premium_dining_keywords):
            keyword_multiplier = 1.18
    elif item_type == "place":
        landmark_keywords = ["museum", "fort", "palace", "temple", "national park", "sanctuary", "tower"]
        if any(keyword in name_seed for keyword in landmark_keywords):
            keyword_multiplier = 1.12

    price_level_multiplier = 1.0
    if item_type in {"restaurant", "hotel"} and price_level > 0:
        price_level_multiplier = {
            1: 0.8,
            2: 1.0,
            3: 1.22,
            4: 1.5,
        }.get(price_level, 1.0)

    return int(round(base_amount * rating_multiplier * variability_band * keyword_multiplier * price_level_multiplier))


def format_inr(amount):
    return f"Rs. {amount:,}"


def haversine_km(lat1, lng1, lat2, lng2):
    lat1 = coerce_float(lat1)
    lng1 = coerce_float(lng1)
    lat2 = coerce_float(lat2)
    lng2 = coerce_float(lng2)

    if not is_valid_coordinate(lat1, lng1) or not is_valid_coordinate(lat2, lng2):
        return 0

    from math import radians, sin, cos, sqrt, atan2

    earth_radius = 6371
    dlat = radians(lat2 - lat1)
    dlng = radians(lng2 - lng1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    return earth_radius * 2 * atan2(sqrt(a), sqrt(1 - a))


def estimate_route_travel_cost(days, budget):
    per_km_rate = {
        "low": 10,
        "medium": 16,
        "high": 25,
    }.get(budget, 16)

    total_distance_km = 0
    for day in days:
        if not isinstance(day, dict):
            continue
        waypoints = []
        for item in day.get("plan", []) if isinstance(day.get("plan", []), list) else []:
            if not isinstance(item, dict):
                continue
            lat = coerce_float(item.get("lat"))
            lng = coerce_float(item.get("lng"))
            if is_valid_coordinate(lat, lng):
                waypoints.append((lat, lng))

        for index in range(1, len(waypoints)):
            total_distance_km += haversine_km(
                waypoints[index - 1][0],
                waypoints[index - 1][1],
                waypoints[index][0],
                waypoints[index][1],
            )

    return int(round(total_distance_km * per_km_rate))


def update_option_costs(trip_options, budget):
    for option in trip_options:
        trip = option.get("trip", {}) if isinstance(option, dict) else {}
        total_cost = 0
        days = trip.get("days", []) if isinstance(trip.get("days", []), list) else []
        for day in days:
            for item in day.get("plan", []) if isinstance(day.get("plan", []), list) else []:
                if not isinstance(item, dict):
                    continue
                item_cost = estimate_item_cost(item, budget)
                item["estimated_cost"] = format_inr(item_cost)
                total_cost += item_cost
        travel_cost = estimate_route_travel_cost(days, budget)
        total_cost += travel_cost
        option["route_travel_cost"] = format_inr(travel_cost)
        option["total_estimated_cost"] = format_inr(total_cost)

    return trip_options


def normalize_trip_options(trip_options, start_location, destination, days, budget, activities):
    if not isinstance(trip_options, list):
        return []

    selected_activities = activities or ["nature", "food", "history"]
    destination_point = geocode_location(destination) or {
        "lat": 20.5937,
        "lng": 78.9629,
    }
    start_point = geocode_location(start_location) or destination_point
    normalized_options = []

    for option_index, raw_option in enumerate(trip_options[:3], start=1):
        option = deepcopy(raw_option) if isinstance(raw_option, dict) else {}
        trip = option.get("trip") if isinstance(option.get("trip"), dict) else {}
        raw_days = trip.get("days") if isinstance(trip.get("days"), list) else []
        normalized_days = []

        for day_index, raw_day in enumerate(raw_days[: max(days, 1)], start=1):
            day = raw_day if isinstance(raw_day, dict) else {}
            raw_plan = day.get("plan") if isinstance(day.get("plan"), list) else []
            normalized_plan = []

            for stop_index, raw_item in enumerate(raw_plan, start=1):
                if not isinstance(raw_item, dict):
                    continue

                item = deepcopy(raw_item)
                item_type = item.get("type") or "place"
                item_name = item.get("name") or item.get("title") or f"{destination} Stop {stop_index}"
                lat = coerce_float(item.get("lat"))
                lng = coerce_float(item.get("lng"))

                if not is_valid_coordinate(lat, lng):
                    resolved_point = find_place_coordinates(item_name, destination)
                    if resolved_point:
                        lat = resolved_point["lat"]
                        lng = resolved_point["lng"]
                    elif item_type == "travel":
                        lat = start_point["lat"]
                        lng = start_point["lng"]
                    else:
                        lat = round(destination_point["lat"] + (day_index * 0.01) + (stop_index * 0.002), 6)
                        lng = round(destination_point["lng"] + (day_index * 0.008) - (stop_index * 0.002), 6)

                item["type"] = item_type
                item["name"] = item_name
                item["title"] = item.get("title") or item_name
                item["lat"] = lat
                item["lng"] = lng
                item["activity_focus"] = infer_activity_focus(item, selected_activities)

                if item_type == "place":
                    item["description"] = item.get("description") or f"Recommended stop in {destination} aligned with {', '.join(activities) if activities else 'your selected interests'}."
                    item["duration"] = item.get("duration") or "2 hours"
                    item["rating"] = item.get("rating") or 4.2
                elif item_type == "restaurant":
                    item["meal"] = item.get("meal") or "meal stop"
                    item["description"] = item.get("description") or f"A well-rated dining stop in {destination}."
                elif item_type == "hotel":
                    item["description"] = item.get("description") or f"A suggested stay option in {destination}."
                elif item_type == "travel":
                    item["description"] = item.get("description") or f"Travel from {start_location} to {destination}."

                normalized_plan.append(item)

            if normalized_plan:
                normalized_days.append({
                    "day": day.get("day") or day_index,
                    "plan": normalized_plan,
                })

        if not normalized_days:
            continue

        normalized_options.append({
            "title": option.get("title") or f"{destination} Route {option_index}",
            "trip": {
                "from": trip.get("from") or start_location,
                "to": trip.get("to") or destination,
                "days": normalized_days,
            },
        })

    return update_option_costs(normalized_options, budget)


def build_fallback_trip_options(start_location, destination, days, budget, activities, error_message):
    destination_point = geocode_location(destination) or {
        "lat": 20.5937,
        "lng": 78.9629,
        "label": destination,
    }
    start_point = geocode_location(start_location) or {
        "lat": max(destination_point["lat"] - 0.18, -90),
        "lng": max(destination_point["lng"] - 0.18, -180),
        "label": start_location,
    }

    destination_name = destination.strip() or "your destination"
    selected_activities = activities or ["nature", "food", "history"]
    activity_text = ", ".join(selected_activity_labels(selected_activities))
    safe_days = max(days, 1)

    def point(lat_offset, lng_offset):
        return {
            "lat": round(destination_point["lat"] + lat_offset, 6),
            "lng": round(destination_point["lng"] + lng_offset, 6),
        }

    def make_day(day_number, theme_name, lat_shift, lng_shift):
        current_activity = selected_activities[(day_number - 1) % len(selected_activities)]
        current_label = ACTIVITY_METADATA.get(current_activity, {}).get("label", current_activity).title()
        base_point = point(lat_shift, lng_shift)
        lunch_point = point(lat_shift + 0.015, lng_shift + 0.012)
        hotel_point = point(lat_shift - 0.012, lng_shift - 0.01)

        plan = []
        if day_number == 1:
            plan.append({
                "type": "travel",
                "title": f"Travel from {start_location} to {destination_name}",
                "lat": start_point["lat"],
                "lng": start_point["lng"],
            })

        plan.extend([
            {
                "type": "place",
                "name": f"{destination_name} {current_label} {theme_name}",
                "description": f"A curated stop in {destination_name} focused on {current_label.lower()} and aligned with {activity_text}.",
                "lat": base_point["lat"],
                "lng": base_point["lng"],
                "duration": "2 hours",
                "rating": 4.2,
                "activity_focus": current_activity,
            },
            {
                "type": "restaurant",
                "name": f"{destination_name} {'Food' if 'food' in selected_activities else 'Local'} Eats",
                "meal": "lunch",
                "lat": lunch_point["lat"],
                "lng": lunch_point["lng"],
                "activity_focus": "food" if "food" in selected_activities else current_activity,
            },
            {
                "type": "hotel",
                "name": f"{destination_name} Stay",
                "lat": hotel_point["lat"],
                "lng": hotel_point["lng"],
                "activity_focus": current_activity,
            },
        ])
        return {"day": day_number, "plan": plan}

    option_blueprints = [
        {
            "title": f"{destination_name} Scenic Explorer",
            "cost": "Rs. 8,000",
            "theme": "Nature Trail",
            "offsets": [(0.02, 0.01), (0.035, -0.012), (0.01, 0.03)],
        },
        {
            "title": f"{destination_name} Culture Circuit",
            "cost": "Rs. 12,000",
            "theme": "Heritage Walk",
            "offsets": [(-0.01, 0.018), (0.012, 0.028), (-0.022, -0.008)],
        },
        {
            "title": f"{destination_name} Balanced Escape",
            "cost": "Rs. 10,500",
            "theme": "City Highlights",
            "offsets": [(0.008, -0.016), (0.024, 0.006), (-0.015, 0.02)],
        },
    ]

    trip_options = []
    for option in option_blueprints:
        day_plans = []
        for day_index in range(safe_days):
            lat_offset, lng_offset = option["offsets"][day_index % len(option["offsets"])]
            day_plans.append(
                make_day(day_index + 1, option["theme"], lat_offset, lng_offset)
            )

        trip_options.append({
            "title": option["title"],
            "trip": {
                "from": start_location,
                "to": destination_name,
                "days": day_plans,
            },
            "fallback_notice": error_message,
        })

    return update_option_costs(trip_options, budget)


def summarize_generation_error(error):
    message = str(error)
    lowered = message.lower()

    if "generative language api has not been used" in lowered or "service_disabled" in lowered:
        return "Gemini API is not enabled for this Google project yet."
    if "api key not valid" in lowered or "permission denied" in lowered:
        return "The Gemini API key is invalid or does not have permission to use Gemini."
    if "gemini_api_key is not configured" in lowered:
        return "Gemini API key is missing from project settings."
    if "no itinerary options" in lowered:
        return "Gemini returned an empty itinerary response."

    return "Live AI trip generation is temporarily unavailable."

# ================= HOME PAGE =================
@login_required
def home(request):
    return render(request, "planner/index.html", {
        "trip": None,
        "show_route": "0"
    })

# ================= AI TRIP MAP =================
@login_required
def trip_map(request):
    trip_data = request.session.get("trip_data")
    if not trip_data:
        return redirect("dashboard")

    return render(request, "planner/trip_map.html", {
        "trip": trip_data
    })


# ================= LOGIN =================
def login_view(request):
    login_type = request.GET.get("type")

    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        login_type = request.POST.get("type")

        user = authenticate(request, username=username, password=password)

        if user is not None:

            # âœ… ADMIN LOGIN
            if login_type == "admin":
                if not user.is_superuser:
                    messages.error(request, "Only admin can login here!")
                    return redirect("login")

                login(request, user)
                return redirect("admin_dashboard")

            # âœ… USER LOGIN
            else:
                if user.is_superuser:
                    messages.error(request, "Please use Admin Login!")
                    return redirect("login")

                login(request, user)
                return redirect("dashboard")

        else:
            messages.error(request, "Invalid credentials")

    return render(request, "login.html", {"login_type": login_type})


# ================= LOGOUT =================
def logout_view(request):
    logout(request)
    return redirect("login")


# ================= REGISTER =================
def register(request):
    if request.method == "POST":
        username = request.POST['username']
        password = request.POST['password']

        if User.objects.filter(username=username).exists():
            messages.error(request, "Username already exists")
            return redirect('register')

        User.objects.create_user(username=username, password=password)

        messages.success(request, "Account created successfully")
        return redirect('login')

    return render(request, "planner/register.html")


# ================= USER DASHBOARD =================
@login_required
def dashboard(request):
    trips = Trip.objects.filter(is_public=True).order_by("-created_at")
    route_histories = RouteHistory.objects.filter(user=request.user)[:6]
    dashboard_trip_data = [
        {
            "destination": trip.destination,
            "title": trip.title,
            "subtitle": trip.subtitle,
            "summary": trip.summary,
            "duration_days": trip.duration_days,
            "price_label": trip.price_label,
        }
        for trip in trips
    ]

    context = {
        "trips": trips,
        "total_trips": trips.count(),
        "hero_trip": trips.first(),
        "featured_trips": trips[:4],
        "dashboard_trip_data": dashboard_trip_data,
        "user_booking_count": Booking.objects.filter(user=request.user).count(),
        "route_histories": route_histories,
    }

    return render(request, "planner/dashboard.html", context)


def split_multiline_values(value):
    return [line.strip() for line in str(value or "").splitlines() if line.strip()]


@login_required
def trip_detail(request, id):
    trip = Trip.objects.get(id=id, is_public=True)

    context = {
        "trip": trip,
        "places_covered": split_multiline_values(trip.places_covered),
        "pricing_points": split_multiline_values(trip.pricing_details),
        "inclusions_list": split_multiline_values(trip.inclusions),
    }
    return render(request, "planner/trip_detail.html", context)


# ================= PLAN TRIP =================
# @login_required
# def plan_trip(request):
#     return  render(request, "plan_trip.html", {
#     "activities": activities,
#     "travel_types": travel_types,
#     "budgets": budgets,
# })
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required


# ================= PLAN TRIP PAGE =================
@login_required
def plan_trip(request):

    # ðŸ”¥ Dynamic options (sent to HTML)
    budgets = [
    ("low", "Low"),
    ("medium", "Medium"),
    ("high", "High"),
]

    activities = [
        ("nature", "Nature"),
    ("adventure", "Adventure"),
    ("food", "Food"),
    ("shopping", "Shopping"),
    ("history", "History"),
    ]

    rating_options = [
        ("3_plus", "3.0+"),
        ("4_plus", "4.0+"),
        ("4_5_plus", "4.5+"),
    ]

    return render(request, "planner/plan_trip.html", {
        "budgets": budgets,
        "activities": activities,
        "rating_options": rating_options,
    })


# ================= GENERATE TRIP =================
@login_required
def generate_trip(request):
    if request.method != "POST":
        return redirect("plan_trip")

    start_location = request.POST.get("start_location")
    destination = request.POST.get("destination")
    try:
        days = int(request.POST.get("days", 2))
    except ValueError:
        days = 2
    budget = request.POST.get("budget", "medium")
    activities = request.POST.getlist("activities")
    rating_preference = request.POST.get("rating_preference", "4_plus")

    rating_label_map = {
        "3_plus": "3.0 or above",
        "4_plus": "4.0 or above",
        "4_5_plus": "4.5 or above",
    }
    rating_value_map = {
        "3_plus": 3.0,
        "4_plus": 4.0,
        "4_5_plus": 4.5,
    }
    rating_label = rating_label_map.get(rating_preference, "4.0 or above")
    minimum_rating = rating_value_map.get(rating_preference, 4.0)
    selected_activity_text = ", ".join(selected_activity_labels(activities))

    generation_warning = None

    prompt = f"""
    You are an expert travel planner. Create 3 DISTINCT {days}-day structured travel itinerary options for a trip from {start_location} to {destination}, India.
    Option 1 must be nature and scenic focused.
    Option 2 must be culture, history, and local-food focused.
    Option 3 must be premium and balanced.
    Budget: {budget}.
    Preferred activities: {selected_activity_text}.
    Minimum expected quality rating: {rating_label}.

    Rules:
    - Use only real places, real restaurants, and real hotels relevant to {destination}.
    - Every option must include all selected activity categories: {selected_activity_text}.
    - The three options must be clearly different from one another.
    - Do not repeat the same place, restaurant, or hotel across the 3 options.
    - Each option must have its own distinct attractions, dining spots, and stay options.
    - Every item must have valid numeric lat/lng coordinates.
    - For each place/restaurant/hotel item, include an "activity_focus" field using one of: nature, adventure, food, shopping, history.
    - Keep each day geographically sensible.
    - Use natural descriptions and real place names only.
    - Return raw JSON only, with no markdown fences.

    Return this exact shape:
    {{
      "options": [
        {{
          "title": "Option title",
          "total_estimated_cost": "Rs. 15,000",
          "trip": {{
            "from": "{start_location}",
            "to": "{destination}",
            "days": [
              {{
                "day": 1,
                "plan": [
                  {{"type": "travel", "title": "Travel from origin", "lat": 12.34, "lng": 56.78}},
                  {{"type": "place", "name": "Real attraction name", "description": "Short description", "activity_focus": "nature", "lat": 12.34, "lng": 56.78, "duration": "2 hours", "rating": 4.5}},
                  {{"type": "restaurant", "name": "Real restaurant name", "meal": "lunch", "activity_focus": "food", "lat": 12.34, "lng": 56.78}},
                  {{"type": "hotel", "name": "Real hotel name", "activity_focus": "history", "lat": 12.34, "lng": 56.78}}
                ]
              }}
            ]
          }}
        }}
      ]
    }}
    """

    try:
        import google.generativeai as genai

        gemini_api_key = getattr(settings, "GEMINI_API_KEY", None)
        if not gemini_api_key:
            raise ValueError("GEMINI_API_KEY is not configured in settings.")

        genai.configure(api_key=gemini_api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")
        trip_options = []
        for attempt in range(2):
            response = model.generate_content(prompt)
            response_text = response.text.strip()

            if response_text.startswith("```json"):
                response_text = response_text[7:-3].strip()
            elif response_text.startswith("```"):
                response_text = response_text[3:-3].strip()

            ai_data = json.loads(response_text)
            trip_options = normalize_trip_options(
                ai_data.get("options", []),
                start_location=start_location,
                destination=destination,
                days=days,
                budget=budget,
                activities=activities,
            )

            for option in trip_options:
                trip_obj = option.get("trip", {}) if isinstance(option.get("trip", {}), dict) else {}
                for day in trip_obj.get("days", []) if isinstance(trip_obj.get("days", []), list) else []:
                    for item in day.get("plan", []) if isinstance(day.get("plan", []), list) else []:
                        if not isinstance(item, dict):
                            continue

                        if "name" in item and "title" not in item:
                            item["title"] = item["name"]
                        elif "title" in item and "name" not in item:
                            item["name"] = item["title"]
                        elif "name" not in item and "title" not in item:
                            item["name"] = "Unknown"
                            item["title"] = "Unknown"

                        if "description" in item and "meal" not in item:
                            item["meal"] = item["description"]
                        elif "meal" in item and "description" not in item:
                            item["description"] = item["meal"]

                        if item.get("type") in {"place", "restaurant", "hotel"}:
                            try:
                                item_rating = float(item.get("rating", minimum_rating))
                            except (TypeError, ValueError):
                                item_rating = minimum_rating
                            item["rating"] = max(item_rating, minimum_rating)

            trip_options = diversify_options_with_real_places(trip_options, destination, minimum_rating)
            trip_options = ensure_distinct_options(trip_options)
            if len(trip_options) >= 3 and not options_have_conflicts(trip_options) and all_options_cover_selected_activities(trip_options, activities):
                break
            if attempt == 0:
                prompt += f"\nIMPORTANT RETRY: Your previous answer either reused places or missed selected categories. Regenerate 3 options with zero repeated places, restaurants, or hotels between the options, and ensure each option clearly covers all of these categories: {selected_activity_text}."

        if len(trip_options) < 3 or options_have_conflicts(trip_options) or not all_options_cover_selected_activities(trip_options, activities):
            raise ValueError("Gemini returned itinerary options that did not fully match the selected categories.")

    except Exception as e:
        print(f"Error generating trip options: {e}")
        generation_warning = summarize_generation_error(e)
        trip_options = build_fallback_trip_options(
            start_location=start_location,
            destination=destination,
            days=days,
            budget=budget,
            activities=activities,
            error_message=generation_warning,
        )

        trip_options = diversify_options_with_real_places(trip_options, destination, minimum_rating)

    request.session["trip_options"] = trip_options
    request.session["trip_dest"] = destination
    request.session["trip_days"] = days
    request.session["trip_budget"] = budget
    request.session["trip_rating_preference"] = rating_preference
    request.session["trip_generation_warning"] = generation_warning

    return redirect("trip_result")
# ================= TRIP RESULT =================
@login_required
def trip_result(request):
    trip_options = request.session.get("trip_options", [])
    destination = request.session.get("trip_dest", "Unknown")
    days = request.session.get("trip_days", 1)
    budget = request.session.get("trip_budget", "medium")
    generation_warning = request.session.get("trip_generation_warning")

    return render(request, "planner/trip_result.html", {
        "trip_options": trip_options,
        "destination": destination,
        "days": days,
        "budget": budget,
        "generation_warning": generation_warning
    })

# ================= SELECT OPTION =================
@login_required
def select_trip_option(request, index):
    import json
    options = request.session.get("trip_options", [])
    if not options or int(index) >= len(options):
        return redirect("dashboard")
        
    selected_option = options[int(index)]
    
    flat_places = []
    
    trip_obj = selected_option.get("trip", {})
    days_arr = trip_obj.get("days", [])
    
    for d in days_arr:
        day_num = d.get("day", 1)
        for p in d.get("plan", []):
            place_info = {
                "name": p.get("name") or p.get("title", "Unknown"),
                "description": p.get("description", p.get("meal", "No description available")),
                "rating": p.get("rating", "N/A"),
                "type": p.get("type", "place"),
                "lat": p.get("lat", 0.0),
                "lng": p.get("lng", 0.0),
                "duration": p.get("duration", "1 hour"),
                "day": day_num,
                "image_url": p.get("image_url"),
            }
            flat_places.append(place_info)
            
    trip_data = {
        "title": selected_option.get("title", "Selected Option"),
        "total_estimated_cost": selected_option.get("total_estimated_cost", "Unknown"),
        "destination": request.session.get("trip_dest", "Unknown"),
        "days": request.session.get("trip_days", 1),
        "budget": request.session.get("trip_budget", "medium"),
        "itinerary": days_arr,
        "places": json.dumps(flat_places) 
    }
    
    request.session["trip_data"] = trip_data

    RouteHistory.objects.create(
        user=request.user,
        route_title=trip_data["title"],
        destination=trip_data["destination"],
        total_estimated_cost=trip_data["total_estimated_cost"],
        days=trip_data["days"],
        budget=trip_data["budget"],
        trip_snapshot={
            "title": trip_data["title"],
            "total_estimated_cost": trip_data["total_estimated_cost"],
            "destination": trip_data["destination"],
            "days": trip_data["days"],
            "budget": trip_data["budget"],
            "itinerary": days_arr,
            "places": flat_places,
        },
    )

    return redirect("/trip-map/")

# ================= ADMIN CHECK DECORATOR =================
def admin_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_superuser:
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper


# ================= ADMIN DASHBOARD =================
@login_required
@admin_required
def admin_dashboard(request):
    users = User.objects.all().order_by("-date_joined", "-id")
    trips = Trip.objects.select_related("created_by").order_by("-created_at")
    bookings = Booking.objects.select_related("trip", "user").all()
    route_histories = RouteHistory.objects.select_related("user").all()

    context = {
        'users': users,
        'trips': trips,
        'bookings': bookings,
        'route_histories': route_histories,
        'total_users': users.count(),
        'total_trips': trips.count(),
        'total_bookings': bookings.count(),
        'total_route_histories': route_histories.count(),
    }

    return render(request, 'planner/admin_dashboard.html', context)


@login_required
def book_trip(request, id):
    trip = Trip.objects.get(id=id, is_public=True)

    if request.method == "POST":
        traveler_name = request.POST.get("traveler_name") or request.user.get_full_name() or request.user.username
        traveler_email = request.POST.get("traveler_email") or request.user.email
        traveler_phone = request.POST.get("traveler_phone", "")
        travelers_count = request.POST.get("travelers_count") or 1
        special_request = request.POST.get("special_request", "")
        Booking.objects.create(
            trip=trip,
            user=request.user,
            traveler_name=traveler_name,
            traveler_email=traveler_email,
            traveler_phone=traveler_phone,
            travelers_count=travelers_count,
            special_request=special_request,
        )

        messages.success(request, f"Your booking for {trip.destination} has been saved.")
        return redirect("dashboard")

    return render(request, "planner/book_trip.html", {
        "trip": trip,
        "prefill_name": request.user.get_full_name() or request.user.username,
        "prefill_email": request.user.email,
    })


@login_required
def open_route_history(request, id):
    history = RouteHistory.objects.get(id=id, user=request.user)
    snapshot = history.trip_snapshot or {}
    request.session["trip_data"] = {
        "title": snapshot.get("title", history.route_title),
        "total_estimated_cost": snapshot.get("total_estimated_cost", history.total_estimated_cost),
        "destination": snapshot.get("destination", history.destination),
        "days": snapshot.get("days", history.days),
        "budget": snapshot.get("budget", history.budget),
        "itinerary": snapshot.get("itinerary", []),
        "places": json.dumps(snapshot.get("places", [])),
    }
    return redirect("trip_map")


@login_required
@admin_required
def edit_route_history(request, id):
    history = RouteHistory.objects.get(id=id)

    if request.method == "POST":
        history.route_title = request.POST.get("route_title", history.route_title)
        history.destination = request.POST.get("destination", history.destination)
        history.total_estimated_cost = request.POST.get("total_estimated_cost", history.total_estimated_cost)
        history.days = request.POST.get("days") or history.days
        history.budget = request.POST.get("budget", history.budget)
        history.admin_notes = request.POST.get("admin_notes", "")
        history.save()
        messages.success(request, "Route history updated successfully.")
        return redirect("admin_dashboard")

    return render(request, "planner/edit_route_history.html", {"history": history})


@login_required
@admin_required
def delete_route_history(request, id):
    history = RouteHistory.objects.get(id=id)
    if request.method == "POST":
        history.delete()
        messages.success(request, "Route history deleted successfully.")
    return redirect("admin_dashboard")


# ================= ADD TRIP =================
@login_required
@admin_required
def add_trip(request):
    if request.method == "POST":
        title = request.POST['title']
        destination = request.POST['destination']
        subtitle = request.POST.get("subtitle", "")
        summary = request.POST.get("summary", "")
        places_covered = request.POST.get("places_covered", "")
        pricing_details = request.POST.get("pricing_details", "")
        review_summary = request.POST.get("review_summary", "")
        review_rating = request.POST.get("review_rating") or None
        inclusions = request.POST.get("inclusions", "")
        image_file = request.FILES.get("image_file")
        duration_days = request.POST.get("duration_days") or 3
        price_label = request.POST.get("price_label", "")
        trip_style = request.POST.get("trip_style", "")
        is_public = request.POST.get("is_public") == "on"

        Trip.objects.create(
            title=title,
            destination=destination,
            subtitle=subtitle,
            summary=summary,
            places_covered=places_covered,
            pricing_details=pricing_details,
            review_summary=review_summary,
            review_rating=review_rating,
            inclusions=inclusions,
            image_url="",
            image_file=image_file,
            duration_days=duration_days,
            price_label=price_label,
            trip_style=trip_style,
            created_by=request.user,
            is_public=is_public
        )

        messages.success(request, "Trip created successfully.")

        return redirect('admin_dashboard')

    return render(request, 'planner/add_trip.html')


# ================= EDIT TRIP =================
@login_required
@admin_required
def edit_trip(request, id):
    trip = Trip.objects.get(id=id)

    if request.method == "POST":
        trip.title = request.POST['title']
        trip.destination = request.POST['destination']
        trip.subtitle = request.POST.get("subtitle", "")
        trip.summary = request.POST.get("summary", "")
        trip.places_covered = request.POST.get("places_covered", "")
        trip.pricing_details = request.POST.get("pricing_details", "")
        trip.review_summary = request.POST.get("review_summary", "")
        trip.review_rating = request.POST.get("review_rating") or None
        trip.inclusions = request.POST.get("inclusions", "")
        trip.image_url = ""
        if request.POST.get("remove_image_file") == "on":
            trip.image_file = ""
        elif request.FILES.get("image_file"):
            trip.image_file = request.FILES.get("image_file")
        trip.duration_days = request.POST.get("duration_days") or 3
        trip.price_label = request.POST.get("price_label", "")
        trip.trip_style = request.POST.get("trip_style", "")
        trip.is_public = request.POST.get("is_public") == "on"
        trip.save()

        messages.success(request, "Trip updated successfully.")

        return redirect('admin_dashboard')

    return render(request, 'planner/edit_trip.html', {'trip': trip})


# ================= DELETE TRIP =================
@login_required
@admin_required
def delete_trip(request, id):
    trip = Trip.objects.get(id=id)
    if request.method == "POST":
        trip.delete()
        messages.success(request, "Trip deleted successfully.")
    return redirect('admin_dashboard')


# ================= BOOKING CRUD =================
@login_required
@admin_required
def add_booking(request):
    users = User.objects.order_by("username")
    trips = Trip.objects.order_by("destination", "title")

    if request.method == "POST":
        user_id = request.POST.get("user")
        trip_id = request.POST.get("trip")
        traveler_name = request.POST.get("traveler_name", "").strip()
        traveler_email = request.POST.get("traveler_email", "").strip()
        traveler_phone = request.POST.get("traveler_phone", "").strip()
        travelers_count = request.POST.get("travelers_count") or 1
        special_request = request.POST.get("special_request", "").strip()

        if not user_id or not trip_id or not traveler_name or not traveler_email:
            messages.error(request, "User, trip, traveler name, and traveler email are required.")
        else:
            Booking.objects.create(
                user=User.objects.get(id=user_id),
                trip=Trip.objects.get(id=trip_id),
                traveler_name=traveler_name,
                traveler_email=traveler_email,
                traveler_phone=traveler_phone,
                travelers_count=travelers_count,
                special_request=special_request,
            )
            messages.success(request, "Booking created successfully.")
            return redirect("admin_dashboard")

    return render(request, "planner/add_booking.html", {
        "users": users,
        "trips": trips,
    })


@login_required
@admin_required
def edit_booking(request, id):
    booking = Booking.objects.get(id=id)
    users = User.objects.order_by("username")
    trips = Trip.objects.order_by("destination", "title")

    if request.method == "POST":
        user_id = request.POST.get("user")
        trip_id = request.POST.get("trip")
        booking.user = User.objects.get(id=user_id) if user_id else booking.user
        booking.trip = Trip.objects.get(id=trip_id) if trip_id else booking.trip
        booking.traveler_name = request.POST.get("traveler_name", booking.traveler_name).strip()
        booking.traveler_email = request.POST.get("traveler_email", booking.traveler_email).strip()
        booking.traveler_phone = request.POST.get("traveler_phone", "").strip()
        booking.travelers_count = request.POST.get("travelers_count") or booking.travelers_count
        booking.special_request = request.POST.get("special_request", "").strip()
        booking.save()
        messages.success(request, "Booking updated successfully.")
        return redirect("admin_dashboard")

    return render(request, "planner/edit_booking.html", {
        "booking": booking,
        "users": users,
        "trips": trips,
    })


@login_required
@admin_required
def delete_booking(request, id):
    booking = Booking.objects.get(id=id)
    if request.method == "POST":
        booking.delete()
        messages.success(request, "Booking deleted successfully.")
    return redirect("admin_dashboard")


# ================= ADD USER =================
@login_required
@admin_required
def add_user(request):
    if request.method == "POST":
        username = request.POST["username"]
        email = request.POST.get("email", "")
        password = request.POST["password"]
        is_staff = request.POST.get("is_staff") == "on"

        if User.objects.filter(username=username).exists():
            messages.error(request, "Username already exists.")
            return redirect("add_user")

        user = User.objects.create_user(username=username, email=email, password=password)
        user.is_staff = is_staff
        user.is_superuser = is_staff
        user.save()
        messages.success(request, "User created successfully.")
        return redirect("admin_dashboard")

    return render(request, "planner/add_user.html")


# ================= EDIT USER =================
@login_required
@admin_required
def edit_user(request, id):
    managed_user = User.objects.get(id=id)

    if request.method == "POST":
        managed_user.username = request.POST["username"]
        managed_user.email = request.POST.get("email", "")
        managed_user.is_staff = request.POST.get("is_staff") == "on"
        managed_user.is_superuser = managed_user.is_staff
        new_password = request.POST.get("password")
        if new_password:
            managed_user.set_password(new_password)
        managed_user.save()
        messages.success(request, "User updated successfully.")
        return redirect("admin_dashboard")

    return render(request, "planner/edit_user.html", {"managed_user": managed_user})


# ================= DELETE USER =================
@login_required
@admin_required
def delete_user(request, id):
    managed_user = User.objects.get(id=id)
    if request.method == "POST" and managed_user != request.user:
        managed_user.delete()
        messages.success(request, "User deleted successfully.")
    elif managed_user == request.user:
        messages.error(request, "You cannot delete your own admin account.")
    return redirect("admin_dashboard")


# @login_required
# def view_map(request):
#     trip_data = request.session.get("trip_data")

#     return render(request, "planner/map.html", {
#         "trip": trip_data
#     })

def get_places(query):
    url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    
    params = {
        "query": query,
        "key": settings.GOOGLE_API_KEY
    }

    response = requests.get(url, params=params)
    data = response.json()

    results = []
    for place in data.get("results", [])[:5]:
        results.append({
            "name": place["name"],
            "address": place.get("formatted_address"),
            "rating": place.get("rating"),
            "location": place["geometry"]["location"]
        })

    return results

def get_places(query):
    url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    
    params = {
        "query": query,
        "key": settings.GOOGLE_API_KEY
    }

    response = requests.get(url, params=params)
    data = response.json()

    results = []
    for place in data.get("results", [])[:5]:
        results.append({
            "name": place["name"],
            "address": place.get("formatted_address"),
            "rating": place.get("rating"),
        })

    return results

