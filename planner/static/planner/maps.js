console.log("MAPS JS LOADED");

var map = L.map("map", {
    zoomControl: false,
    attributionControl: false
}).setView([18.5204, 73.8567], 15);

var streetTile = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png");
var satelliteTile = L.tileLayer("https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}");

var currentTile = satelliteTile;
currentTile.addTo(map);

var userLat = 18.5204;
var userLon = 73.8567;
var mapMarkers = [];
var tripPlaces = [];
var allTripPlaces = [];
var routeControl = null;
var userLocationResolved = false;
var userMarker = null;
var selectedAiDay = null;
var activeRoutePopup = null;
var currentExploreRadiusKm = 5;
var activeCategoryRequest = null;

function setMapStyle(style, clickedBtn) {
    map.removeLayer(currentTile);
    currentTile = style === "satellite" ? satelliteTile : streetTile;
    currentTile.addTo(map);

    document.querySelectorAll(".mapBtn").forEach(function (btn) {
        btn.classList.remove("bg-map-ocean", "text-white");
        btn.classList.add("bg-transparent", "text-slate-400");
    });

    if (clickedBtn) {
        clickedBtn.classList.remove("bg-transparent", "text-slate-400");
        clickedBtn.classList.add("bg-map-ocean", "text-white");
    }
}

function makePopupCard(title, bodyHtml, imageUrl) {
    return `
        <div style="width:220px;padding:12px;color:#f8f5ff;font-family:Manrope,sans-serif;">
            ${imageUrl ? `<img src="${imageUrl}" alt="${title}" style="width:100%;height:126px;object-fit:cover;border-radius:14px;margin-bottom:12px;">` : ""}
            <h3 style="font-size:16px;font-weight:800;line-height:1.35;">${title}</h3>
            <div style="margin-top:8px;font-size:12px;line-height:1.55;color:#cbd5e1;">${bodyHtml}</div>
        </div>
    `;
}

function locateUser(centerMap) {
    if (typeof centerMap === "undefined") {
        centerMap = true;
    }

    navigator.geolocation.getCurrentPosition(function (position) {
        userLat = position.coords.latitude;
        userLon = position.coords.longitude;
        userLocationResolved = true;

        if (centerMap) {
            map.setView([userLat, userLon], 15);
        }

        var userIcon = L.divIcon({
            className: "",
            html: '<div style="width:16px;height:16px;background:#60a5fa;border:3px solid #ffffff;border-radius:50%;box-shadow:0 0 0 4px rgba(96,165,250,0.3);"></div>',
            iconSize: [16, 16],
            iconAnchor: [8, 8]
        });

        if (userMarker) {
            map.removeLayer(userMarker);
        }

        userMarker = L.marker([userLat, userLon], { icon: userIcon })
            .addTo(map);
        userMarker.bindPopup('<div style="padding:12px 14px;font-family:Manrope,sans-serif;color:#f8f5ff;"><b>Location detected</b></div>');

        fetch("https://nominatim.openstreetmap.org/reverse?format=json&lat=" + userLat + "&lon=" + userLon)
            .then(function (res) { return res.json(); })
            .then(function (data) {
                var city = data.address.city || data.address.town || data.address.village || "Your Location";
                var locText = document.getElementById("locationText");
                var locBadge = document.getElementById("locationBadge");

                if (locText) locText.textContent = city;
                if (locBadge) locBadge.classList.remove("hidden");
            });

        if (typeof loadDefaultMarkers === "function") {
            loadDefaultMarkers(userLat, userLon);
        }
    });
}

locateUser(typeof showRoute === "undefined" || showRoute !== "1");

function getDistance(lat1, lon1, lat2, lon2) {
    var earthRadius = 6371;
    var dLat = (lat2 - lat1) * Math.PI / 180;
    var dLon = (lon2 - lon1) * Math.PI / 180;
    var a =
        Math.sin(dLat / 2) * Math.sin(dLat / 2) +
        Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
        Math.sin(dLon / 2) * Math.sin(dLon / 2);
    return earthRadius * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function loadPlaceImage(placeName, lat, lng, popupId) {
    if (typeof google === "undefined" || !google.maps || !google.maps.places) return;

    var service = new google.maps.places.PlacesService(document.createElement("div"));
    var request = {
        query: placeName,
        fields: ["name", "photos"],
        locationBias: new google.maps.LatLng(lat, lng)
    };

    service.findPlaceFromQuery(request, function (results, status) {
        if (status === google.maps.places.PlacesServiceStatus.OK && results && results.length > 0 && results[0].photos) {
            var photoUrl = results[0].photos[0].getUrl({ maxWidth: 400, maxHeight: 250 });
            var imgEl = document.getElementById(popupId);
            if (imgEl) {
                imgEl.src = photoUrl;
                imgEl.style.display = "block";
            }
        }
    });
}

function zoomToLocation(lat, lng, name) {
    if (typeof map === "undefined") return;
    map.flyTo([lat, lng], 15, { animate: true, duration: 1.5 });

    mapMarkers.forEach(function (marker) {
        var latLng = marker.getLatLng();
        if (Math.abs(latLng.lat - lat) < 0.0001 && Math.abs(latLng.lng - lng) < 0.0001) {
            marker.openPopup();
        }
    });
}

function clearRouteStats() {
    var distEl = document.getElementById("routeDist");
    var timeEl = document.getElementById("routeTime");
    var cardEl = document.getElementById("routeCard");
    if (distEl) distEl.textContent = "...";
    if (timeEl) timeEl.textContent = "...";
    if (cardEl) cardEl.classList.add("hidden");
}

function showToast(message) {
    var toast = document.getElementById("toast");
    var msg = document.getElementById("toastMsg");

    if (!toast || !msg) return;

    msg.textContent = message;
    toast.classList.remove("hidden");

    setTimeout(function () {
        toast.classList.add("hidden");
    }, 2500);
}

function clearMapMarkers() {
    mapMarkers.forEach(function (marker) {
        map.removeLayer(marker);
    });
    mapMarkers = [];
}

function resetCategoryResults() {
    var section = document.getElementById("placesSection");
    var list = document.getElementById("placesList");
    var countEl = document.getElementById("placeCount");

    clearExistingRoute();
    clearMapMarkers();

    if (list) {
        list.innerHTML = "";
    }

    if (countEl) {
        countEl.textContent = "0";
    }

    if (section) {
        section.classList.add("hidden");
    }

    document.querySelectorAll(".catBtn").forEach(function (btn) {
        btn.classList.remove("border-map-forest", "bg-map-fog");
        btn.classList.add("border-white/10", "bg-white/5", "text-white");
    });
}

function getExploreRadiusMeters() {
    return currentExploreRadiusKm * 1000;
}

function updateRadiusLabel() {
    var label = document.getElementById("radiusValue");
    if (label) {
        label.textContent = currentExploreRadiusKm + " km";
    }
}

function reloadActiveCategory() {
    if (!activeCategoryRequest) {
        return;
    }

    loadCategory(
        activeCategoryRequest.type,
        activeCategoryRequest.value,
        activeCategoryRequest.button,
        true
    );
}

function setCategoryButtonState(clickedBtn) {
    document.querySelectorAll(".catBtn").forEach(function (btn) {
        btn.classList.remove("border-map-forest", "bg-map-fog");
        btn.classList.add("border-white/10", "bg-white/5", "text-white");
    });

    if (clickedBtn) {
        clickedBtn.classList.add("border-map-forest", "bg-map-fog", "text-white");
        clickedBtn.classList.remove("border-white/10", "bg-white/5");
    }
}

function createPlaceSidebarCard(place, lat, lon, dist, photo, marker) {
    var card = document.createElement("div");
    card.className = "group cursor-pointer overflow-hidden rounded-3xl border border-white/10 bg-white/5 shadow-[0_18px_50px_rgba(5,2,16,0.22)] backdrop-blur-xl transition-all hover:border-[#c4b5fd]/30 hover:bg-white/8";

    card.innerHTML = `
        ${photo ? `<div class="h-32 w-full overflow-hidden"><img src="${photo}" class="h-full w-full object-cover transition-transform duration-500 group-hover:scale-105"></div>` : ""}
        <div class="relative p-3.5">
            <p class="text-[14px] font-bold leading-snug text-white">${place.name}</p>
            <div class="mt-2 flex items-center gap-3 text-[11px] font-bold text-slate-400">
                <span class="rounded border border-[#c4b5fd]/15 bg-[#7c5cff]/12 px-1.5 py-0.5 text-[#d8ccff]">Rating ${place.rating || "N/A"}</span>
                <span>${dist} km</span>
            </div>
            <div class="mt-4 grid grid-cols-2 gap-2">
                <button class="rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-xs font-semibold text-slate-100 transition hover:border-[#c4b5fd]/30 hover:bg-white/10" onclick="event.stopPropagation(); buildRouteFromCurrentLocation('${place.name.replace(/'/g, "")}',${lat},${lon})">
                    Route from me
                </button>
                <button class="rounded-xl border border-white/10 bg-[#7c5cff]/18 px-3 py-2 text-xs font-semibold text-[#e9ddff] transition hover:bg-[#7c5cff] hover:text-white" onclick="event.stopPropagation(); addToTrip('${place.name.replace(/'/g, "")}',${lat},${lon})">
                    Add to trip
                </button>
            </div>
        </div>
    `;

    card.onclick = function () {
        map.setView([lat, lon], 16);
        marker.openPopup();
    };

    return card;
}

function clearExistingRoute() {
    if (routeControl) {
        map.removeControl(routeControl);
        routeControl = null;
    }

    if (window.fallbackRouteLine) {
        map.removeLayer(window.fallbackRouteLine);
        window.fallbackRouteLine = null;
    }
    if (activeRoutePopup) {
        map.removeLayer(activeRoutePopup);
        activeRoutePopup = null;
    }
    clearRouteStats();
}

function renderRouteForPlaces(places, successMessage) {
    if (!places || places.length < 2) {
        alert("Add at least 2 places");
        return;
    }

    if (typeof L.Routing === "undefined") {
        alert("Routing library not loaded");
        return;
    }

    clearExistingRoute();

    var waypoints = places.map(function (place) {
        return L.latLng(parseFloat(place.lat), parseFloat(place.lon));
    });

    window.fallbackRouteLine = L.polyline(
        places.map(function (place) { return [parseFloat(place.lat), parseFloat(place.lon)]; }),
        {
            color: "#a78bfa",
            weight: 4,
            dashArray: "8, 12",
            opacity: 0.75
        }
    ).addTo(map);

    try {
        routeControl = L.Routing.control({
            waypoints: waypoints,
            router: L.Routing.osrmv1({
                serviceUrl: "https://router.project-osrm.org/route/v1",
                profile: "driving"
            }),
            routeWhileDragging: false,
            addWaypoints: false,
            draggableWaypoints: false,
            fitSelectedRoutes: true,
            show: false,
            lineOptions: {
                styles: [{ color: "#7c5cff", weight: 6, opacity: 0.95 }]
            },
            createMarker: function () { return null; }
        });

        routeControl.addTo(map);

        routeControl.on("routesfound", function (e) {
            var route = e.routes[0];
            var km = (route.summary.totalDistance / 1000).toFixed(1);
            var minutes = Math.round(route.summary.totalTime / 60);
            var timeStr = minutes >= 60
                ? Math.floor(minutes / 60) + "h " + (minutes % 60) + "m"
                : minutes + " min";

            var distEl = document.getElementById("routeDist");
            var timeEl = document.getElementById("routeTime");
            var cardEl = document.getElementById("routeCard");

            if (distEl) distEl.textContent = km + " km";
            if (timeEl) timeEl.textContent = timeStr;
            if (cardEl) cardEl.classList.remove("hidden");

            var center = route.coordinates[Math.floor(route.coordinates.length / 2)];
            activeRoutePopup = L.popup({
                closeButton: false,
                autoClose: false,
                className: "route-popup"
            })
                .setLatLng([center.lat, center.lng])
                .setContent(`<div style="padding:8px 12px;font-size:13px;color:#f8f5ff;"><b>${km} km</b><br>${timeStr}</div>`);
            activeRoutePopup.openOn(map);

            if (window.fallbackRouteLine) {
                map.removeLayer(window.fallbackRouteLine);
                window.fallbackRouteLine = null;
            }

        });

        routeControl.on("routingerror", function (e) {
            console.error("OSRM routing failed:", e.error);
            showToast("Showing an approximate route");
        });
    } catch (err) {
        console.error("FULL ERROR:", err);
        alert("Check console (F12)");
    }
}

function buildRouteFromCurrentLocation(destinationName, lat, lon) {
    if (!userLocationResolved) {
        alert("Current location is still loading. Please click 'Locate me' and try again.");
        return;
    }

    var directRoutePlaces = [
        { name: "My Location", lat: userLat, lon: userLon },
        { name: destinationName, lat: lat, lon: lon }
    ];

    renderRouteForPlaces(directRoutePlaces, "Route from your location is ready");
}

function getAiDayPlaces(dayNumber) {
    return allTripPlaces.filter(function (place) {
        if (String(place.day) !== String(dayNumber)) {
            return false;
        }
        if (dayNumber > 1 && place.type === "travel") {
            return false;
        }
        return true;
    });
}

function updateAiDayButtons(dayNumber) {
    document.querySelectorAll("[data-day-button]").forEach(function (button) {
        var isActive = String(button.getAttribute("data-day-button")) === String(dayNumber);
        button.classList.toggle("border-[#c4b5fd]/30", isActive);
        button.classList.toggle("bg-[#7c5cff]/20", isActive);
        button.classList.toggle("text-white", isActive);
        button.classList.toggle("bg-white/5", !isActive);
        button.classList.toggle("text-slate-200", !isActive);
    });

    document.querySelectorAll("[data-day-section]").forEach(function (section) {
        var isActive = String(section.getAttribute("data-day-section")) === String(dayNumber);
        section.classList.toggle("hidden", !isActive);
    });
}

function updateAiDayMarkers(dayNumber) {
    mapMarkers.forEach(function (marker) {
        var belongsToDay = String(marker._tripDay || "") === String(dayNumber);
        if (belongsToDay) {
            if (!map.hasLayer(marker)) {
                marker.addTo(map);
            }
        } else if (map.hasLayer(marker)) {
            map.removeLayer(marker);
        }
    });

    if (userMarker && !map.hasLayer(userMarker)) {
        userMarker.addTo(map);
    }
}

function setAiDay(dayNumber) {
    if (typeof showRoute === "undefined" || showRoute !== "1") {
        return;
    }

    selectedAiDay = Number(dayNumber);
    updateAiDayButtons(selectedAiDay);
    updateAiDayMarkers(selectedAiDay);

    tripPlaces = getAiDayPlaces(selectedAiDay);

    if (tripPlaces.length >= 2) {
        renderRouteForPlaces(tripPlaces, "Day " + selectedAiDay + " route ready");
    } else if (tripPlaces.length === 1) {
        clearExistingRoute();
        map.setView([tripPlaces[0].lat, tripPlaces[0].lon], 14);
        showToast("Showing Day " + selectedAiDay + " stop");
    } else {
        clearExistingRoute();
    }
}

function loadCategory(type, value, clickedBtn, isReload) {
    if (!userLat || !userLon) {
        alert("Location not loaded yet. Please click 'Locate me' first.");
        return;
    }

    if (!isReload && activeCategoryRequest && activeCategoryRequest.type === type && activeCategoryRequest.value === value) {
        activeCategoryRequest = null;
        resetCategoryResults();
        return;
    }

    if (!isReload) {
        activeCategoryRequest = {
            type: type,
            value: value,
            button: clickedBtn || null
        };
    }

    setCategoryButtonState(clickedBtn || (activeCategoryRequest && activeCategoryRequest.button));

    var section = document.getElementById("placesSection");
    var list = document.getElementById("placesList");

    if (section) section.classList.remove("hidden");
    if (list) list.innerHTML = "";

    clearMapMarkers();

    var service = new google.maps.places.PlacesService(document.createElement("div"));
    var request = {
        location: new google.maps.LatLng(userLat, userLon),
        radius: getExploreRadiusMeters(),
        keyword: value
    };

    if (type === "type") {
        request.type = value;
    }

    service.nearbySearch(request, function (results, status) {
        if (status !== google.maps.places.PlacesServiceStatus.OK) return;

        var countEl = document.getElementById("placeCount");
        if (countEl) countEl.textContent = results.length + " places";

        results.slice(0, 10).forEach(function (place) {
            var lat = place.geometry.location.lat();
            var lon = place.geometry.location.lng();
            var photo = place.photos ? place.photos[0].getUrl({ maxWidth: 400 }) : "";
            var dist = getDistance(userLat, userLon, lat, lon).toFixed(2);

            var marker = L.marker([lat, lon]).addTo(map);
            marker.bindPopup(makePopupCard(
                place.name,
                `Rating: ${place.rating || "N/A"}<br>Distance: ${dist} km away<br><button style="margin-top:12px;width:100%;border:none;border-radius:14px;background:rgba(255,255,255,0.06);padding:11px 14px;color:#f8f5ff;font-weight:700;cursor:pointer;" onclick="buildRouteFromCurrentLocation('${place.name.replace(/'/g, "")}',${lat},${lon})">Route from my location</button><button style="margin-top:8px;width:100%;border:none;border-radius:14px;background:linear-gradient(135deg,#7c5cff,#a855f7);padding:11px 14px;color:#fff;font-weight:700;cursor:pointer;" onclick="addToTrip('${place.name.replace(/'/g, "")}',${lat},${lon})">Add to Trip</button>`,
                photo
            ));
            marker.on("mouseover", function () {
                this.openPopup();
            });

            mapMarkers.push(marker);

            if (list) {
                list.appendChild(createPlaceSidebarCard(place, lat, lon, dist, photo, marker));
            }
        });

        if (mapMarkers.length) {
            var group = new L.featureGroup(mapMarkers);
            map.fitBounds(group.getBounds());
        }

        currentTile.addTo(map);
        map.invalidateSize();
        setTimeout(function () {
            map.invalidateSize();
        }, 200);
    });
}

function searchLocation() {
    var keyword = document.getElementById("searchInput").value;
    if (!keyword) return;

    clearMapMarkers();

    var service = new google.maps.places.PlacesService(document.createElement("div"));
    var request = {
        query: keyword,
        location: new google.maps.LatLng(userLat, userLon),
        radius: 50000
    };

    service.textSearch(request, function (results, status) {
        if (status !== google.maps.places.PlacesServiceStatus.OK || !results.length) {
            alert("No results found for: " + keyword);
            return;
        }

        results.forEach(function (place) {
            var lat = place.geometry.location.lat();
            var lng = place.geometry.location.lng();
            var marker = L.marker([lat, lng]).addTo(map);

            marker.bindPopup(makePopupCard(
                place.name,
                `Rating: ${place.rating || "N/A"}<br><button style="margin-top:12px;width:100%;border:none;border-radius:14px;background:rgba(255,255,255,0.06);padding:11px 14px;color:#f8f5ff;font-weight:700;cursor:pointer;" onclick="buildRouteFromCurrentLocation('${place.name.replace(/'/g, "")}',${lat},${lng})">Route from my location</button><button style="margin-top:8px;width:100%;border:none;border-radius:14px;background:linear-gradient(135deg,#7c5cff,#a855f7);padding:11px 14px;color:#fff;font-weight:700;cursor:pointer;" onclick="addToTrip('${place.name.replace(/'/g, "")}',${lat},${lng})">Add to Trip</button>`
            ));

            mapMarkers.push(marker);
        });

        map.setView([
            results[0].geometry.location.lat(),
            results[0].geometry.location.lng()
        ], 12);
    });
}

document.getElementById("searchInput").addEventListener("keydown", function (e) {
    if (e.key === "Enter") searchLocation();
});

function addToTrip(name, lat, lon) {
    var alreadyExists = tripPlaces.some(function (place) { return place.name === name; });
    if (alreadyExists) {
        showToast(name + " is already in your trip");
        return;
    }

    tripPlaces.push({ name: name, lat: lat, lon: lon });
    showToast("Added " + name + " to trip");
    updateTripList();

    var btn = document.getElementById("addbtn-" + encodeURIComponent(name));
    if (btn) {
        btn.textContent = "Added";
        btn.classList.remove("border-map-forest", "text-map-moss", "hover:bg-map-forest", "hover:text-white");
        btn.classList.add("border-emerald-500", "text-emerald-400", "pointer-events-none");
    }
}

function removeFromTrip(name) {
    tripPlaces = tripPlaces.filter(function (place) { return place.name !== name; });
    updateTripList();

    if (routeControl) {
        map.removeControl(routeControl);
        routeControl = null;
    }

    var routeCard = document.getElementById("routeCard");
    if (routeCard) routeCard.classList.add("hidden");

    var btn = document.getElementById("addbtn-" + encodeURIComponent(name));
    if (btn) {
        btn.textContent = "+ Add";
        btn.classList.remove("border-emerald-500", "text-emerald-400", "pointer-events-none");
        btn.classList.add("border-map-forest", "text-map-moss", "hover:bg-map-forest", "hover:text-white");
    }
}

function updateTripList() {
    var list = document.getElementById("tripList");
    var emptyMsg = document.getElementById("tripEmpty");
    var routeBtn = document.getElementById("routeBtn");
    var countBadge = document.getElementById("tripCount");

    if (!list || !emptyMsg || !routeBtn || !countBadge) return;

    list.innerHTML = "";
    countBadge.textContent = tripPlaces.length + (tripPlaces.length === 1 ? " stop" : " stops");

    if (tripPlaces.length === 0) {
        emptyMsg.classList.remove("hidden");
        routeBtn.classList.add("hidden");
        routeBtn.classList.remove("flex");
        return;
    }

    emptyMsg.classList.add("hidden");

    tripPlaces.forEach(function (place, index) {
        var item = document.createElement("div");
        item.className = "group flex items-center gap-3 rounded-2xl border border-white/10 bg-white/5 px-3 py-3 shadow-[0_10px_24px_rgba(5,2,16,0.18)] backdrop-blur-xl transition-colors hover:border-[#c4b5fd]/30 hover:bg-white/8";

        item.innerHTML =
            '<div class="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full bg-[linear-gradient(135deg,#7c5cff,#a855f7)] text-[12px] font-black text-white">' +
            (index + 1) +
            "</div>" +
            '<span class="flex-1 truncate text-[13px] font-bold text-slate-100 transition-colors group-hover:text-white">' + place.name + "</span>" +
            '<button onclick="removeFromTrip(\'' + place.name.replace(/'/g, "\\'") + '\')" class="flex h-7 w-7 cursor-pointer items-center justify-center rounded-full border border-white/10 bg-red-500/10 text-red-400 transition-colors hover:bg-red-500 hover:text-white">' +
            '<svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5">' +
            '<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12"/>' +
            "</svg>" +
            "</button>";

        list.appendChild(item);
    });

    if (tripPlaces.length >= 2) {
        routeBtn.classList.remove("hidden");
        routeBtn.classList.add("flex");
    } else {
        routeBtn.classList.add("hidden");
        routeBtn.classList.remove("flex");
    }
}

function optimizeRoute(points) {
    if (points.length <= 2) return points;

    var optimized = [];
    var remaining = points.slice();
    var current = remaining.shift();
    optimized.push(current);

    while (remaining.length > 0) {
        var nearestIndex = 0;
        var minDist = Infinity;

        for (var i = 0; i < remaining.length; i++) {
            var dist = getDistance(current.lat, current.lon, remaining[i].lat, remaining[i].lon);
            if (dist < minDist) {
                minDist = dist;
                nearestIndex = i;
            }
        }

        current = remaining.splice(nearestIndex, 1)[0];
        optimized.push(current);
    }

    return optimized;
}

function drawRoute() {
    if (!tripPlaces || tripPlaces.length < 2) {
        alert("Add at least 2 places");
        return;
    }

    var isAiTripMode = typeof showRoute !== "undefined" && showRoute === "1";
    var optimizedPlaces = isAiTripMode ? tripPlaces : optimizeRoute(tripPlaces);

    tripPlaces = optimizedPlaces;
    updateTripList();
    renderRouteForPlaces(optimizedPlaces, "Route generated successfully");
}

document.addEventListener("DOMContentLoaded", function () {
    var input = document.getElementById("searchInput");
    var box = document.getElementById("suggestions");
    var searchBtn = document.getElementById("searchBtn");
    var radiusSlider = document.getElementById("radiusSlider");

    if (!input || !box || typeof google === "undefined" || !google.maps || !google.maps.places) return;

    updateRadiusLabel();

    if (radiusSlider) {
        radiusSlider.addEventListener("input", function () {
            currentExploreRadiusKm = Number(radiusSlider.value || 5);
            updateRadiusLabel();
        });

        radiusSlider.addEventListener("change", function () {
            currentExploreRadiusKm = Number(radiusSlider.value || 5);
            updateRadiusLabel();
            reloadActiveCategory();
        });
    }

    var autocompleteService = new google.maps.places.AutocompleteService();

    input.addEventListener("input", function () {
        var query = input.value;

        if (!query) {
            box.classList.add("hidden");
            return;
        }

        autocompleteService.getPlacePredictions({ input: query }, function (predictions, status) {
            box.innerHTML = "";

            if (status !== google.maps.places.PlacesServiceStatus.OK) {
                box.classList.add("hidden");
                return;
            }

            predictions.forEach(function (prediction) {
                var div = document.createElement("div");
                div.className = "cursor-pointer px-4 py-3 text-sm text-slate-100 transition hover:bg-white/8";
                div.textContent = prediction.description;
                div.onclick = function () {
                    input.value = prediction.description;
                    box.classList.add("hidden");
                    searchLocation();
                };
                box.appendChild(div);
            });

            box.classList.remove("hidden");
        });
    });

    if (searchBtn) {
        searchBtn.addEventListener("click", function () {
            box.classList.add("hidden");
            box.innerHTML = "";
            searchLocation();
        });
    }

    document.addEventListener("click", function (e) {
        if (!input.contains(e.target) && !box.contains(e.target)) {
            box.classList.add("hidden");
        }
    });
});

window.addEventListener("load", function () {
    if (typeof tripPlacesFromBackend === "undefined" || !tripPlacesFromBackend || tripPlacesFromBackend.length === 0) {
        return;
    }

    tripPlaces = [];
    allTripPlaces = [];

    tripPlacesFromBackend.forEach(function (place) {
        var tripPlace = {
            name: place.name,
            lat: place.lat,
            lon: place.lng,
            description: place.description || "",
            time_to_spend: place.duration || place.time_to_spend || "",
            day: place.day || "",
            type: place.type || "place"
        };
        tripPlaces.push(tripPlace);
        allTripPlaces.push(tripPlace);

        var safeNameId = "img-" + place.name.replace(/[^a-zA-Z0-9]/g, "");
        var markerColor = "#2563eb";
        var markerLabel = "P";

        if (place.type === "hotel") {
            markerColor = "#8b5cf6";
            markerLabel = "H";
        } else if (place.type === "restaurant") {
            markerColor = "#f59e0b";
            markerLabel = "R";
        } else if (place.type === "travel") {
            markerColor = "#10b981";
            markerLabel = "T";
        }

        var customIcon = L.divIcon({
            className: "custom-div-icon",
            html: `<div style="background:${markerColor};color:white;border-radius:50%;width:30px;height:30px;display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:800;box-shadow:0 8px 24px rgba(5,2,16,0.24);border:2px solid white;transform:translateY(-10px);">${markerLabel}</div>`,
            iconSize: [30, 30],
            iconAnchor: [15, 15],
            popupAnchor: [0, -15]
        });

        var marker = L.marker([place.lat, place.lng], { icon: customIcon }).addTo(map);
        marker._tripDay = place.day || 1;
        marker.bindPopup(`
            <div style="width:220px;padding:12px;color:#f8f5ff;font-family:Manrope,sans-serif;">
                <img id="${safeNameId}" src="" alt="${place.name}" style="display:none;width:100%;height:130px;object-fit:cover;border-radius:14px;margin-bottom:10px;box-shadow:0 8px 24px rgba(5,2,16,0.22);">
                <h3 style="font-weight:800;font-size:16px;line-height:1.35;margin-bottom:4px;">${place.name}</h3>
                <span style="display:inline-block;font-size:11px;padding:4px 8px;background:rgba(124,92,255,0.16);color:#d8ccff;border-radius:999px;font-weight:700;">Day ${place.day || 1}</span>
                <p style="font-size:12px;margin-top:10px;line-height:1.5;color:#cbd5e1;">${place.description || ""}</p>
                <div style="display:flex;justify-content:space-between;margin-top:8px;">
                    <span style="font-size:12px;color:#e9ddff;font-weight:700;">${place.time_to_spend || ""}</span>
                </div>
            </div>
        `);

        marker.on("popupopen", function () {
            var imgEl = document.getElementById(safeNameId);
            if (imgEl && imgEl.style.display === "none") {
                loadPlaceImage(place.name, place.lat, place.lng, safeNameId);
            }
        });

        mapMarkers.push(marker);
    });

    updateTripList();

    if (tripPlaces.length > 0) {
        map.setView([tripPlaces[0].lat, tripPlaces[0].lon], 13);
    }

    if (typeof showRoute !== "undefined" && showRoute === "1") {
        var satBtn = null;
        document.querySelectorAll(".mapBtn").forEach(function (btn) {
            if (btn.innerText.toLowerCase().indexOf("satellite") !== -1) satBtn = btn;
        });
        if (satBtn) setMapStyle("satellite", satBtn);
        var firstDay = allTripPlaces.reduce(function (minDay, place) {
            var day = parseInt(place.day, 10) || 1;
            return minDay === null || day < minDay ? day : minDay;
        }, null);
        if (firstDay !== null) {
            setTimeout(function () {
                setAiDay(firstDay);
            }, 200);
            return;
        }
    }

    setTimeout(function () {
        if (typeof drawRoute === "function" && typeof showRoute !== "undefined" && showRoute === "1") {
            drawRoute();
        }
    }, 800);
});

